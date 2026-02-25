"""MCP-facing tool service wrappers for Brainstem."""

from __future__ import annotations

from typing import Any

from brainstem.jobs import JobManager
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
    ) -> None:
        self.repository = repository if repository is not None else InMemoryRepository()
        self.jobs = jobs if jobs is not None else JobManager(self.repository)

    def remember(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = RememberRequest.model_validate(payload)
        return self.repository.remember(request).model_dump()

    def recall(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = RecallRequest.model_validate(payload)
        return self.repository.recall(request).model_dump()

    def inspect(self, payload: dict[str, Any]) -> dict[str, Any]:
        tenant_id = str(payload["tenant_id"])
        agent_id = str(payload["agent_id"])
        memory_id = str(payload["memory_id"])
        scope = Scope(str(payload.get("scope", "private")))
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
        request = ForgetRequest.model_validate(payload)
        memory_id = str(payload["memory_id"])
        return self.repository.forget(
            tenant_id=request.tenant_id,
            agent_id=request.agent_id,
            memory_id=memory_id,
        ).model_dump()

    def reflect(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = ReflectRequest.model_validate(payload)
        job = self.jobs.submit_reflect(
            tenant_id=request.tenant_id,
            agent_id=request.agent_id,
            window_hours=request.window_hours,
            max_candidates=request.max_candidates,
        )
        return {"job_id": job.job_id, "status": "queued"}

    def train(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = TrainRequest.model_validate(payload)
        agent_id = str(payload.get("agent_id", "mcp_admin"))
        job = self.jobs.submit_train(
            tenant_id=request.tenant_id,
            agent_id=agent_id,
            model_kind=request.model_kind,
            lookback_days=request.lookback_days,
        )
        return {"job_id": job.job_id, "status": "queued"}

    def cleanup(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = CleanupRequest.model_validate(payload)
        agent_id = str(payload.get("agent_id", "mcp_admin"))
        job = self.jobs.submit_cleanup(
            tenant_id=request.tenant_id,
            agent_id=agent_id,
            grace_hours=request.grace_hours,
        )
        return {"job_id": job.job_id, "status": "queued"}

    def job_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload["job_id"])
        tenant_id = str(payload["tenant_id"])
        agent_id = str(payload.get("agent_id", "mcp_admin"))
        job = self.jobs.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            raise ValueError("job_not_found")
        if job.agent_id != agent_id and agent_id != "mcp_admin":
            raise ValueError("agent_mismatch")
        return job.to_dict()
