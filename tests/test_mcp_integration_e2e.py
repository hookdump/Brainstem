from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import anyio
import pytest

pytest.importorskip("mcp.client.stdio")

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult

ROOT = Path(__file__).resolve().parents[1]
SERVER_SCRIPT = ROOT / "scripts" / "mcp_server.py"

DEFAULT_TOKENS = {
    "reader-token": {"tenant_id": "t_mcp", "agent_id": "a_reader", "role": "reader"},
    "writer-token": {"tenant_id": "t_mcp", "agent_id": "a_writer", "role": "writer"},
    "admin-token": {"tenant_id": "t_mcp", "agent_id": "a_admin", "role": "admin"},
}


@asynccontextmanager
async def _mcp_session(
    *,
    auth_mode: str = "token",
    tokens: dict[str, dict[str, str]] | None = DEFAULT_TOKENS,
):
    env = {"BRAINSTEM_MCP_AUTH_MODE": auth_mode}
    if tokens is not None:
        env["BRAINSTEM_MCP_TOKENS"] = json.dumps(tokens)

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_SCRIPT)],
        env=env,
        cwd=str(ROOT),
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


async def _call_tool(
    session: ClientSession,
    tool_name: str,
    payload: dict[str, Any],
) -> CallToolResult:
    return await session.call_tool(tool_name, {"payload": payload})


def _result_text(result: CallToolResult) -> str:
    return "\n".join(
        item.text
        for item in result.content
        if hasattr(item, "text") and isinstance(item.text, str)
    )


def _result_json(result: CallToolResult) -> dict[str, Any]:
    return json.loads(_result_text(result))


def test_mcp_e2e_list_tools_and_memory_flow() -> None:
    async def scenario() -> None:
        async with _mcp_session() as session:
            tools = await session.list_tools()
            tool_names = {tool.name for tool in tools.tools}
            assert "brain.remember" in tool_names
            assert "brain.recall" in tool_names
            assert "brain.job_status" in tool_names

            remember = await _call_tool(
                session,
                "brain.remember",
                {
                    "auth_token": "writer-token",
                    "tenant_id": "t_mcp",
                    "agent_id": "a_writer",
                    "scope": "team",
                    "items": [{"type": "fact", "text": "MCP E2E fact"}],
                },
            )
            assert remember.isError is False
            memory_id = str(_result_json(remember)["memory_ids"][0])

            recall = await _call_tool(
                session,
                "brain.recall",
                {
                    "_session": {"token": "reader-token"},
                    "tenant_id": "t_mcp",
                    "agent_id": "a_reader",
                    "scope": "team",
                    "query": "What MCP E2E fact exists?",
                    "budget": {"max_items": 5, "max_tokens": 2000},
                },
            )
            assert recall.isError is False
            recall_json = _result_json(recall)
            assert any(item["memory_id"] == memory_id for item in recall_json["items"])

    anyio.run(scenario)


@pytest.mark.parametrize(
    "auth_fields",
    [
        {"auth_token": "writer-token"},
        {"_session": {"token": "writer-token"}},
    ],
)
def test_mcp_e2e_accepts_token_envelopes(auth_fields: dict[str, Any]) -> None:
    async def scenario() -> None:
        async with _mcp_session() as session:
            remember = await _call_tool(
                session,
                "brain.remember",
                {
                    **auth_fields,
                    "tenant_id": "t_mcp",
                    "agent_id": "a_writer",
                    "scope": "team",
                    "items": [{"type": "fact", "text": "auth envelope smoke"}],
                },
            )
            assert remember.isError is False
            payload = _result_json(remember)
            assert payload["accepted"] == 1

    anyio.run(scenario)


