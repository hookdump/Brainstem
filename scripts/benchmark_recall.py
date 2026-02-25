#!/usr/bin/env python3
"""Run a baseline retrieval benchmark for Brainstem."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from brainstem.eval import EvalCase, run_retrieval_eval
from brainstem.models import RememberRequest
from brainstem.store import InMemoryRepository, SQLiteRepository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark Brainstem retrieval quality.")
    parser.add_argument(
        "--backend",
        choices=["inmemory", "sqlite"],
        default="inmemory",
        help="Storage backend for benchmark run.",
    )
    parser.add_argument("--sqlite-path", default=".data/benchmark.db", help="SQLite DB path.")
    parser.add_argument("--k", type=int, default=5, help="Cutoff for Recall@K and nDCG@K.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    repository = (
        InMemoryRepository()
        if args.backend == "inmemory"
        else SQLiteRepository(str(Path(args.sqlite_path)))
    )

    tenant_id = "bench_tenant"
    agent_id = "bench_agent"

    seeds = [
        ("migration_deadline", "Migration must complete before April planning cycle."),
        ("security_policy", "Security policy requires MFA for all admin actions."),
        ("incident_note", "Incident channel is #ops-incidents and escalation is 15 minutes."),
        ("release_constraint", "Release cannot proceed without passing integration tests."),
    ]
    memory_ids: dict[str, str] = {}

    for key, text in seeds:
        response = repository.remember(
            RememberRequest.model_validate(
                {
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "scope": "team",
                    "items": [{"type": "fact", "text": text, "trust_level": "trusted_tool"}],
                }
            )
        )
        memory_ids[key] = response.memory_ids[0]

    cases: list[EvalCase] = [
        {
            "name": "deadline_query",
            "query": "What deadline exists for migration?",
            "expected_ids": [memory_ids["migration_deadline"]],
        },
        {
            "name": "security_query",
            "query": "Any mandatory security control for admin actions?",
            "expected_ids": [memory_ids["security_policy"]],
        },
        {
            "name": "release_query",
            "query": "What blocks the release?",
            "expected_ids": [memory_ids["release_constraint"]],
        },
    ]

    metrics = run_retrieval_eval(
        repository=repository,
        tenant_id=tenant_id,
        agent_id=agent_id,
        cases=cases,
        k=args.k,
    )
    print(json.dumps(metrics, indent=2))

    close = getattr(repository, "close", None)
    if callable(close):
        close()


if __name__ == "__main__":
    main()
