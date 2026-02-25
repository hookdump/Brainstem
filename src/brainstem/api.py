"""HTTP API for Brainstem v0."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException

from brainstem.models import (
    ForgetRequest,
    ForgetResponse,
    RecallRequest,
    RecallResponse,
    ReflectRequest,
    ReflectResponse,
    RememberRequest,
    RememberResponse,
    TrainRequest,
    TrainResponse,
)
from brainstem.store import InMemoryRepository


def create_app(repository: InMemoryRepository | None = None) -> FastAPI:
    app = FastAPI(
        title="Brainstem API",
        version="0.1.0",
        description="Shared memory coprocessor for multi-agent systems.",
    )
    repo = repository if repository is not None else InMemoryRepository()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "brainstem", "version": "0.1.0"}

    @app.post("/v0/memory/remember", response_model=RememberResponse)
    async def remember(payload: RememberRequest) -> RememberResponse:
        return repo.remember(payload)

    @app.post("/v0/memory/recall", response_model=RecallResponse)
    async def recall(payload: RecallRequest) -> RecallResponse:
        return repo.recall(payload)

    @app.get("/v0/memory/{memory_id}")
    async def inspect(memory_id: str, tenant_id: str) -> dict[str, object]:
        details = repo.inspect(tenant_id=tenant_id, memory_id=memory_id)
        if details is None:
            raise HTTPException(status_code=404, detail="memory_not_found")
        return details.model_dump()

    @app.delete("/v0/memory/{memory_id}", response_model=ForgetResponse)
    async def forget(memory_id: str, payload: ForgetRequest) -> ForgetResponse:
        deleted = repo.forget(tenant_id=payload.tenant_id, memory_id=memory_id)
        if not deleted.deleted:
            raise HTTPException(status_code=404, detail="memory_not_found")
        return deleted

    @app.post("/v0/memory/reflect", response_model=ReflectResponse)
    async def reflect(payload: ReflectRequest) -> ReflectResponse:
        # v0 bootstrap: synchronous lightweight candidate generation.
        recent = repo.recall(
            RecallRequest(
                tenant_id=payload.tenant_id,
                agent_id=payload.agent_id,
                query="constraints commitments unresolved tasks",
            )
        )
        candidates = []
        for item in recent.items[: payload.max_candidates]:
            candidates.append(f"[candidate_fact] {item.text}")
        return ReflectResponse(
            job_id=f"rfl_{uuid4().hex[:8]}",
            status="completed",
            candidate_facts=candidates,
        )

    @app.post("/v0/memory/train", response_model=TrainResponse)
    async def train(payload: TrainRequest) -> TrainResponse:
        return TrainResponse(
            job_id=f"trn_{uuid4().hex[:8]}",
            status="queued",
            notes=(
                f"Queued {payload.model_kind} training for tenant {payload.tenant_id} "
                f"using {payload.lookback_days} day lookback."
            ),
        )

    @app.get("/v0/meta")
    async def meta() -> dict[str, str]:
        return {
            "service": "brainstem",
            "mode": "v0-bootstrap",
            "generated_at": datetime.now(UTC).isoformat(),
        }

    return app