def test_mcp_e2e_rejects_missing_and_invalid_tokens() -> None:
    async def scenario() -> None:
        async with _mcp_session() as session:
            missing = await _call_tool(
                session,
                "brain.recall",
                {
                    "tenant_id": "t_mcp",
                    "agent_id": "a_reader",
                    "scope": "team",
                    "query": "missing token",
                    "budget": {"max_items": 5, "max_tokens": 2000},
                },
            )
            assert missing.isError is True
            assert "missing_mcp_token" in _result_text(missing)

            invalid = await _call_tool(
                session,
                "brain.recall",
                {
                    "auth_token": "bad-token",
                    "tenant_id": "t_mcp",
                    "agent_id": "a_reader",
                    "scope": "team",
                    "query": "invalid token",
                    "budget": {"max_items": 5, "max_tokens": 2000},
                },
            )
            assert invalid.isError is True
            assert "invalid_mcp_token" in _result_text(invalid)

    anyio.run(scenario)


@pytest.mark.parametrize(
    ("tool_name", "payload", "expected_error"),
    [
        (
            "brain.remember",
            {
                "auth_token": "reader-token",
                "tenant_id": "t_mcp",
                "agent_id": "a_reader",
                "scope": "team",
                "items": [{"type": "fact", "text": "reader cannot write"}],
            },
            "insufficient_role",
        ),
        (
            "brain.train",
            {
                "auth_token": "writer-token",
                "tenant_id": "t_mcp",
                "model_kind": "reranker",
                "lookback_days": 3,
            },
            "insufficient_role",
        ),
        (
            "brain.recall",
            {
                "auth_token": "writer-token",
                "tenant_id": "t_mcp",
                "agent_id": "a_writer",
                "scope": "global",
                "query": "writers cannot request global scope",
                "budget": {"max_items": 5, "max_tokens": 2000},
            },
            "global_scope_requires_admin",
        ),
    ],
)
def test_mcp_e2e_role_boundaries(
    tool_name: str,
    payload: dict[str, Any],
    expected_error: str,
) -> None:
    async def scenario() -> None:
        async with _mcp_session() as session:
            result = await _call_tool(session, tool_name, payload)
            assert result.isError is True
            assert expected_error in _result_text(result)

    anyio.run(scenario)


def test_mcp_e2e_admin_can_query_job_status_cross_agent() -> None:
    async def scenario() -> None:
        async with _mcp_session() as session:
            reflect = await _call_tool(
                session,
                "brain.reflect",
                {
                    "auth_token": "writer-token",
                    "tenant_id": "t_mcp",
                    "agent_id": "a_writer",
                    "window_hours": 4,
                    "max_candidates": 4,
                },
            )
            assert reflect.isError is False
            job_id = str(_result_json(reflect)["job_id"])

            admin_status = await _call_tool(
                session,
                "brain.job_status",
                {
                    "auth_token": "admin-token",
                    "tenant_id": "t_mcp",
                    "agent_id": "a_admin",
                    "job_id": job_id,
                },
            )
            assert admin_status.isError is False
            status_payload = _result_json(admin_status)
            assert status_payload["job_id"] == job_id

            reader_status = await _call_tool(
                session,
                "brain.job_status",
                {
                    "auth_token": "reader-token",
                    "tenant_id": "t_mcp",
                    "agent_id": "a_reader",
                    "job_id": job_id,
                },
            )
            assert reader_status.isError is True
            assert "agent_mismatch" in _result_text(reader_status)

    anyio.run(scenario)


def test_mcp_e2e_disabled_mode_allows_legacy_payloads() -> None:
    async def scenario() -> None:
        async with _mcp_session(auth_mode="disabled", tokens=None) as session:
            remember = await _call_tool(
                session,
                "brain.remember",
                {
                    "tenant_id": "t_legacy",
                    "agent_id": "a_legacy",
                    "scope": "private",
                    "items": [{"type": "fact", "text": "legacy payload works"}],
                },
            )
            assert remember.isError is False
            payload = _result_json(remember)
            assert payload["accepted"] == 1

    anyio.run(scenario)
