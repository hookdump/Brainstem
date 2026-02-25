"""Evaluation helpers for memory retrieval quality."""

from __future__ import annotations

import math
from statistics import mean
from typing import Protocol, TypedDict

from brainstem.models import RecallRequest, RecallResponse, Scope


class RecallRepository(Protocol):
    def recall(self, payload: RecallRequest) -> RecallResponse: ...


class EvalCase(TypedDict):
    name: str
    query: str
    expected_ids: list[str]


class EvalResult(TypedDict):
    name: str
    query: str
    expected_ids: list[str]
    found_ids: list[str]
    recall: float
    ndcg: float
    composed_tokens: float


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
    repository: RecallRepository,
    tenant_id: str,
    agent_id: str,
    cases: list[EvalCase],
    k: int = 5,
) -> dict[str, float]:
    metrics, _ = run_retrieval_eval_detailed(
        repository=repository,
        tenant_id=tenant_id,
        agent_id=agent_id,
        cases=cases,
        k=k,
    )
    return metrics


def run_retrieval_eval_detailed(
    repository: RecallRepository,
    tenant_id: str,
    agent_id: str,
    cases: list[EvalCase],
    k: int = 5,
) -> tuple[dict[str, float], list[EvalResult]]:
    recalls: list[float] = []
    ndcgs: list[float] = []
    tokens: list[float] = []
    results: list[EvalResult] = []

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
        case_recall = recall_at_k(found_ids, case["expected_ids"], k)
        case_ndcg = ndcg_at_k(found_ids, case["expected_ids"], k)
        case_tokens = float(response.composed_tokens_estimate)
        recalls.append(case_recall)
        ndcgs.append(case_ndcg)
        tokens.append(case_tokens)
        results.append(
            EvalResult(
                name=case["name"],
                query=case["query"],
                expected_ids=case["expected_ids"],
                found_ids=found_ids,
                recall=case_recall,
                ndcg=case_ndcg,
                composed_tokens=case_tokens,
            )
        )

    metrics = {
        "cases": float(len(cases)),
        f"recall@{k}": mean(recalls) if recalls else 0.0,
        f"ndcg@{k}": mean(ndcgs) if ndcgs else 0.0,
        "avg_composed_tokens": mean(tokens) if tokens else 0.0,
    }
    return metrics, results
