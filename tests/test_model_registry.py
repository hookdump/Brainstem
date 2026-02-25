from __future__ import annotations

import time

from brainstem.jobs import JobManager, JobStatus
from brainstem.model_registry import ModelRegistry
from brainstem.store import InMemoryRepository


def test_model_registry_rollout_selection_and_allowlist() -> None:
    registry = ModelRegistry()
    registry.register_canary(
        model_kind="reranker",
        version="reranker-canary-v2",
        rollout_percent=0,
        tenant_allowlist=["tenant_canary"],
    )

    version_allowlisted, route_allowlisted = registry.select_version("reranker", "tenant_canary")
    assert version_allowlisted == "reranker-canary-v2"
    assert route_allowlisted == "canary_allowlist"

    version_default, route_default = registry.select_version("reranker", "tenant_default")
    assert version_default == "reranker-baseline-v1"
    assert route_default == "active"


def test_model_registry_promote_and_rollback() -> None:
    registry = ModelRegistry()
    state = registry.register_canary(
        model_kind="salience",
        version="salience-canary-v2",
        rollout_percent=100,
    )
    assert state["canary_version"] == "salience-canary-v2"

    promoted = registry.promote_canary("salience")
    assert promoted["active_version"] == "salience-canary-v2"
    assert promoted["canary_version"] is None

    rollback = registry.rollback_canary("salience")
    assert rollback["canary_version"] is None
    assert rollback["rollout_percent"] == 0


def test_train_job_registers_canary_version() -> None:
    registry = ModelRegistry()
    manager = JobManager(
        repository=InMemoryRepository(),
        model_registry=registry,
    )
    try:
        job = manager.submit_train(
            tenant_id="t_registry",
            agent_id="a_admin",
            model_kind="reranker",
            lookback_days=7,
        )

        end = time.time() + 2.0
        while time.time() < end:
            status = manager.get(job.job_id)
            if status is not None and status.status is JobStatus.COMPLETED:
                break
            time.sleep(0.02)

        status = manager.get(job.job_id)
        assert status is not None
        assert status.status is JobStatus.COMPLETED
        assert status.result is not None
        candidate_version = str(status.result["candidate_version"])
        state = registry.get_state("reranker")
        assert state["canary_version"] == candidate_version
    finally:
        manager.close()
