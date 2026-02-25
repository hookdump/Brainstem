from __future__ import annotations

from brainstem.compaction import compact_context
from brainstem.models import CompactRequest, MemoryType, RecallRequest, RememberRequest, Scope
from brainstem.store import InMemoryRepository


def test_compact_context_creates_summary_memory() -> None:
    repository = InMemoryRepository()
    repository.remember(
        RememberRequest.model_validate(
            {
                "tenant_id": "t_compact",
                "agent_id": "a_writer",
                "scope": "team",
                "items": [
                    {
                        "type": "fact",
                        "text": "Migration runbook must be finalized before release review.",
                    },
                    {
                        "type": "event",
                        "text": "SRE team reported staging instability during deploy rehearsal.",
                    },
                    {
                        "type": "policy",
                        "text": "Security sign-off is required before production rollout.",
                    },
                ],
            }
        )
    )

    response = compact_context(
        repository=repository,
        payload=CompactRequest.model_validate(
            {
                "tenant_id": "t_compact",
                "agent_id": "a_writer",
                "scope": "team",
                "query": "Summarize deployment readiness constraints.",
                "max_source_items": 10,
                "input_max_tokens": 3000,
                "target_tokens": 220,
                "output_type": "episode",
            }
        ),
    )

    assert response.created_memory_id is not None
    assert response.source_count >= 1
    assert response.input_tokens_estimate > 0
    assert response.output_tokens_estimate > 0
    assert response.reduction_ratio >= 0.0
    assert response.summary_text.startswith("Compacted context for query")

    details = repository.inspect(
        tenant_id="t_compact",
        agent_id="a_writer",
        scope=Scope.TEAM,
        memory_id=response.created_memory_id,
    )
    assert details is not None
    assert details.type is MemoryType.EPISODE

    recall = repository.recall(
        RecallRequest.model_validate(
            {
                "tenant_id": "t_compact",
                "agent_id": "a_writer",
                "scope": "team",
                "query": "deployment readiness summary",
                "budget": {"max_items": 20, "max_tokens": 4000},
            }
        )
    )
    assert any(item.memory_id == response.created_memory_id for item in recall.items)


def test_compact_context_returns_warning_when_no_source_memories() -> None:
    repository = InMemoryRepository()
    response = compact_context(
        repository=repository,
        payload=CompactRequest.model_validate(
            {
                "tenant_id": "t_compact",
                "agent_id": "a_writer",
                "scope": "team",
                "query": "No memory exists yet.",
            }
        ),
    )

    assert response.created_memory_id is None
    assert response.source_count == 0
    assert "no_source_memories" in response.warnings
