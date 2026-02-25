from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from brainstem.models import RecallRequest, RememberRequest, Scope
from brainstem.store_postgres import PostgresRepository

pytestmark = pytest.mark.skipif(
    not os.getenv("BRAINSTEM_TEST_POSTGRES_DSN"),
    reason="BRAINSTEM_TEST_POSTGRES_DSN is not set",
)


def test_postgres_repository_end_to_end() -> None:
    dsn = os.environ["BRAINSTEM_TEST_POSTGRES_DSN"]
    repository = PostgresRepository(dsn)

    tenant_id = f"t_pg_{uuid4().hex[:8]}"
    agent_id = "a_pg"
    remember_payload = RememberRequest.model_validate(
        {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "scope": "team",
            "idempotency_key": "idem-1",
            "items": [
                {
                    "type": "fact",
                    "text": "Postgres memory must persist across calls.",
                    "trust_level": "trusted_tool",
                }
            ],
        }
    )
    first = repository.remember(remember_payload)
    replay = repository.remember(remember_payload)
    assert "idempotency_replay" in replay.warnings
    memory_id = first.memory_ids[0]

    recall = repository.recall(
        RecallRequest.model_validate(
            {
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "scope": "team",
                "query": "What postgres memory exists?",
            }
        )
    )
    assert len(recall.items) >= 1

    details = repository.inspect(
        tenant_id=tenant_id,
        agent_id=agent_id,
        scope=Scope.TEAM,
        memory_id=memory_id,
    )
    assert details is not None

    expired = repository.remember(
        RememberRequest.model_validate(
            {
                "tenant_id": tenant_id,
                "agent_id": agent_id,
                "scope": "team",
                "items": [
                    {
                        "type": "fact",
                        "text": "Expired postgres memory item.",
                        "expires_at": (datetime.now(UTC) - timedelta(hours=2)).isoformat(),
                    }
                ],
            }
        )
    )
    purged_count = repository.purge_expired(tenant_id=tenant_id, grace_hours=0)
    assert purged_count >= 1
    delete_result = repository.forget(
        tenant_id=tenant_id,
        agent_id=agent_id,
        memory_id=expired.memory_ids[0],
    )
    assert delete_result.deleted is False

    repository.close()
