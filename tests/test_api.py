from __future__ import annotations

import httpx
import pytest

from brainstem.api import create_app
from brainstem.auth import AuthManager, AuthMode
from brainstem.store import InMemoryRepository


def _client() -> httpx.AsyncClient:
    app = create_app(
        repository=InMemoryRepository(),
        auth_manager=AuthManager(mode=AuthMode.DISABLED),
    )
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_healthz() -> None:
    async with _client() as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_memory_lifecycle() -> None:
    async with _client() as client:
        remember_response = await client.post(
            "/v0/memory/remember",
            json={
                "tenant_id": "t_demo",
                "agent_id": "a_writer",
                "scope": "team",
                "items": [
                    {
                        "type": "fact",
                        "text": "Deployment migration must finish before April planning cycle.",
                        "trust_level": "trusted_tool",
                        "source_ref": "trace_01",
                    }
                ],
                "idempotency_key": "idem-1",
            },
        )
        assert remember_response.status_code == 200
        payload = remember_response.json()
        assert payload["accepted"] == 1
        memory_id = payload["memory_ids"][0]

        replay_response = await client.post(
            "/v0/memory/remember",
            json={
                "tenant_id": "t_demo",
                "agent_id": "a_writer",
                "scope": "team",
                "items": [
                    {
                        "type": "fact",
                        "text": "Deployment migration must finish before April planning cycle.",
                        "trust_level": "trusted_tool",
                        "source_ref": "trace_01",
                    }
                ],
                "idempotency_key": "idem-1",
            },
        )
        assert replay_response.status_code == 200
        assert "idempotency_replay" in replay_response.json()["warnings"]

        recall_response = await client.post(
            "/v0/memory/recall",
            json={
                "tenant_id": "t_demo",
                "agent_id": "a_writer",
                "query": "What migration constraints exist?",
                "scope": "team",
                "budget": {"max_items": 10, "max_tokens": 1200},
                "filters": {"trust_min": 0.0, "types": ["fact"]},
            },
        )
        assert recall_response.status_code == 200
        recall_payload = recall_response.json()
        assert len(recall_payload["items"]) >= 1
        assert recall_payload["items"][0]["memory_id"] == memory_id

        inspect_response = await client.get(
            f"/v0/memory/{memory_id}?tenant_id=t_demo&agent_id=a_writer&scope=team"
        )
        assert inspect_response.status_code == 200
        assert inspect_response.json()["memory_id"] == memory_id

        delete_response = await client.request(
            "DELETE",
            f"/v0/memory/{memory_id}",
            json={"tenant_id": "t_demo", "agent_id": "a_writer"},
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["deleted"] is True

        inspect_after_delete = await client.get(
            f"/v0/memory/{memory_id}?tenant_id=t_demo&agent_id=a_writer&scope=team"
        )
        assert inspect_after_delete.status_code == 404


@pytest.mark.anyio
async def test_reflect_and_train() -> None:
    async with _client() as client:
        remember = await client.post(
            "/v0/memory/remember",
            json={
                "tenant_id": "t_demo",
                "agent_id": "a_ops",
                "scope": "team",
                "items": [
                    {
                        "type": "event",
                        "text": "Team is blocked by missing migration runbook and deadline risk.",
                        "trust_level": "user_claim",
                    }
                ],
            },
        )
        assert remember.status_code == 200

        reflect = await client.post(
            "/v0/memory/reflect",
            json={"tenant_id": "t_demo", "agent_id": "a_ops", "window_hours": 24},
        )
        assert reflect.status_code == 200
        assert reflect.json()["status"] == "completed"

        train = await client.post(
            "/v0/memory/train",
            json={"tenant_id": "t_demo", "model_kind": "reranker", "lookback_days": 7},
        )
        assert train.status_code == 200
        assert train.json()["status"] == "queued"
