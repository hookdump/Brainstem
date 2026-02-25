"""MCP-facing tool service wrappers for Brainstem."""

from __future__ import annotations

from typing import Any

from brainstem.auth import AgentRole, AuthContext, role_rank
from brainstem.jobs import JobManager
from brainstem.mcp_auth import MCPAuthManager
from brainstem.model_registry import ModelRegistry
from brainstem.models import (
    CleanupRequest,
    ForgetRequest,
    RecallRequest,
    ReflectRequest,
    RememberRequest,
    Scope,
    TrainRequest,
)
from brainstem.store import InMemoryRepository, MemoryRepository


class MCPToolService:
    def __init__(
        self,
        repository: MemoryRepository | None = None,
        jobs: JobManager | None = None,
        auth_manager: MCPAuthManager | None = None,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        self.repository = repository if repository is not None else InMemoryRepository()
        self.model_registry = model_registry if model_registry is not None else ModelRegistry()
        self.jobs = (
            jobs
            if jobs is not None
            else JobManager(self.repository, model_registry=self.model_registry)
        )
        self.auth_manager = auth_manager if auth_manager is not None else MCPAuthManager.from_env()

    def _authorize(
        self,
        payload: dict[str, Any],
        *,
        minimum_role: AgentRole,
        require_agent: bool,
        allow_admin_agent_override: bool = False,
    ) -> tuple[dict[str, Any], AuthContext]:
        context = self.auth_manager.authenticate(payload)
        normalized = self.auth_manager.strip_auth(payload)
        if context.bypass:
            return normalized, context

        if role_rank(context.role) < role_rank(minimum_role):
            raise ValueError("insufficient_role")

        tenant_id = str(normalized.get("tenant_id", context.tenant_id))
        if tenant_id != context.tenant_id:
            raise ValueError("tenant_mismatch")
        normalized["tenant_id"] = tenant_id

        if require_agent:
            agent_id = str(normalized.get("agent_id", context.agent_id))
            if (
                agent_id != context.agent_id
                and not (allow_admin_agent_override and context.role is AgentRole.ADMIN)
            ):
                raise ValueError("agent_mismatch")
            normalized["agent_id"] = agent_id
        elif "agent_id" in normalized:
            agent_id = str(normalized["agent_id"])
            if (
                agent_id != context.agent_id
                and not (allow_admin_agent_override and context.role is AgentRole.ADMIN)
            ):
                raise ValueError("agent_mismatch")

        scope = normalized.get("scope")
        if (
            scope is not None
            and Scope(str(scope)) is Scope.GLOBAL
            and context.role is not AgentRole.ADMIN
        ):
            raise ValueError("global_scope_requires_admin")

        return normalized, context

    def remember(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._authorize(
            payload,
            minimum_role=AgentRole.WRITER,
            require_agent=True,
        )
        request = RememberRequest.model_validate(normalized)
        return self.repository.remember(request).model_dump()

    def recall(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._authorize(
            payload,
            minimum_role=AgentRole.READER,
            require_agent=True,
        )
        request = RecallRequest.model_validate(normalized)
        response = self.repository.recall(request)
        model_version, model_route = self.model_registry.select_version(
            model_kind="reranker",
            tenant_id=request.tenant_id,
        )
        response.model_version = model_version
        response.model_route = model_route
        return response.model_dump()

    def inspect(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._authorize(
            payload,
            minimum_role=AgentRole.READER,
            require_agent=True,
        )
        tenant_id = str(normalized["tenant_id"])
        agent_id = str(normalized["agent_id"])
        memory_id = str(normalized["memory_id"])
        scope = Scope(str(normalized.get("scope", "private")))
        details = self.repository.inspect(
            tenant_id=tenant_id,
            agent_id=agent_id,
            scope=scope,
            memory_id=memory_id,
        )
        if details is None:
            raise ValueError("memory_not_found")
        return details.model_dump()

    def forget(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._authorize(
            payload,
            minimum_role=AgentRole.WRITER,
            require_agent=True,
        )
        request = ForgetRequest.model_validate(normalized)
        memory_id = str(normalized["memory_id"])
        return self.repository.forget(
            tenant_id=request.tenant_id,
            agent_id=request.agent_id,
            memory_id=memory_id,
        ).model_dump()

    def reflect(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, _ = self._authorize(
            payload,
            minimum_role=AgentRole.WRITER,
            require_agent=True,
        )
        request = ReflectRequest.model_validate(normalized)
        job = self.jobs.submit_reflect(
            tenant_id=request.tenant_id,
            agent_id=request.agent_id,
            window_hours=request.window_hours,
            max_candidates=request.max_candidates,
        )
        return {"job_id": job.job_id, "status": "queued"}

    def train(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, context = self._authorize(
            payload,
            minimum_role=AgentRole.ADMIN,
            require_agent=False,
        )
        request = TrainRequest.model_validate(normalized)
        agent_id = str(normalized.get("agent_id", context.agent_id))
        job = self.jobs.submit_train(
            tenant_id=request.tenant_id,
            agent_id=agent_id,
            model_kind=request.model_kind,
            lookback_days=request.lookback_days,
        )
        return {"job_id": job.job_id, "status": "queued"}

    def cleanup(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, context = self._authorize(
            payload,
            minimum_role=AgentRole.ADMIN,
            require_agent=False,
        )
        request = CleanupRequest.model_validate(normalized)
        agent_id = str(normalized.get("agent_id", context.agent_id))
        job = self.jobs.submit_cleanup(
            tenant_id=request.tenant_id,
            agent_id=agent_id,
            grace_hours=request.grace_hours,
        )
        return {"job_id": job.job_id, "status": "queued"}

    def job_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized, context = self._authorize(
            payload,
            minimum_role=AgentRole.READER,
            require_agent=False,
            allow_admin_agent_override=True,
        )
        job_id = str(normalized["job_id"])
        tenant_id = str(normalized["tenant_id"])
        job = self.jobs.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            raise ValueError("job_not_found")
        if (
            not context.bypass
            and context.role is not AgentRole.ADMIN
            and job.agent_id != context.agent_id
        ):
            raise ValueError("agent_mismatch")
        return job.to_dict()
