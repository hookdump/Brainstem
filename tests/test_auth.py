from __future__ import annotations

import httpx
import pytest

from brainstem.api import create_app
from brainstem.auth import AgentRole, AuthContext, AuthManager, AuthMode
from brainstem.store import InMemoryRepository


def _auth_client(auth_manager: AuthManager) -> httpx.AsyncClient:
    app = create_app(repository=InMemoryRepository(), auth_manager=auth_manager)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _manager() -> AuthManager:
    return AuthManager(
        mode=AuthMode.API_KEY,
        api_keys={
            "reader-key": AuthContext(
                tenant_id="t_auth",
                agent_id="a_reader",
                role=AgentRole.READER,
            ),
            "writer-key": AuthContext(
                tenant_id="t_auth",
                agent_id="a_writer",
                role=AgentRole.WRITER,
            ),
            "admin-key": AuthContext(
                tenant_id="t_auth",
                agent_id="a_admin",
                role=AgentRole.ADMIN,
            ),
        },
    )


@pytest.mark.anyio
async def test_missing_api_key_rejected() -> None:
    async with _auth_client(_manager()) as client:
        response = await client.post(
            "/v0/memory/remember",
            json={
                "tenant_id": "t_auth",
                "agent_id": "a_writer",
                "scope": "team",
                "items": [{"type": "fact", "text": "missing key"}],
            },
        )
    assert response.status_code == 401
    assert response.json()["detail"] == "missing_api_key"


@pytest.mark.anyio
async def test_reader_cannot_write_but_can_read() -> None:
    async with _auth_client(_manager()) as client:
        write_response = await client.post(
            "/v0/memory/remember",
            headers={"x-brainstem-api-key": "reader-key"},
            json={
                "tenant_id": "t_auth",
                "agent_id": "a_reader",
                "scope": "team",
                "items": [{"type": "fact", "text": "reader cannot write"}],
            },
        )
        assert write_response.status_code == 403
        assert write_response.json()["detail"] == "insufficient_role"

        admin_write = await client.post(
            "/v0/memory/remember",
            headers={"x-brainstem-api-key": "admin-key"},
            json={
                "tenant_id": "t_auth",
                "agent_id": "a_admin",
                "scope": "team",
                "items": [{"type": "fact", "text": "team memory for reader"}],
            },
        )
        assert admin_write.status_code == 200

        read_response = await client.post(
            "/v0/memory/recall",
            headers={"x-brainstem-api-key": "reader-key"},
            json={
                "tenant_id": "t_auth",
                "agent_id": "a_reader",
                "scope": "global",
                "query": "team memory",
            },
        )
        assert read_response.status_code == 200
        assert len(read_response.json()["items"]) >= 1


@pytest.mark.anyio
async def test_writer_scope_and_tenant_restrictions() -> None:
    async with _auth_client(_manager()) as client:
        global_scope = await client.post(
            "/v0/memory/remember",
            headers={"x-brainstem-api-key": "writer-key"},
            json={
                "tenant_id": "t_auth",
                "agent_id": "a_writer",
                "scope": "global",
                "items": [{"type": "fact", "text": "writer cannot do global"}],
            },
        )
        assert global_scope.status_code == 403
        assert global_scope.json()["detail"] == "global_scope_requires_admin"

        wrong_tenant = await client.post(
            "/v0/memory/remember",
            headers={"x-brainstem-api-key": "writer-key"},
            json={
                "tenant_id": "other_tenant",
                "agent_id": "a_writer",
                "scope": "team",
                "items": [{"type": "fact", "text": "wrong tenant"}],
            },
        )
        assert wrong_tenant.status_code == 403
        assert wrong_tenant.json()["detail"] == "tenant_mismatch"


@pytest.mark.anyio
async def test_train_requires_admin() -> None:
    async with _auth_client(_manager()) as client:
        writer_train = await client.post(
            "/v0/memory/train",
            headers={"x-brainstem-api-key": "writer-key"},
            json={
                "tenant_id": "t_auth",
                "model_kind": "reranker",
                "lookback_days": 14,
            },
        )
        assert writer_train.status_code == 403

        admin_train = await client.post(
            "/v0/memory/train",
            headers={"x-brainstem-api-key": "admin-key"},
            json={
                "tenant_id": "t_auth",
                "model_kind": "reranker",
                "lookback_days": 14,
            },
        )
        assert admin_train.status_code == 200
        assert admin_train.json()["status"] == "queued"
