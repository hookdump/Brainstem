from __future__ import annotations

import httpx
import pytest

from brainstem.api import create_app
from brainstem.auth import AgentRole, AuthContext, AuthManager, AuthMode
from brainstem.store import InMemoryRepository


def _client(auth_manager: AuthManager) -> httpx.AsyncClient:
    app = create_app(repository=InMemoryRepository(), auth_manager=auth_manager)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_metrics_endpoint_tracks_requests() -> None:
    async with _client(AuthManager(mode=AuthMode.DISABLED)) as client:
        assert (await client.get("/healthz")).status_code == 200
        assert (await client.get("/healthz")).status_code == 200
        assert (
            await client.post(
                "/v0/memory/remember",
                json={
                    "tenant_id": "t_metrics",
                    "agent_id": "a_metrics",
                    "scope": "team",
                    "items": [{"type": "fact", "text": "metrics memory write"}],
                },
            )
        ).status_code == 200
        assert (
            await client.post(
                "/v0/memory/recall",
                json={
                    "tenant_id": "t_metrics",
                    "agent_id": "a_metrics",
                    "scope": "team",
                    "query": "metrics memory",
                },
            )
        ).status_code == 200

        metrics = await client.get("/v0/metrics")
        assert metrics.status_code == 200
        payload = metrics.json()
        snapshot = payload["snapshot"]
        # Snapshot is computed before middleware records the /v0/metrics request itself.
        assert snapshot["request_count"] >= 3
        assert snapshot["route_counts"]["GET /healthz"] >= 2
        assert snapshot["route_counts"]["POST /v0/memory/remember"] >= 1
        assert snapshot["route_counts"]["POST /v0/memory/recall"] >= 1
        assert snapshot["pipeline_latency_ms"]["recall.auth"]["count"] >= 1
        assert snapshot["pipeline_latency_ms"]["recall.store"]["count"] >= 1


@pytest.mark.anyio
async def test_metrics_endpoint_requires_admin_when_auth_enabled() -> None:
    auth_manager = AuthManager(
        mode=AuthMode.API_KEY,
        api_keys={
            "reader-key": AuthContext(
                tenant_id="t_obs",
                agent_id="a_reader",
                role=AgentRole.READER,
            ),
            "admin-key": AuthContext(
                tenant_id="t_obs",
                agent_id="a_admin",
                role=AgentRole.ADMIN,
            ),
        },
    )
    async with _client(auth_manager) as client:
        reader_response = await client.get(
            "/v0/metrics", headers={"x-brainstem-api-key": "reader-key"}
        )
        assert reader_response.status_code == 403

        admin_response = await client.get(
            "/v0/metrics", headers={"x-brainstem-api-key": "admin-key"}
        )
        assert admin_response.status_code == 200
