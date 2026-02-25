from __future__ import annotations

import time

from brainstem.jobs import JobManager, JobStatus
from brainstem.models import RecallResponse
from brainstem.store import InMemoryRepository


class FlakyRepository(InMemoryRepository):
    def __init__(self, fail_times: int) -> None:
        super().__init__()
        self.fail_times = fail_times
        self.calls = 0

    def recall(self, payload):  # type: ignore[override]
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient failure")
        return RecallResponse.model_validate(
            {
                "items": [],
                "composed_tokens_estimate": 0,
                "conflicts": [],
                "trace_id": "rec_test",
            }
        )


def _wait(manager: JobManager, job_id: str, timeout_s: float = 2.0):
    end = time.time() + timeout_s
    while time.time() < end:
        job = manager.get(job_id)
        if job is not None and job.status in {JobStatus.COMPLETED, JobStatus.FAILED}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not reach terminal state")


def test_job_retries_then_completes() -> None:
    repository = FlakyRepository(fail_times=2)
    manager = JobManager(repository=repository, default_max_attempts=3)
    try:
        job = manager.submit_reflect(
            tenant_id="t_jobs",
            agent_id="a_jobs",
            window_hours=24,
            max_candidates=4,
        )
        terminal = _wait(manager, job.job_id)
        assert terminal.status is JobStatus.COMPLETED
        assert terminal.attempts == 3
    finally:
        manager.close()


def test_job_dead_letter_after_retry_exhaustion() -> None:
    repository = FlakyRepository(fail_times=5)
    manager = JobManager(repository=repository, default_max_attempts=2)
    try:
        job = manager.submit_reflect(
            tenant_id="t_jobs",
            agent_id="a_jobs",
            window_hours=24,
            max_candidates=4,
        )
        terminal = _wait(manager, job.job_id)
        assert terminal.status is JobStatus.FAILED
        assert terminal.attempts == 2
        dead = manager.list_dead_letters(tenant_id="t_jobs", limit=10)
        assert len(dead) == 1
        assert dead[0].job_id == job.job_id
    finally:
        manager.close()
