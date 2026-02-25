"""Authentication and authorization primitives for Brainstem."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

from fastapi import HTTPException, status

from brainstem.models import Scope


class AgentRole(StrEnum):
    READER = "reader"
    WRITER = "writer"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class AuthContext:
    tenant_id: str
    agent_id: str
    role: AgentRole
    bypass: bool = False


class AuthMode(StrEnum):
    DISABLED = "disabled"
    API_KEY = "api_key"


def role_rank(role: AgentRole) -> int:
    return {
        AgentRole.READER: 1,
        AgentRole.WRITER: 2,
        AgentRole.ADMIN: 3,
    }[role]


class AuthManager:
    def __init__(
        self,
        mode: AuthMode = AuthMode.DISABLED,
        api_keys: dict[str, AuthContext] | None = None,
    ) -> None:
        self.mode = mode
        self.api_keys = api_keys or {}

    @classmethod
    def from_json(cls, mode: str, raw_json: str | None) -> AuthManager:
        auth_mode = AuthMode(mode)
        if auth_mode is AuthMode.DISABLED:
            return cls(mode=auth_mode)

        if raw_json is None:
            raise ValueError("BRAINSTEM_API_KEYS is required when auth mode is api_key")

        payload = json.loads(raw_json)
        if not isinstance(payload, dict):
            raise ValueError("BRAINSTEM_API_KEYS must be a JSON object")

        parsed: dict[str, AuthContext] = {}
        for api_key, value in payload.items():
            if not isinstance(value, dict):
                raise ValueError("API key entries must be JSON objects")
            tenant_id = str(value["tenant_id"])
            agent_id = str(value["agent_id"])
            role = AgentRole(str(value["role"]))
            parsed[str(api_key)] = AuthContext(
                tenant_id=tenant_id,
                agent_id=agent_id,
                role=role,
            )
        return cls(mode=auth_mode, api_keys=parsed)

    def authenticate(self, api_key: str | None) -> AuthContext:
        if self.mode is AuthMode.DISABLED:
            return AuthContext(
                tenant_id="*",
                agent_id="*",
                role=AgentRole.ADMIN,
                bypass=True,
            )

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="missing_api_key",
            )
        context = self.api_keys.get(api_key)
        if context is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid_api_key",
            )
        return context

    def authorize(
        self,
        context: AuthContext,
        tenant_id: str,
        agent_id: str,
        minimum_role: AgentRole,
        scope: Scope | None = None,
    ) -> None:
        if context.bypass:
            return
        if context.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="tenant_mismatch",
            )
        if context.role is not AgentRole.ADMIN and context.agent_id != agent_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="agent_mismatch",
            )
        if role_rank(context.role) < role_rank(minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="insufficient_role",
            )
        if scope is Scope.GLOBAL and context.role is not AgentRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="global_scope_requires_admin",
            )
