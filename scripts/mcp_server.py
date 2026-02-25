#!/usr/bin/env python3
"""Brainstem MCP server entrypoint."""

from __future__ import annotations

from typing import Any

from brainstem.mcp_auth import MCPAuthManager
from brainstem.mcp_tools import MCPToolService

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - import guard for optional dependency
    raise SystemExit(
        "MCP dependency not installed. Install with `pip install -e \".[mcp]\"`."
    ) from exc


def _build_service() -> MCPToolService:
    try:
        auth_manager = MCPAuthManager.from_env()
    except ValueError as exc:
        raise SystemExit(
            "Invalid MCP auth configuration. Set BRAINSTEM_MCP_AUTH_MODE and "
            f"BRAINSTEM_MCP_TOKENS correctly. Details: {exc}"
        ) from exc
    return MCPToolService(auth_manager=auth_manager)


service = _build_service()
mcp = FastMCP("brainstem")


@mcp.tool(name="brain.remember")
def brain_remember(payload: dict[str, Any]) -> dict[str, Any]:
    return service.remember(payload)


@mcp.tool(name="brain.recall")
def brain_recall(payload: dict[str, Any]) -> dict[str, Any]:
    return service.recall(payload)


@mcp.tool(name="brain.inspect")
def brain_inspect(payload: dict[str, Any]) -> dict[str, Any]:
    return service.inspect(payload)


@mcp.tool(name="brain.forget")
def brain_forget(payload: dict[str, Any]) -> dict[str, Any]:
    return service.forget(payload)


@mcp.tool(name="brain.reflect")
def brain_reflect(payload: dict[str, Any]) -> dict[str, Any]:
    return service.reflect(payload)


@mcp.tool(name="brain.train")
def brain_train(payload: dict[str, Any]) -> dict[str, Any]:
    return service.train(payload)


@mcp.tool(name="brain.cleanup")
def brain_cleanup(payload: dict[str, Any]) -> dict[str, Any]:
    return service.cleanup(payload)


@mcp.tool(name="brain.job_status")
def brain_job_status(payload: dict[str, Any]) -> dict[str, Any]:
    return service.job_status(payload)


if __name__ == "__main__":
    mcp.run()
