from __future__ import annotations

import httpx
import pytest

from brainstem.api import create_app
from brainstem.auth import AgentRole, AuthContext, AuthManager, AuthMode
from brainstem.store import InMemoryRepository


def _disabled_client() -> httpx.AsyncClient:
    app = create_app(
        repository=InMemoryRepository(),
        auth_manager=AuthManager(mode=AuthMode.DISABLED),
    )
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _auth_client() -> httpx.AsyncClient:
    manager = AuthManager(
        mode=AuthMode.API_KEY,
        api_keys={
            "writer-key": AuthContext("t_demo", "a_writer", AgentRole.WRITER),
            "admin-key": AuthContext("t_demo", "a_admin", AgentRole.ADMIN),
        },
    )
    app = create_app(repository=InMemoryRepository(), auth_manager=manager)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_model_registry_endpoints_and_recall_routing() -> None:
    async with _disabled_client() as client:
        register = await client.post(
            "/v0/models/reranker/canary/register",
            json={
                "tenant_id": "t_demo",
                "agent_id": "a_admin",
                "version": "reranker-canary-v2",
                "rollout_percent": 0,
                "tenant_allowlist": ["t_demo"],
            },
        )
        assert register.status_code == 200
        assert register.json()["canary_version"] == "reranker-canary-v2"

        remember = await client.post(
            "/v0/memory/remember",
            json={
                "tenant_id": "t_demo",
                "agent_id": "a_writer",
                "scope": "team",
                "items": [{"type": "fact", "text": "Canary routing fact."}],
            },
        )
        assert remember.status_code == 200

        recall = await client.post(
            "/v0/memory/recall",
            json={
                "tenant_id": "t_demo",
                "agent_id": "a_writer",
                "scope": "team",
                "query": "What canary fact exists?",
            },
        )
        assert recall.status_code == 200
        assert recall.json()["model_version"] == "reranker-canary-v2"
        assert recall.json()["model_route"] == "canary_allowlist"

        signal = await client.post(
            "/v0/models/reranker/signals",
            json={
                "tenant_id": "t_demo",
                "agent_id": "a_admin",
                "version": "reranker-canary-v2",
                "metric": "recall_at_5",
                "value": 0.93,
                "source": "eval_suite",
            },
        )
        assert signal.status_code == 200
        summary = signal.json()["signal_summary"]["reranker-canary-v2"]
        assert summary["recall_at_5.count"] == 1.0

        state = await client.get("/v0/models/reranker?tenant_id=t_demo&agent_id=a_admin")
        assert state.status_code == 200
        assert state.json()["canary_version"] == "reranker-canary-v2"

        promote = await client.post(
            "/v0/models/reranker/canary/promote",
            json={"tenant_id": "t_demo", "agent_id": "a_admin"},
        )
        assert promote.status_code == 200
        assert promote.json()["active_version"] == "reranker-canary-v2"
        assert promote.json()["canary_version"] is None


@pytest.mark.anyio
async def test_model_registry_admin_only_routes() -> None:
    async with _auth_client() as client:
        denied = await client.post(
            "/v0/models/reranker/canary/register",
            headers={"x-brainstem-api-key": "writer-key"},
            json={
                "tenant_id": "t_demo",
                "agent_id": "a_writer",
                "version": "reranker-canary-v2",
                "rollout_percent": 10,
            },
        )
        assert denied.status_code == 403

        allowed = await client.post(
            "/v0/models/reranker/canary/register",
            headers={"x-brainstem-api-key": "admin-key"},
            json={
                "tenant_id": "t_demo",
                "agent_id": "a_admin",
                "version": "reranker-canary-v2",
                "rollout_percent": 10,
            },
        )
        assert allowed.status_code == 200
