"""Authentication and session context handling for MCP tool calls."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from brainstem.auth import AgentRole, AuthContext


class MCPAuthMode(StrEnum):
    DISABLED = "disabled"
    TOKEN = "token"


class MCPAuthManager:
    def __init__(
        self,
        mode: MCPAuthMode = MCPAuthMode.TOKEN,
        tokens: dict[str, AuthContext] | None = None,
    ) -> None:
        self.mode = mode
        self.tokens = tokens or {}
        if self.mode is MCPAuthMode.TOKEN and not self.tokens:
            raise ValueError(
                "BRAINSTEM_MCP_TOKENS must define at least one token when token auth is enabled"
            )

    @classmethod
    def from_env(
        cls,
        mode: str | None = None,
        tokens_json: str | None = None,
    ) -> MCPAuthManager:
        raw_mode = mode if mode is not None else os.getenv("BRAINSTEM_MCP_AUTH_MODE", "token")
        auth_mode = MCPAuthMode(raw_mode.lower())
        if auth_mode is MCPAuthMode.DISABLED:
            return cls(mode=auth_mode, tokens={})

        raw_tokens = tokens_json or os.getenv("BRAINSTEM_MCP_TOKENS")
        if raw_tokens is None:
            raise ValueError(
                "BRAINSTEM_MCP_TOKENS is required when BRAINSTEM_MCP_AUTH_MODE=token"
            )

        payload = json.loads(raw_tokens)
        if not isinstance(payload, dict):
            raise ValueError("BRAINSTEM_MCP_TOKENS must be a JSON object")

        parsed: dict[str, AuthContext] = {}
        for token, value in payload.items():
            if not isinstance(value, dict):
                raise ValueError("MCP token entries must be JSON objects")
            parsed[str(token)] = AuthContext(
                tenant_id=str(value["tenant_id"]),
                agent_id=str(value["agent_id"]),
                role=AgentRole(str(value["role"])),
            )
        return cls(mode=auth_mode, tokens=parsed)

    @staticmethod
    def strip_auth(payload: Mapping[str, Any]) -> dict[str, Any]:
        cleaned = dict(payload)
        cleaned.pop("auth_token", None)
        cleaned.pop("_session", None)
        return cleaned

    def authenticate(self, payload: Mapping[str, Any]) -> AuthContext:
        if self.mode is MCPAuthMode.DISABLED:
            return AuthContext(
                tenant_id="*",
                agent_id="*",
                role=AgentRole.ADMIN,
                bypass=True,
            )

        token = self._extract_token(payload)
        if token is None:
            raise ValueError("missing_mcp_token")

        context = self.tokens.get(token)
        if context is None:
            raise ValueError("invalid_mcp_token")
        return context

    @staticmethod
    def _extract_token(payload: Mapping[str, Any]) -> str | None:
        token = payload.get("auth_token")
        if token is not None:
            return str(token)

        session = payload.get("_session")
        if isinstance(session, dict):
            session_token = session.get("token")
            if session_token is not None:
                return str(session_token)
        return None
