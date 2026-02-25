from __future__ import annotations

import pytest

from brainstem.auth import AgentRole
from brainstem.mcp_auth import MCPAuthManager, MCPAuthMode


def test_mcp_auth_from_env_requires_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAINSTEM_MCP_AUTH_MODE", "token")
    monkeypatch.delenv("BRAINSTEM_MCP_TOKENS", raising=False)
    with pytest.raises(ValueError, match="BRAINSTEM_MCP_TOKENS is required"):
        MCPAuthManager.from_env()


def test_mcp_auth_from_env_parses_and_authenticates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAINSTEM_MCP_AUTH_MODE", "token")
    monkeypatch.setenv(
        "BRAINSTEM_MCP_TOKENS",
        '{"writer":{"tenant_id":"t1","agent_id":"a1","role":"writer"}}',
    )
    manager = MCPAuthManager.from_env()
    context = manager.authenticate({"_session": {"token": "writer"}})
    assert context.tenant_id == "t1"
    assert context.agent_id == "a1"
    assert context.role is AgentRole.WRITER
    assert manager.strip_auth({"auth_token": "writer", "tenant_id": "t1"}) == {"tenant_id": "t1"}


def test_mcp_auth_disabled_mode_returns_bypass_context() -> None:
    manager = MCPAuthManager(mode=MCPAuthMode.DISABLED)
    context = manager.authenticate({})
    assert context.bypass is True
    assert context.role is AgentRole.ADMIN
