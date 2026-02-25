"""Background job queue for async Brainstem tasks."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from queue import Empty, Queue
from threading import Event, RLock, Thread
from typing import Any
from uuid import uuid4

from brainstem.model_registry import ModelRegistry
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
    attempts: int = 0
    max_attempts: int = 1

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
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
        }


class JobManager:
    def __init__(
        self,
        repository: MemoryRepository,
        default_max_attempts: int = 3,
        sqlite_path: str | None = None,
        start_worker: bool = True,
        poll_interval_s: float = 0.2,
        model_registry: ModelRegistry | None = None,
    ) -> None:
        self._repository = repository
        self._default_max_attempts = max(1, default_max_attempts)
        self._sqlite_path = sqlite_path
        self._poll_interval_s = max(0.05, poll_interval_s)
        self._model_registry = model_registry
        self._lock = RLock()
        self._stop_event = Event()
        self._queue: Queue[str] = Queue()
        self._jobs: dict[str, JobRecord] = {}
        self._dead_letters: list[str] = []

        if self._sqlite_path is not None:
            self._init_sqlite_schema()

        self._worker: Thread | None = None
        if start_worker:
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
        max_attempts: int | None = None,
    ) -> JobRecord:
        job = JobRecord(
            job_id=f"job_{uuid4().hex[:10]}",
            kind=kind,
            tenant_id=tenant_id,
            agent_id=agent_id,
            status=JobStatus.QUEUED,
            created_at=datetime.now(UTC),
            payload=payload,
            max_attempts=(
                self._default_max_attempts if max_attempts is None else max(1, max_attempts)
            ),
        )

        if self._sqlite_path is not None:
            self._insert_sqlite_job(job)
            return job

        with self._lock:
            self._jobs[job.job_id] = job
        self._queue.put(job.job_id)
        return job

    def get(self, job_id: str) -> JobRecord | None:
        if self._sqlite_path is not None:
            return self._get_sqlite_job(job_id)
        with self._lock:
            return self._jobs.get(job_id)

    def list_dead_letters(self, tenant_id: str, limit: int = 50) -> list[JobRecord]:
        bounded = max(1, limit)
        if self._sqlite_path is not None:
            return self._list_sqlite_dead_letters(tenant_id=tenant_id, limit=bounded)

        with self._lock:
            records = [
                self._jobs[job_id]
                for job_id in self._dead_letters
                if job_id in self._jobs and self._jobs[job_id].tenant_id == tenant_id
            ]
        records.sort(key=lambda record: record.finished_at or record.created_at, reverse=True)
        return records[:bounded]

    def process_next(self) -> bool:
        if self._sqlite_path is not None:
            claimed = self._claim_next_sqlite_job()
            if claimed is None:
                return False
            self._execute_sqlite(claimed)
            return True

        try:
            job_id = self._queue.get(timeout=0.0)
        except Empty:
            return False

        self._execute_inmemory(job_id)
        self._queue.task_done()
        return True

    def run_forever(self) -> None:
        while not self._stop_event.is_set():
            processed = self.process_next()
            if not processed:
                self._stop_event.wait(self._poll_interval_s)

    def close(self) -> None:
        self._stop_event.set()
        if self._worker is not None:
            self._worker.join(timeout=1.0)

    def _run(self) -> None:
        self.run_forever()

    def _execute_inmemory(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(UTC)
            job.attempts += 1

        try:
            result = self._execute_job(job)
            with self._lock:
                job.status = JobStatus.COMPLETED
                job.finished_at = datetime.now(UTC)
                job.result = result
                job.error = None
        except Exception as exc:  # pragma: no cover - defensive guard
            with self._lock:
                job.error = str(exc)
                if job.attempts < job.max_attempts:
                    job.status = JobStatus.QUEUED
                    self._queue.put(job.job_id)
                else:
                    job.status = JobStatus.FAILED
                    job.finished_at = datetime.now(UTC)
                    self._dead_letters.append(job.job_id)

    def _execute_sqlite(self, job: JobRecord) -> None:
        try:
            result = self._execute_job(job)
            self._update_sqlite_job_success(job_id=job.job_id, result=result)
        except Exception as exc:  # pragma: no cover - defensive guard
            self._update_sqlite_job_failure(job=job, error=str(exc))

    def _execute_job(self, job: JobRecord) -> dict[str, Any]:
        if job.kind is JobKind.REFLECT:
            max_candidates = int(job.payload["max_candidates"])
            model_version = None
            model_route = None
            if self._model_registry is not None:
                model_version, model_route = self._model_registry.select_version(
                    model_kind="reranker",
                    tenant_id=job.tenant_id,
                )
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
            return {
                "candidate_facts": candidates,
                "model_version": model_version,
                "model_route": model_route,
            }

        if job.kind is JobKind.TRAIN:
            model_kind = str(job.payload["model_kind"])
            lookback_days = int(job.payload["lookback_days"])
            canary_version = (
                f"{model_kind}-canary-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-"
                f"{uuid4().hex[:6]}"
            )
            if self._model_registry is not None:
                self._model_registry.register_canary(
                    model_kind=model_kind,
                    version=canary_version,
                    rollout_percent=10,
                    actor_agent_id=job.agent_id,
                )
            return {
                "notes": (
                    f"Simulated {model_kind} training for tenant {job.tenant_id} "
                    f"with {lookback_days} day lookback."
                ),
                "candidate_version": canary_version,
            }

        if job.kind is JobKind.CLEANUP:
            grace_hours = int(job.payload["grace_hours"])
            purged = self._repository.purge_expired(
                tenant_id=job.tenant_id,
                grace_hours=grace_hours,
            )
            return {"purged_count": purged, "grace_hours": grace_hours}

        raise ValueError(f"Unsupported job kind: {job.kind}")

    def _init_sqlite_schema(self) -> None:
        with self._sqlite_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS async_jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    payload TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    attempts INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL
                );
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_async_jobs_status_created
                ON async_jobs (status, created_at);
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_async_jobs_tenant_status
                ON async_jobs (tenant_id, status);
                """
            )

    def _sqlite_connection(self) -> sqlite3.Connection:
        assert self._sqlite_path is not None
        db_path = Path(self._sqlite_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(db_path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _insert_sqlite_job(self, job: JobRecord) -> None:
        with self._sqlite_connection() as connection:
            connection.execute(
                """
                INSERT INTO async_jobs (
                    job_id, kind, tenant_id, agent_id, status, created_at, started_at,
                    finished_at, payload, result, error, attempts, max_attempts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    job.job_id,
                    job.kind.value,
                    job.tenant_id,
                    job.agent_id,
                    job.status.value,
                    job.created_at.isoformat(),
                    None,
                    None,
                    json.dumps(job.payload),
                    None,
                    None,
                    job.attempts,
                    job.max_attempts,
                ),
            )

    def _get_sqlite_job(self, job_id: str) -> JobRecord | None:
        with self._sqlite_connection() as connection:
            row = connection.execute(
                "SELECT * FROM async_jobs WHERE job_id = ?;",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return self._job_from_row(row)

    def _list_sqlite_dead_letters(self, tenant_id: str, limit: int) -> list[JobRecord]:
        with self._sqlite_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM async_jobs
                WHERE tenant_id = ? AND status = ?
                ORDER BY COALESCE(finished_at, created_at) DESC
                LIMIT ?;
                """,
                (tenant_id, JobStatus.FAILED.value, limit),
            ).fetchall()
        return [self._job_from_row(row) for row in rows]

    def _claim_next_sqlite_job(self) -> JobRecord | None:
        connection = self._sqlite_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE;")
            row = cursor.execute(
                """
                SELECT * FROM async_jobs
                WHERE status = ?
                ORDER BY created_at
                LIMIT 1;
                """,
                (JobStatus.QUEUED.value,),
            ).fetchone()
            if row is None:
                cursor.execute("COMMIT;")
                return None

            started_at = datetime.now(UTC).isoformat()
            cursor.execute(
                """
                UPDATE async_jobs
                SET status = ?, started_at = ?, attempts = attempts + 1
                WHERE job_id = ? AND status = ?;
                """,
                (
                    JobStatus.RUNNING.value,
                    started_at,
                    row["job_id"],
                    JobStatus.QUEUED.value,
                ),
            )
            if cursor.rowcount != 1:
                cursor.execute("ROLLBACK;")
                return None

            claimed = cursor.execute(
                "SELECT * FROM async_jobs WHERE job_id = ?;",
                (row["job_id"],),
            ).fetchone()
            cursor.execute("COMMIT;")
            if claimed is None:
                return None
            return self._job_from_row(claimed)
        finally:
            connection.close()

    def _update_sqlite_job_success(self, job_id: str, result: dict[str, Any]) -> None:
        with self._sqlite_connection() as connection:
            connection.execute(
                """
                UPDATE async_jobs
                SET status = ?, finished_at = ?, result = ?, error = NULL
                WHERE job_id = ?;
                """,
                (
                    JobStatus.COMPLETED.value,
                    datetime.now(UTC).isoformat(),
                    json.dumps(result),
                    job_id,
                ),
            )

    def _update_sqlite_job_failure(self, job: JobRecord, error: str) -> None:
        if job.attempts < job.max_attempts:
            with self._sqlite_connection() as connection:
                connection.execute(
                    """
                    UPDATE async_jobs
                    SET status = ?, error = ?, finished_at = NULL
                    WHERE job_id = ?;
                    """,
                    (
                        JobStatus.QUEUED.value,
                        error,
                        job.job_id,
                    ),
                )
            return

        with self._sqlite_connection() as connection:
            connection.execute(
                """
                UPDATE async_jobs
                SET status = ?, error = ?, finished_at = ?
                WHERE job_id = ?;
                """,
                (
                    JobStatus.FAILED.value,
                    error,
                    datetime.now(UTC).isoformat(),
                    job.job_id,
                ),
            )

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> JobRecord:
        payload_raw = row["payload"]
        result_raw = row["result"]
        payload = json.loads(payload_raw) if isinstance(payload_raw, str) else {}
        result = json.loads(result_raw) if isinstance(result_raw, str) else None
        return JobRecord(
            job_id=str(row["job_id"]),
            kind=JobKind(str(row["kind"])),
            tenant_id=str(row["tenant_id"]),
            agent_id=str(row["agent_id"]),
            status=JobStatus(str(row["status"])),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            started_at=(
                datetime.fromisoformat(str(row["started_at"]))
                if row["started_at"] is not None
                else None
            ),
            finished_at=(
                datetime.fromisoformat(str(row["finished_at"]))
                if row["finished_at"] is not None
                else None
            ),
            payload=payload if isinstance(payload, dict) else {},
            result=result if isinstance(result, dict) else None,
            error=str(row["error"]) if row["error"] is not None else None,
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
        )
