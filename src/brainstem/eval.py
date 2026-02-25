"""Evaluation helpers for memory retrieval quality."""

from __future__ import annotations

import math
from statistics import mean
from typing import TypedDict

from brainstem.models import RecallRequest, Scope
from brainstem.store import MemoryRepository


class EvalCase(TypedDict):
    name: str
    query: str
    expected_ids: list[str]


def recall_at_k(found_ids: list[str], expected_ids: list[str], k: int) -> float:
    top_k = set(found_ids[:k])
    expected = set(expected_ids)
    if not expected:
        return 1.0
    return 1.0 if top_k.intersection(expected) else 0.0


def ndcg_at_k(found_ids: list[str], expected_ids: list[str], k: int) -> float:
    expected = set(expected_ids)
    if not expected:
        return 1.0

    dcg = 0.0
    for index, memory_id in enumerate(found_ids[:k]):
        rel = 1.0 if memory_id in expected else 0.0
        if rel > 0.0:
            dcg += rel / math.log2(index + 2.0)

    ideal_hits = min(len(expected), k)
    idcg = sum(1.0 / math.log2(index + 2.0) for index in range(ideal_hits))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def run_retrieval_eval(
    repository: MemoryRepository,
    tenant_id: str,
    agent_id: str,
    cases: list[EvalCase],
    k: int = 5,
) -> dict[str, float]:
    recalls: list[float] = []
    ndcgs: list[float] = []
    tokens: list[float] = []

    for case in cases:
        response = repository.recall(
            RecallRequest.model_validate(
                {
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "scope": Scope.GLOBAL,
                    "query": case["query"],
                    "budget": {"max_items": k, "max_tokens": 4000},
                }
            )
        )
        found_ids = [item.memory_id for item in response.items]
        recalls.append(recall_at_k(found_ids, case["expected_ids"], k))
        ndcgs.append(ndcg_at_k(found_ids, case["expected_ids"], k))
        tokens.append(float(response.composed_tokens_estimate))

    return {
        "cases": float(len(cases)),
        f"recall@{k}": mean(recalls) if recalls else 0.0,
        f"ndcg@{k}": mean(ndcgs) if ndcgs else 0.0,
        "avg_composed_tokens": mean(tokens) if tokens else 0.0,
    }
