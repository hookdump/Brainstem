"""Background job queue for async Brainstem tasks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from queue import Empty, Queue
from threading import Event, RLock, Thread
from typing import Any
from uuid import uuid4

from brainstem.models import RecallRequest, Scope
from brainstem.store import MemoryRepository


class JobKind(StrEnum):
    REFLECT = "reflect"
    TRAIN = "train"
    CLEANUP = "cleanup"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class JobRecord:
    job_id: str
    kind: JobKind
    tenant_id: str
    agent_id: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind.value,
            "tenant_id": self.tenant_id,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository
        self._lock = RLock()
        self._stop_event = Event()
        self._queue: Queue[str] = Queue()
        self._jobs: dict[str, JobRecord] = {}
        self._worker = Thread(target=self._run, daemon=True)
        self._worker.start()

    def submit_reflect(
        self, tenant_id: str, agent_id: str, window_hours: int, max_candidates: int
    ) -> JobRecord:
        return self._enqueue(
            kind=JobKind.REFLECT,
            tenant_id=tenant_id,
            agent_id=agent_id,
            payload={
                "window_hours": window_hours,
                "max_candidates": max_candidates,
            },
        )

    def submit_train(
        self, tenant_id: str, agent_id: str, model_kind: str, lookback_days: int
    ) -> JobRecord:
        return self._enqueue(
            kind=JobKind.TRAIN,
            tenant_id=tenant_id,
            agent_id=agent_id,
            payload={
                "model_kind": model_kind,
                "lookback_days": lookback_days,
            },
        )

    def submit_cleanup(self, tenant_id: str, agent_id: str, grace_hours: int) -> JobRecord:
        return self._enqueue(
            kind=JobKind.CLEANUP,
            tenant_id=tenant_id,
            agent_id=agent_id,
            payload={"grace_hours": grace_hours},
        )

    def _enqueue(
        self,
        kind: JobKind,
        tenant_id: str,
        agent_id: str,
        payload: dict[str, Any],
    ) -> JobRecord:
        job = JobRecord(
            job_id=f"job_{uuid4().hex[:10]}",
            kind=kind,
            tenant_id=tenant_id,
            agent_id=agent_id,
            status=JobStatus.QUEUED,
            created_at=datetime.now(UTC),
            payload=payload,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        self._queue.put(job.job_id)
        return job

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def close(self) -> None:
        self._stop_event.set()
        self._worker.join(timeout=1.0)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                job_id = self._queue.get(timeout=0.2)
            except Empty:
                continue
            self._execute(job_id)
            self._queue.task_done()

    def _execute(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(UTC)

        try:
            result = self._execute_job(job)
            with self._lock:
                job.status = JobStatus.COMPLETED
                job.finished_at = datetime.now(UTC)
                job.result = result
        except Exception as exc:  # pragma: no cover - defensive guard
            with self._lock:
                job.status = JobStatus.FAILED
                job.finished_at = datetime.now(UTC)
                job.error = str(exc)

    def _execute_job(self, job: JobRecord) -> dict[str, Any]:
        if job.kind is JobKind.REFLECT:
            max_candidates = int(job.payload["max_candidates"])
            recent = self._repository.recall(
                RecallRequest.model_validate(
                    {
                        "tenant_id": job.tenant_id,
                        "agent_id": job.agent_id,
                        "scope": Scope.GLOBAL,
                        "query": "constraints commitments unresolved tasks deadlines",
                    }
                )
            )
            candidates = [
                f"[candidate_fact] {item.text}" for item in recent.items[:max_candidates]
            ]
            return {"candidate_facts": candidates}

        if job.kind is JobKind.TRAIN:
            model_kind = str(job.payload["model_kind"])
            lookback_days = int(job.payload["lookback_days"])
            return {
                "notes": (
                    f"Simulated {model_kind} training for tenant {job.tenant_id} "
                    f"with {lookback_days} day lookback."
                )
            }

        if job.kind is JobKind.CLEANUP:
            grace_hours = int(job.payload["grace_hours"])
            purged = self._repository.purge_expired(
                tenant_id=job.tenant_id,
                grace_hours=grace_hours,
            )
            return {"purged_count": purged, "grace_hours": grace_hours}

        raise ValueError(f"Unsupported job kind: {job.kind}")
