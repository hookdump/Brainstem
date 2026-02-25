from __future__ import annotations

from pathlib import Path

from brainstem.jobs import JobManager, JobStatus
from brainstem.store import InMemoryRepository


class FailingCleanupRepository(InMemoryRepository):
    def __init__(self, fail_times: int) -> None:
        super().__init__()
        self.fail_times = fail_times
        self.calls = 0

    def purge_expired(self, tenant_id: str, grace_hours: int = 0) -> int:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("cleanup failed")
        return super().purge_expired(tenant_id=tenant_id, grace_hours=grace_hours)


def test_sqlite_job_queue_processes_across_manager_instances(tmp_path: Path) -> None:
    queue_db = tmp_path / "jobs.db"
    repository = InMemoryRepository()
    producer = JobManager(repository=repository, sqlite_path=str(queue_db), start_worker=False)
    worker = JobManager(repository=repository, sqlite_path=str(queue_db), start_worker=False)
    try:
        job = producer.submit_train(
            tenant_id="t_jobs",
            agent_id="a_admin",
            model_kind="reranker",
            lookback_days=7,
        )
        processed = worker.process_next()
        assert processed is True

        updated = producer.get(job.job_id)
        assert updated is not None
        assert updated.status is JobStatus.COMPLETED
        assert updated.attempts == 1
    finally:
        producer.close()
        worker.close()


def test_sqlite_job_queue_persists_retries_and_dead_letters(tmp_path: Path) -> None:
    queue_db = tmp_path / "jobs.db"
    repository = FailingCleanupRepository(fail_times=5)
    producer = JobManager(
        repository=repository,
        default_max_attempts=2,
        sqlite_path=str(queue_db),
        start_worker=False,
    )
    worker_one = JobManager(
        repository=repository,
        default_max_attempts=2,
        sqlite_path=str(queue_db),
        start_worker=False,
    )
    worker_two = JobManager(
        repository=repository,
        default_max_attempts=2,
        sqlite_path=str(queue_db),
        start_worker=False,
    )
    try:
        job = producer.submit_cleanup(
            tenant_id="t_jobs",
            agent_id="a_admin",
            grace_hours=0,
        )

        assert worker_one.process_next() is True
        queued = producer.get(job.job_id)
        assert queued is not None
        assert queued.status is JobStatus.QUEUED
        assert queued.attempts == 1

        assert worker_two.process_next() is True
        failed = producer.get(job.job_id)
        assert failed is not None
        assert failed.status is JobStatus.FAILED
        assert failed.attempts == 2

        dead = producer.list_dead_letters(tenant_id="t_jobs", limit=10)
        assert len(dead) == 1
        assert dead[0].job_id == job.job_id
    finally:
        producer.close()
        worker_one.close()
        worker_two.close()
