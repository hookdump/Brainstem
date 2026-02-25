"""HTTP API for Brainstem v0."""

import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from starlette.responses import Response

from brainstem.auth import AgentRole, AuthContext, AuthManager
from brainstem.graph import (
    GraphAugmentedRepository,
    InMemoryGraphStore,
    PostgresGraphStore,
    SQLiteGraphStore,
)
from brainstem.jobs import JobManager
from brainstem.model_registry import ModelRegistry
from brainstem.models import (
    CleanupRequest,
    CleanupResponse,
    ForgetRequest,
    ForgetResponse,
    JobStatusResponse,
    ModelKind,
    ModelRegistryStateResponse,
    ModelSignalRequest,
    PromoteCanaryRequest,
    RecallRequest,
    RecallResponse,
    ReflectRequest,
    ReflectResponse,
    RegisterCanaryRequest,
    RememberRequest,
    RememberResponse,
    RollbackCanaryRequest,
    Scope,
    TrainRequest,
    TrainResponse,
)
from brainstem.observability import MetricsStore, RequestMetric, duration_ms
from brainstem.settings import Settings, load_settings
from brainstem.store import InMemoryRepository, MemoryRepository, SQLiteRepository
from brainstem.store_postgres import PostgresRepository

LOGGER = logging.getLogger("brainstem.api")


def _create_repository(settings: Settings) -> MemoryRepository:
    if settings.store_backend == "inmemory":
        return InMemoryRepository()
    if settings.store_backend == "sqlite":
        return SQLiteRepository(settings.sqlite_path)
    if settings.store_backend == "postgres":
        if not settings.postgres_dsn:
            raise ValueError(
                "BRAINSTEM_POSTGRES_DSN is required when BRAINSTEM_STORE_BACKEND=postgres"
            )
        return PostgresRepository(settings.postgres_dsn)
    raise ValueError(f"unsupported BRAINSTEM_STORE_BACKEND: {settings.store_backend}")


def _create_auth_manager(settings: Settings) -> AuthManager:
    return AuthManager.from_json(settings.auth_mode, settings.api_keys_json)


def _create_job_manager(
    settings: Settings,
    repository: MemoryRepository,
    model_registry: ModelRegistry,
) -> JobManager:
    if settings.job_backend == "inprocess":
        return JobManager(
            repository=repository,
            model_registry=model_registry,
        )
    if settings.job_backend == "sqlite":
        return JobManager(
            repository=repository,
            sqlite_path=settings.job_sqlite_path,
            start_worker=settings.job_worker_enabled,
            model_registry=model_registry,
        )
    raise ValueError(f"unsupported BRAINSTEM_JOB_BACKEND: {settings.job_backend}")


def _create_graph_store(
    settings: Settings,
) -> InMemoryGraphStore | SQLiteGraphStore | PostgresGraphStore | None:
    if not settings.graph_enabled:
        return None
    if settings.store_backend == "inmemory":
        return InMemoryGraphStore()
    if settings.store_backend == "sqlite":
        return SQLiteGraphStore(settings.sqlite_path)
    if settings.store_backend == "postgres":
        if not settings.postgres_dsn:
            raise ValueError(
                "BRAINSTEM_POSTGRES_DSN is required when BRAINSTEM_STORE_BACKEND=postgres"
            )
        return PostgresGraphStore(settings.postgres_dsn)
    raise ValueError(f"unsupported BRAINSTEM_STORE_BACKEND: {settings.store_backend}")


