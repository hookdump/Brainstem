from __future__ import annotations

from brainstem.eval import ndcg_at_k, recall_at_k, run_retrieval_eval
from brainstem.models import RememberRequest
from brainstem.store import InMemoryRepository


def test_recall_and_ndcg_primitives() -> None:
    found = ["a", "b", "c"]
    expected = ["c"]
    assert recall_at_k(found, expected, k=2) == 0.0
    assert recall_at_k(found, expected, k=3) == 1.0
    assert 0.0 < ndcg_at_k(found, expected, k=3) <= 1.0


def test_run_retrieval_eval() -> None:
    repository = InMemoryRepository()
    response = repository.remember(
        RememberRequest.model_validate(
            {
                "tenant_id": "t_eval",
                "agent_id": "a_eval",
                "scope": "team",
                "items": [
                    {
                        "type": "fact",
                        "text": "Deployment migration must finish before April planning cycle.",
                        "trust_level": "trusted_tool",
                    }
                ],
            }
        )
    )
    memory_id = response.memory_ids[0]
    metrics = run_retrieval_eval(
        repository=repository,
        tenant_id="t_eval",
        agent_id="a_eval",
        cases=[
            {
                "name": "migration",
                "query": "What migration deadline exists?",
                "expected_ids": [memory_id],
            }
        ],
        k=5,
    )
    assert metrics["cases"] == 1.0
    assert metrics["recall@5"] == 1.0
    assert metrics["ndcg@5"] > 0.0
