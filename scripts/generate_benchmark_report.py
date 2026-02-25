#!/usr/bin/env python3
"""Generate a markdown report from Brainstem retrieval benchmarks."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from brainstem.benchmark import run_benchmark


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate retrieval benchmark markdown report.")
    parser.add_argument(
        "--dataset",
        default="benchmarks/retrieval_dataset.json",
        help="Path to benchmark dataset JSON.",
    )
    parser.add_argument(
        "--output-md",
        default="reports/retrieval_benchmark.md",
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Cutoff for Recall@K and nDCG@K.",
    )
    parser.add_argument(
        "--sqlite-path",
        default=".data/benchmark-report.db",
        help="SQLite path for sqlite backend run.",
    )
    return parser.parse_args()


def format_metrics_row(label: str, benchmark: dict[str, object], k: int) -> str:
    metrics = benchmark["metrics"]
    assert isinstance(metrics, dict)
    recall = metrics[f"recall@{k}"]
    ndcg = metrics[f"ndcg@{k}"]
    tokens = metrics["avg_composed_tokens"]
    return f"| {label} | {recall:.3f} | {ndcg:.3f} | {tokens:.1f} |"


def main() -> None:
    args = parse_args()
    inmemory = run_benchmark(
        dataset_path=args.dataset,
        backend="inmemory",
        k=args.k,
    )
    sqlite = run_benchmark(
        dataset_path=args.dataset,
        backend="sqlite",
        sqlite_path=args.sqlite_path,
        k=args.k,
    )

    lines: list[str] = []
    lines.append("# Brainstem Retrieval Benchmark Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(UTC).isoformat()}")
    lines.append(f"Dataset: `{args.dataset}`")
    lines.append(f"Cutoff K: `{args.k}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Backend | Recall@K | nDCG@K | Avg Composed Tokens |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(format_metrics_row("inmemory", inmemory, args.k))
    lines.append(format_metrics_row("sqlite", sqlite, args.k))
    lines.append("")
    lines.append("## Case-level Results (inmemory)")
    lines.append("")
    lines.append("| Case | Recall | nDCG | Tokens |")
    lines.append("| --- | ---: | ---: | ---: |")

    for case in inmemory["case_results"]:
        assert isinstance(case, dict)
        lines.append(
            f"| {case['name']} | {case['recall']:.3f} | {case['ndcg']:.3f} | "
            f"{case['composed_tokens']:.1f} |"
        )

    output_path = Path(args.output_md)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote benchmark report to {output_path}")


if __name__ == "__main__":
    main()
