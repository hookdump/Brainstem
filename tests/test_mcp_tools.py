from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from brainstem.auth import AgentRole, AuthContext
from brainstem.mcp_auth import MCPAuthManager, MCPAuthMode
from brainstem.mcp_tools import MCPToolService
from brainstem.store import InMemoryRepository


def _auth_manager() -> MCPAuthManager:
    return MCPAuthManager(
        mode=MCPAuthMode.TOKEN,
        tokens={
            "reader-token": AuthContext("t_mcp", "a_reader", AgentRole.READER),
            "writer-token": AuthContext("t_mcp", "a_writer", AgentRole.WRITER),
            "admin-token": AuthContext("t_mcp", "a_admin", AgentRole.ADMIN),
        },
    )


def _with_token(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {"auth_token": token, **payload}


def _wait_for_job(service: MCPToolService, job_id: str, token: str) -> dict[str, Any]:
    for _ in range(40):
        status = service.job_status(_with_token(token, {"job_id": job_id}))
        if status["status"] == "completed":
            return status
        time.sleep(0.02)
    raise AssertionError("job did not complete in time")


def test_mcp_tool_service_memory_flow() -> None:
    service = MCPToolService(repository=InMemoryRepository(), auth_manager=_auth_manager())

    remember = service.remember(
        _with_token(
            "writer-token",
            {
                "scope": "team",
                "items": [{"type": "fact", "text": "MCP memory fact."}],
            },
        )
    )
    memory_id = remember["memory_ids"][0]

    compact = service.compact(
        _with_token(
            "writer-token",
            {
                "scope": "team",
                "query": "Summarize MCP memory fact context",
                "target_tokens": 200,
                "max_source_items": 10,
            },
        )
    )
    assert compact["created_memory_id"] is not None
    assert compact["source_count"] >= 1

    recall = service.recall(
        _with_token(
            "reader-token",
            {
                "scope": "team",
                "query": "What MCP memory fact exists?",
            },
        )
    )
    assert len(recall["items"]) >= 1
    recall_ids = [item["memory_id"] for item in recall["items"]]
    assert memory_id in recall_ids
    assert compact["created_memory_id"] in recall_ids
    assert recall["model_version"] is not None
    assert recall["model_route"] is not None

    details = service.inspect(
        _with_token(
            "writer-token",
            {
                "memory_id": memory_id,
                "scope": "team",
            },
        )
    )
    assert details["memory_id"] == memory_id


def test_mcp_async_jobs_and_cleanup() -> None:
    service = MCPToolService(repository=InMemoryRepository(), auth_manager=_auth_manager())

    service.remember(
        _with_token(
            "writer-token",
            {
                "scope": "team",
                "items": [
                    {
                        "type": "fact",
                        "text": "Expired memory for cleanup.",
                        "expires_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                    }
                ],
            },
        )
    )

    reflect = service.reflect(
        _with_token(
            "writer-token",
            {
                "window_hours": 24,
                "max_candidates": 4,
            },
        )
    )
    reflect_status = _wait_for_job(service, reflect["job_id"], "admin-token")
    assert "candidate_facts" in reflect_status["result"]

    train = service.train(
        _with_token(
            "admin-token",
            {
                "model_kind": "reranker",
                "lookback_days": 7,
            },
        )
    )
    train_status = _wait_for_job(service, train["job_id"], "admin-token")
    assert "notes" in train_status["result"]

    cleanup = service.cleanup(_with_token("admin-token", {"grace_hours": 0}))
    cleanup_status = _wait_for_job(service, cleanup["job_id"], "admin-token")
    assert cleanup_status["result"]["purged_count"] >= 1


def test_mcp_auth_rejects_missing_token() -> None:
    service = MCPToolService(repository=InMemoryRepository(), auth_manager=_auth_manager())
    with pytest.raises(ValueError, match="missing_mcp_token"):
        service.recall({"query": "anything"})


def test_mcp_auth_rejects_invalid_token() -> None:
    service = MCPToolService(repository=InMemoryRepository(), auth_manager=_auth_manager())
    with pytest.raises(ValueError, match="invalid_mcp_token"):
        service.recall(_with_token("bad-token", {"query": "anything"}))


def test_mcp_auth_enforces_tenant_and_agent() -> None:
    service = MCPToolService(repository=InMemoryRepository(), auth_manager=_auth_manager())

    with pytest.raises(ValueError, match="tenant_mismatch"):
        service.remember(
            _with_token(
                "writer-token",
                {
                    "tenant_id": "other_tenant",
                    "scope": "team",
                    "items": [{"type": "fact", "text": "X"}],
                },
            )
        )

    with pytest.raises(ValueError, match="agent_mismatch"):
        service.remember(
            _with_token(
                "writer-token",
                {
                    "agent_id": "other_agent",
                    "scope": "team",
                    "items": [{"type": "fact", "text": "Y"}],
                },
            )
        )


def test_mcp_auth_enforces_role_and_scope() -> None:
    service = MCPToolService(repository=InMemoryRepository(), auth_manager=_auth_manager())

    with pytest.raises(ValueError, match="insufficient_role"):
        service.remember(
            _with_token(
                "reader-token",
                {"scope": "team", "items": [{"type": "fact", "text": "readers can't write"}]},
            )
        )

    with pytest.raises(ValueError, match="global_scope_requires_admin"):
        service.remember(
            _with_token(
                "writer-token",
                {"scope": "global", "items": [{"type": "fact", "text": "global write"}]},
            )
        )


def test_mcp_job_status_rejects_non_admin_cross_agent_access() -> None:
    service = MCPToolService(repository=InMemoryRepository(), auth_manager=_auth_manager())
    reflect = service.reflect(
        _with_token(
            "writer-token",
            {
                "window_hours": 24,
                "max_candidates": 4,
            },
        )
    )
    with pytest.raises(ValueError, match="agent_mismatch"):
        service.job_status(_with_token("reader-token", {"job_id": reflect["job_id"]}))


def test_mcp_auth_disabled_mode_allows_legacy_calls() -> None:
    disabled = MCPAuthManager(mode=MCPAuthMode.DISABLED)
    service = MCPToolService(repository=InMemoryRepository(), auth_manager=disabled)
    remember = service.remember(
        {
            "tenant_id": "t_mcp",
            "agent_id": "a_legacy",
            "scope": "team",
            "items": [{"type": "fact", "text": "Legacy no-token call."}],
        }
    )
    assert remember["accepted"] == 1
