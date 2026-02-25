from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from brainstem.mcp_tools import MCPToolService
from brainstem.store import InMemoryRepository


def _wait_for_job(service: MCPToolService, job_id: str, tenant_id: str) -> dict:
    for _ in range(40):
        status = service.job_status(
            {"job_id": job_id, "tenant_id": tenant_id, "agent_id": "mcp_admin"}
        )
        if status["status"] == "completed":
            return status
        time.sleep(0.02)
    raise AssertionError("job did not complete in time")


def test_mcp_tool_service_memory_flow() -> None:
    service = MCPToolService(repository=InMemoryRepository())
    remember = service.remember(
        {
            "tenant_id": "t_mcp",
            "agent_id": "a_mcp",
            "scope": "team",
            "items": [{"type": "fact", "text": "MCP memory fact."}],
        }
    )
    memory_id = remember["memory_ids"][0]

    recall = service.recall(
        {
            "tenant_id": "t_mcp",
            "agent_id": "a_mcp",
            "scope": "team",
            "query": "What MCP memory fact exists?",
        }
    )
    assert len(recall["items"]) >= 1
    assert recall["items"][0]["memory_id"] == memory_id

    details = service.inspect(
        {
            "tenant_id": "t_mcp",
            "agent_id": "a_mcp",
            "memory_id": memory_id,
            "scope": "team",
        }
    )
    assert details["memory_id"] == memory_id


def test_mcp_async_jobs_and_cleanup() -> None:
    service = MCPToolService(repository=InMemoryRepository())

    service.remember(
        {
            "tenant_id": "t_mcp",
            "agent_id": "mcp_admin",
            "scope": "team",
            "items": [
                {
                    "type": "fact",
                    "text": "Expired memory for cleanup.",
                    "expires_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                }
            ],
        }
    )

    reflect = service.reflect(
        {
            "tenant_id": "t_mcp",
            "agent_id": "mcp_admin",
            "window_hours": 24,
            "max_candidates": 4,
        }
    )
    reflect_status = _wait_for_job(service, reflect["job_id"], "t_mcp")
    assert "candidate_facts" in reflect_status["result"]

    train = service.train(
        {
            "tenant_id": "t_mcp",
            "agent_id": "mcp_admin",
            "model_kind": "reranker",
            "lookback_days": 7,
        }
    )
    train_status = _wait_for_job(service, train["job_id"], "t_mcp")
    assert "notes" in train_status["result"]

    cleanup = service.cleanup(
        {"tenant_id": "t_mcp", "agent_id": "mcp_admin", "grace_hours": 0}
    )
    cleanup_status = _wait_for_job(service, cleanup["job_id"], "t_mcp")
    assert cleanup_status["result"]["purged_count"] >= 1


def test_mcp_job_status_rejects_agent_mismatch() -> None:
    service = MCPToolService(repository=InMemoryRepository())
    train = service.train(
        {
            "tenant_id": "t_mcp",
            "agent_id": "a_train",
            "model_kind": "reranker",
            "lookback_days": 7,
        }
    )
    with pytest.raises(ValueError, match="agent_mismatch"):
        service.job_status(
            {"job_id": train["job_id"], "tenant_id": "t_mcp", "agent_id": "other_agent"}
        )
