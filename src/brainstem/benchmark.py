"""Benchmark dataset loading and execution utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from brainstem.eval import EvalCase, run_retrieval_eval_detailed
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
    return BenchmarkDataset(
        tenant_id=str(payload["tenant_id"]),
        agent_id=str(payload["agent_id"]),
        seeds=list(payload["seeds"]),
        cases=list(payload["cases"]),
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
) -> dict[str, Any]:
    dataset = load_benchmark_dataset(dataset_path)
    repository = _build_repository(backend=backend, sqlite_path=sqlite_path)

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

    metrics, case_results = run_retrieval_eval_detailed(
        repository=repository,
        tenant_id=tenant_id,
        agent_id=agent_id,
        cases=eval_cases,
        k=k,
    )

    close = getattr(repository, "close", None)
    if callable(close):
        close()

    return {
        "backend": backend,
        "k": k,
        "dataset_path": dataset_path,
        "seed_count": len(dataset["seeds"]),
        "case_count": len(dataset["cases"]),
        "metrics": metrics,
        "case_results": case_results,
    }
