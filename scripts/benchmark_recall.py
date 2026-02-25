#!/usr/bin/env python3
"""Run Brainstem retrieval benchmark using a dataset file."""

from __future__ import annotations

import argparse
import json

from brainstem.benchmark import run_benchmark


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
    parser.add_argument(
        "--dataset",
        default="benchmarks/retrieval_dataset.json",
        help="Path to benchmark dataset JSON.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional path for writing full benchmark output JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = run_benchmark(
        dataset_path=args.dataset,
        backend=args.backend,
        sqlite_path=args.sqlite_path,
        k=args.k,
    )
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as handle:
            json.dump(output, handle, indent=2)
        print(f"Wrote benchmark output to {args.output_json}")
    print(json.dumps(output["metrics"], indent=2))


if __name__ == "__main__":
    main()
