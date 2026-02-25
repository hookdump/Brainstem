"""HTTP API for Brainstem v0."""

import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from starlette.responses import Response

from brainstem.auth import AgentRole, AuthContext, AuthManager
from brainstem.jobs import JobManager
from brainstem.models import (
    ForgetRequest,
    ForgetResponse,
    JobStatusResponse,
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


def create_app(
    repository: MemoryRepository | None = None,
    settings: Settings | None = None,
    auth_manager: AuthManager | None = None,
) -> FastAPI:
    runtime_settings = settings if settings is not None else load_settings()
    repo = repository if repository is not None else _create_repository(runtime_settings)
    auth = auth_manager if auth_manager is not None else _create_auth_manager(runtime_settings)
    jobs = JobManager(repo)
    metrics = MetricsStore()

    app = FastAPI(
        title="Brainstem API",
        version="0.2.0",
        description="Shared memory coprocessor for multi-agent systems.",
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
        auth_start = perf_counter()
        auth.authorize(
            context=auth_context,
            tenant_id=payload.tenant_id,
            agent_id=payload.agent_id,
            minimum_role=AgentRole.READER,
        )
        auth_ms = duration_ms(auth_start)
        recall_start = perf_counter()
        response = repo.recall(payload)
        recall_ms = duration_ms(recall_start)

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

    @app.get("/v0/meta")
    async def meta() -> dict[str, str]:
        return {
            "service": "brainstem",
            "mode": "v0",
            "store_backend": runtime_settings.store_backend,
            "auth_mode": runtime_settings.auth_mode,
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
            "snapshot": metrics.snapshot(),
        }

    return app
