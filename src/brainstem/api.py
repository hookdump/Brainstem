"""HTTP API for Brainstem v0."""

from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException

from brainstem.auth import AgentRole, AuthContext, AuthManager
from brainstem.models import (
    ForgetRequest,
    ForgetResponse,
    RecallRequest,
    RecallResponse,
    ReflectRequest,
    ReflectResponse,
    RememberRequest,
    RememberResponse,
    Scope,
    TrainRequest,
    TrainResponse,
)
from brainstem.settings import Settings, load_settings
from brainstem.store import InMemoryRepository, MemoryRepository, SQLiteRepository


def _create_repository(settings: Settings) -> MemoryRepository:
    if settings.store_backend == "inmemory":
        return InMemoryRepository()
    if settings.store_backend == "sqlite":
        return SQLiteRepository(settings.sqlite_path)
    raise ValueError(f"unsupported BRAINSTEM_STORE_BACKEND: {settings.store_backend}")


def _create_auth_manager(settings: Settings) -> AuthManager:
    return AuthManager.from_json(settings.auth_mode, settings.api_keys_json)


def create_app(
    repository: MemoryRepository | None = None,
    settings: Settings | None = None,
    auth_manager: AuthManager | None = None,
) -> FastAPI:
    runtime_settings = settings if settings is not None else load_settings()
    repo = repository if repository is not None else _create_repository(runtime_settings)
    auth = auth_manager if auth_manager is not None else _create_auth_manager(runtime_settings)

    app = FastAPI(
        title="Brainstem API",
        version="0.2.0",
        description="Shared memory coprocessor for multi-agent systems.",
    )

    async def get_auth_context(
        x_brainstem_api_key: Annotated[str | None, Header()] = None,
    ) -> AuthContext:
        return auth.authenticate(x_brainstem_api_key)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "service": "brainstem", "version": "0.2.0"}

    @app.post("/v0/memory/remember", response_model=RememberResponse)
    async def remember(
        payload: RememberRequest,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> RememberResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            minimum_role=AgentRole.WRITER,
            scope=payload.scope,
        )
        return repo.remember(payload)

    @app.post("/v0/memory/recall", response_model=RecallResponse)
    async def recall(
        payload: RecallRequest,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> RecallResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            minimum_role=AgentRole.READER,
        )
        return repo.recall(payload)

    @app.get("/v0/memory/{memory_id}")
    async def inspect(
        memory_id: str,
        tenant_id: str,
        agent_id: str,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
        scope: Scope = Scope.PRIVATE,
    ) -> dict[str, object]:
        auth.authorize(
            context=auth_context,
            tenant_id=tenant_id,
            agent_id=agent_id,
            minimum_role=AgentRole.READER,
        )
        details = repo.inspect(
            tenant_id=tenant_id,
            agent_id=agent_id,
            scope=scope,
            memory_id=memory_id,
        )
        if details is None:
            raise HTTPException(status_code=404, detail="memory_not_found")
        return details.model_dump()

    @app.delete("/v0/memory/{memory_id}", response_model=ForgetResponse)
    async def forget(
        memory_id: str,
        payload: ForgetRequest,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> ForgetResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            minimum_role=AgentRole.WRITER,
        )
        deleted = repo.forget(
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            memory_id=memory_id,
        )
        if not deleted.deleted:
            raise HTTPException(status_code=404, detail="memory_not_found")
        return deleted

    @app.post("/v0/memory/reflect", response_model=ReflectResponse)
    async def reflect(
        payload: ReflectRequest,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> ReflectResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            minimum_role=AgentRole.WRITER,
        )
        recent = repo.recall(
            RecallRequest(
                tenant_id=payload.tenant_id,
                agent_id=payload.agent_id,
                scope=Scope.GLOBAL,
                query="constraints commitments unresolved tasks deadlines",
            )
        )
        candidates = [
            f"[candidate_fact] {item.text}" for item in recent.items[: payload.max_candidates]
        ]
        return ReflectResponse(
            job_id=f"rfl_{uuid4().hex[:8]}",
            status="completed",
            candidate_facts=candidates,
        )

    @app.post("/v0/memory/train", response_model=TrainResponse)
    async def train(
        payload: TrainRequest,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> TrainResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=auth_context.agent_id,
            minimum_role=AgentRole.ADMIN,
        )
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
            "mode": "v0",
            "store_backend": runtime_settings.store_backend,
            "auth_mode": runtime_settings.auth_mode,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    return app
