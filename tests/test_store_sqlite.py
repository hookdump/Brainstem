from __future__ import annotations

from pathlib import Path

from brainstem.models import RecallRequest, RememberRequest, Scope
from brainstem.store import SQLiteRepository


def _remember_payload(
    tenant_id: str = "t_sql",
    agent_id: str = "a_writer",
    scope: str = "team",
    idempotency_key: str | None = None,
) -> RememberRequest:
    return RememberRequest.model_validate(
        {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "scope": scope,
            "idempotency_key": idempotency_key,
            "items": [
                {
                    "type": "fact",
                    "text": "Migration must finish before April planning cycle.",
                    "trust_level": "trusted_tool",
                    "source_ref": "trace_sql_1",
                }
            ],
        }
    )


def test_sqlite_repository_persists_and_replays_idempotency(tmp_path: Path) -> None:
    db_path = tmp_path / "brainstem.db"

    repo1 = SQLiteRepository(str(db_path))
    response1 = repo1.remember(_remember_payload(idempotency_key="idem-sql-1"))
    memory_id = response1.memory_ids[0]
    repo1.close()

    repo2 = SQLiteRepository(str(db_path))
    replay = repo2.remember(_remember_payload(idempotency_key="idem-sql-1"))
    assert replay.memory_ids[0] == memory_id
    assert "idempotency_replay" in replay.warnings

    recall = repo2.recall(
        RecallRequest.model_validate(
            {
                "tenant_id": "t_sql",
                "agent_id": "a_writer",
                "scope": "team",
                "query": "migration constraints",
            }
        )
    )
    assert len(recall.items) >= 1
    assert recall.items[0].memory_id == memory_id

    details = repo2.inspect(
        tenant_id="t_sql",
        agent_id="a_writer",
        scope=Scope.TEAM,
        memory_id=memory_id,
    )
    assert details is not None
    assert details.memory_id == memory_id

    deleted = repo2.forget(tenant_id="t_sql", agent_id="a_writer", memory_id=memory_id)
    assert deleted.deleted is True
    assert (
        repo2.inspect(
            tenant_id="t_sql",
            agent_id="a_writer",
            scope=Scope.TEAM,
            memory_id=memory_id,
        )
        is None
    )
    repo2.close()


def test_sqlite_private_scope_isolation(tmp_path: Path) -> None:
    db_path = tmp_path / "brainstem-private.db"
    repo = SQLiteRepository(str(db_path))
    response = repo.remember(_remember_payload(scope="private"))
    memory_id = response.memory_ids[0]

    private_owner_read = repo.inspect(
        tenant_id="t_sql",
        agent_id="a_writer",
        scope=Scope.PRIVATE,
        memory_id=memory_id,
    )
    assert private_owner_read is not None

    cross_agent_read = repo.inspect(
        tenant_id="t_sql",
        agent_id="a_other",
        scope=Scope.GLOBAL,
        memory_id=memory_id,
    )
    assert cross_agent_read is None

    cross_agent_delete = repo.forget(
        tenant_id="t_sql",
        agent_id="a_other",
        memory_id=memory_id,
    )
    assert cross_agent_delete.deleted is False
    repo.close()
