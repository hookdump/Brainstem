"""Benchmark dataset loading and execution utilities."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any, NotRequired, TypedDict

from brainstem.eval import EvalCase, run_retrieval_eval_detailed
from brainstem.graph import (
    DEFAULT_RELATION_WEIGHTS,
    GraphAugmentedRepository,
    InMemoryGraphStore,
    SQLiteGraphStore,
)
from brainstem.models import RememberRequest
from brainstem.store import InMemoryRepository, MemoryRepository, SQLiteRepository


class SeedItem(TypedDict):
    id: str
    type: str
    text: str
    scope: str
    trust_level: str


class DatasetCase(TypedDict):
    name: str
    query: str
    expected_seed_ids: list[str]
    tags: NotRequired[list[str]]


class BenchmarkDataset(TypedDict):
    tenant_id: str
    agent_id: str
    seeds: list[SeedItem]
    cases: list[DatasetCase]


def load_benchmark_dataset(path: str) -> BenchmarkDataset:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Dataset JSON must be an object.")
    for key in ("tenant_id", "agent_id", "seeds", "cases"):
        if key not in payload:
            raise ValueError(f"Dataset JSON missing required key: {key}")

    seeds: list[SeedItem] = []
    for seed in payload["seeds"]:
        if not isinstance(seed, dict):
            raise ValueError("Dataset `seeds` entries must be objects.")
        seeds.append(
            SeedItem(
                id=str(seed["id"]),
                type=str(seed["type"]),
                text=str(seed["text"]),
                scope=str(seed["scope"]),
                trust_level=str(seed["trust_level"]),
            )
        )

    cases: list[DatasetCase] = []
    for case in payload["cases"]:
        if not isinstance(case, dict):
            raise ValueError("Dataset `cases` entries must be objects.")
        parsed_case = DatasetCase(
            name=str(case["name"]),
            query=str(case["query"]),
            expected_seed_ids=[str(seed_id) for seed_id in list(case["expected_seed_ids"])],
        )
        raw_tags = case.get("tags")
        if raw_tags is not None:
            parsed_case["tags"] = [str(tag) for tag in list(raw_tags)]
        cases.append(parsed_case)

    return BenchmarkDataset(
        tenant_id=str(payload["tenant_id"]),
        agent_id=str(payload["agent_id"]),
        seeds=seeds,
        cases=cases,
    )


def _build_repository(backend: str, sqlite_path: str) -> MemoryRepository:
    if backend == "inmemory":
        return InMemoryRepository()
    if backend == "sqlite":
        return SQLiteRepository(sqlite_path)
    raise ValueError(f"Unsupported benchmark backend: {backend}")


def run_benchmark(
    dataset_path: str,
    backend: str = "inmemory",
    sqlite_path: str = ".data/benchmark.db",
    k: int = 5,
    graph_enabled: bool = False,
    graph_max_expansion: int = 4,
    graph_half_life_hours: float = 168.0,
    graph_relation_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    dataset = load_benchmark_dataset(dataset_path)
    repository = _build_repository(backend=backend, sqlite_path=sqlite_path)
    graph_store: InMemoryGraphStore | SQLiteGraphStore | None = None
    if graph_enabled:
        graph_store = (
            InMemoryGraphStore(
                half_life_hours=graph_half_life_hours,
                relation_weights=graph_relation_weights,
            )
            if backend == "inmemory"
            else SQLiteGraphStore(
                sqlite_path,
                half_life_hours=graph_half_life_hours,
                relation_weights=graph_relation_weights,
            )
        )

    tenant_id = dataset["tenant_id"]
    agent_id = dataset["agent_id"]
    seed_memory_ids: dict[str, str] = {}

    for seed in dataset["seeds"]:
        response = repository.remember(
            RememberRequest.model_validate(
                {
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "scope": seed["scope"],
                    "items": [
                        {
                            "type": seed["type"],
                            "text": seed["text"],
                            "trust_level": seed["trust_level"],
                        }
                    ],
                }
            )
        )
        seed_memory_ids[seed["id"]] = response.memory_ids[0]
        if graph_store is not None:
            graph_store.project_memory(
                tenant_id=tenant_id,
                memory_id=response.memory_ids[0],
                text=seed["text"],
            )

    eval_cases: list[EvalCase] = []
    for case in dataset["cases"]:
        expected_ids = [seed_memory_ids[seed_id] for seed_id in case["expected_seed_ids"]]
        eval_cases.append(
            EvalCase(
                name=case["name"],
                query=case["query"],
                expected_ids=expected_ids,
            )
        )

    eval_repository = (
        GraphAugmentedRepository(
            repository=repository,
            graph_store=graph_store,
            max_expansion=graph_max_expansion,
        )
        if graph_store is not None
        else repository
    )
    metrics, case_results = run_retrieval_eval_detailed(
        repository=eval_repository,
        tenant_id=tenant_id,
        agent_id=agent_id,
        cases=eval_cases,
        k=k,
    )

    case_tag_lookup = {
        case["name"]: [tag for tag in case.get("tags", [])]
        for case in dataset["cases"]
    }
    slice_scores: dict[str, list[dict[str, float]]] = {}
    for result in case_results:
        tags = case_tag_lookup.get(result["name"], [])
        for tag in tags:
            slice_scores.setdefault(tag, []).append(
                {
                    "recall": float(result["recall"]),
                    "ndcg": float(result["ndcg"]),
                    "tokens": float(result["composed_tokens"]),
                }
            )

    slice_metrics: dict[str, dict[str, float]] = {}
    for tag, values in slice_scores.items():
        recalls = [entry["recall"] for entry in values]
        ndcgs = [entry["ndcg"] for entry in values]
        tokens = [entry["tokens"] for entry in values]
        slice_metrics[tag] = {
            "cases": float(len(values)),
            f"recall@{k}": mean(recalls) if recalls else 0.0,
            f"ndcg@{k}": mean(ndcgs) if ndcgs else 0.0,
            "avg_composed_tokens": mean(tokens) if tokens else 0.0,
        }

    close = getattr(repository, "close", None)
    if callable(close):
        close()
    graph_close = getattr(graph_store, "close", None)
    if callable(graph_close):
        graph_close()

    return {
        "backend": backend,
        "k": k,
        "graph_enabled": graph_enabled,
        "graph_max_expansion": graph_max_expansion,
        "graph_half_life_hours": graph_half_life_hours,
        "graph_relation_weights": {
            **DEFAULT_RELATION_WEIGHTS,
            **(graph_relation_weights or {}),
        },
        "dataset_path": dataset_path,
        "seed_count": len(dataset["seeds"]),
        "case_count": len(dataset["cases"]),
        "metrics": metrics,
        "slice_metrics": slice_metrics,
        "case_results": case_results,
    }