def create_app(
    repository: MemoryRepository | None = None,
    settings: Settings | None = None,
    auth_manager: AuthManager | None = None,
    model_registry: ModelRegistry | None = None,
) -> FastAPI:
    runtime_settings = settings if settings is not None else load_settings()
    repo = repository if repository is not None else _create_repository(runtime_settings)
    auth = auth_manager if auth_manager is not None else _create_auth_manager(runtime_settings)
    registry = model_registry if model_registry is not None else ModelRegistry()
    jobs = _create_job_manager(runtime_settings, repo, registry)
    graph_store = _create_graph_store(runtime_settings)
    graph_repository = (
        GraphAugmentedRepository(
            repository=repo,
            graph_store=graph_store,
            max_expansion=runtime_settings.graph_max_expansion,
        )
        if graph_store is not None
        else None
    )
    metrics = MetricsStore()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            jobs.close()
            if graph_store is not None:
                graph_store.close()

    app = FastAPI(
        title="Brainstem API",
        version="0.2.0",
        description="Shared memory coprocessor for multi-agent systems.",
        lifespan=lifespan,
    )

    def resolve_route_path(request: Request) -> str:
        route = request.scope.get("route")
        if route is not None and hasattr(route, "path"):
            return str(route.path)
        return request.url.path

    @app.middleware("http")
    async def observe_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start_perf = perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            status_code = 500
            metrics.record(
                RequestMetric(
                    method=request.method,
                    path=resolve_route_path(request),
                    status_code=status_code,
                    duration_ms=duration_ms(start_perf),
                )
            )
            raise

        metrics.record(
            RequestMetric(
                method=request.method,
                path=resolve_route_path(request),
                status_code=status_code,
                duration_ms=duration_ms(start_perf),
            )
        )
        return response

    async def get_auth_context(
        x_brainstem_api_key: Annotated[str | None, Header()] = None,
    ) -> AuthContext:
        return auth.authenticate(x_brainstem_api_key)

    def _registry_or_400(callable_fn, *args, **kwargs):
        try:
            return callable_fn(*args, **kwargs)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        response = repo.remember(payload)
        if graph_store is not None:
            for memory_id, item in zip(response.memory_ids, payload.items, strict=False):
                graph_store.project_memory(
                    tenant_id=payload.tenant_id,
                    memory_id=memory_id,
                    text=item.text,
                )
        return response

    @app.post("/v0/memory/recall", response_model=RecallResponse)
    async def recall(
        payload: RecallRequest,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> RecallResponse:
        auth_start = perf_counter()
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            minimum_role=AgentRole.READER,
        )
        auth_ms = duration_ms(auth_start)
        recall_start = perf_counter()
        response = (
            graph_repository.recall(payload)
            if graph_repository is not None
            else repo.recall(payload)
        )
        recall_ms = duration_ms(recall_start)
        model_version, model_route = registry.select_version("reranker", payload.tenant_id)
        response.model_version = model_version
        response.model_route = model_route

        metrics.record_pipeline_timing("recall.auth", auth_ms)
        metrics.record_pipeline_timing("recall.store", recall_ms)

        LOGGER.info(
            "recall_trace %s",
            json.dumps(
                {
                    "tenant_id": payload.tenant_id,
                    "agent_id": payload.agent_id,
                    "trace_id": response.trace_id,
                    "items": len(response.items),
                    "auth_ms": round(auth_ms, 2),
                    "store_ms": round(recall_ms, 2),
                },
                sort_keys=True,
            ),
        )
        return response

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
        job = jobs.submit_reflect(
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            window_hours=payload.window_hours,
            max_candidates=payload.max_candidates,
        )
        return ReflectResponse(
            job_id=job.job_id,
            status="queued",
            candidate_facts=[],
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
        job = jobs.submit_train(
            tenant_id=payload.tenant_id,
            agent_id=auth_context.agent_id,
            model_kind=payload.model_kind,
            lookback_days=payload.lookback_days,
        )
        return TrainResponse(
            job_id=job.job_id,
            status="queued",
            notes="Training job queued.",
        )

    @app.post("/v0/memory/cleanup", response_model=CleanupResponse)
    async def cleanup(
        payload: CleanupRequest,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> CleanupResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=auth_context.agent_id,
            minimum_role=AgentRole.ADMIN,
        )
        job = jobs.submit_cleanup(
            tenant_id=payload.tenant_id,
            agent_id=auth_context.agent_id,
            grace_hours=payload.grace_hours,
        )
        return CleanupResponse(
            job_id=job.job_id,
            status="queued",
            notes="Cleanup job queued.",
        )

    @app.get("/v0/jobs/dead_letters")
    async def dead_letters(
        tenant_id: str,
        agent_id: str,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict[str, object]:
        auth.authorize(
            context=auth_context,
            tenant_id=tenant_id,
            agent_id=agent_id,
            minimum_role=AgentRole.ADMIN,
        )
        jobs_list = jobs.list_dead_letters(tenant_id=tenant_id, limit=limit)
        return {
            "count": len(jobs_list),
            "items": [
                JobStatusResponse.model_validate(job.to_dict()).model_dump()
                for job in jobs_list
            ],
        }

    @app.get("/v0/jobs/{job_id}", response_model=JobStatusResponse)
    async def job_status(
        job_id: str,
        tenant_id: str,
        agent_id: str,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> JobStatusResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=tenant_id,
            agent_id=agent_id,
            minimum_role=AgentRole.READER,
        )
        job = jobs.get(job_id)
        if job is None or job.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="job_not_found")
        if auth_context.role is not AgentRole.ADMIN and job.agent_id != agent_id:
            raise HTTPException(status_code=403, detail="agent_mismatch")
        return JobStatusResponse.model_validate(job.to_dict())

    @app.get("/v0/models/{model_kind}", response_model=ModelRegistryStateResponse)
    async def model_state(
        model_kind: ModelKind,
        tenant_id: str,
        agent_id: str,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> ModelRegistryStateResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=tenant_id,
            agent_id=agent_id,
            minimum_role=AgentRole.ADMIN,
        )
        state = _registry_or_400(registry.get_state, model_kind.value)
        return ModelRegistryStateResponse.model_validate(state)

    @app.post(
        "/v0/models/{model_kind}/canary/register",
        response_model=ModelRegistryStateResponse,
    )
    async def register_model_canary(
        model_kind: ModelKind,
        payload: RegisterCanaryRequest,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> ModelRegistryStateResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            minimum_role=AgentRole.ADMIN,
        )
        state = _registry_or_400(
            registry.register_canary,
            model_kind.value,
            payload.version,
            payload.rollout_percent,
            payload.tenant_allowlist,
            payload.metadata,
        )
        return ModelRegistryStateResponse.model_validate(state)

    @app.post(
        "/v0/models/{model_kind}/canary/promote",
        response_model=ModelRegistryStateResponse,
    )
    async def promote_model_canary(
        model_kind: ModelKind,
        payload: PromoteCanaryRequest,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> ModelRegistryStateResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            minimum_role=AgentRole.ADMIN,
        )
        state = _registry_or_400(registry.promote_canary, model_kind.value)
        return ModelRegistryStateResponse.model_validate(state)

    @app.post(
        "/v0/models/{model_kind}/canary/rollback",
        response_model=ModelRegistryStateResponse,
    )
    async def rollback_model_canary(
        model_kind: ModelKind,
        payload: RollbackCanaryRequest,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> ModelRegistryStateResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            minimum_role=AgentRole.ADMIN,
        )
        state = _registry_or_400(registry.rollback_canary, model_kind.value)
        return ModelRegistryStateResponse.model_validate(state)

    @app.post("/v0/models/{model_kind}/signals", response_model=ModelRegistryStateResponse)
    async def record_model_signal(
        model_kind: ModelKind,
        payload: ModelSignalRequest,
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> ModelRegistryStateResponse:
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            minimum_role=AgentRole.ADMIN,
        )
        state = _registry_or_400(
            registry.record_signal,
            model_kind.value,
            payload.version,
            payload.metric,
            payload.value,
            payload.source,
        )
        return ModelRegistryStateResponse.model_validate(state)

    @app.get("/v0/meta")
    async def meta() -> dict[str, str]:
        return {
            "service": "brainstem",
            "mode": "v0",
            "store_backend": runtime_settings.store_backend,
            "auth_mode": runtime_settings.auth_mode,
            "graph_enabled": str(runtime_settings.graph_enabled).lower(),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    @app.get("/v0/metrics")
    async def metrics_snapshot(
        auth_context: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> dict[str, object]:
        if not auth_context.bypass and auth_context.role is not AgentRole.ADMIN:
            raise HTTPException(status_code=403, detail="insufficient_role")
        return {
            "service": "brainstem",
            "store_backend": runtime_settings.store_backend,
            "auth_mode": runtime_settings.auth_mode,
            "graph_enabled": runtime_settings.graph_enabled,
            "snapshot": metrics.snapshot(),
        }

    return app
