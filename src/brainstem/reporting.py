"""Benchmark reporting helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from brainstem.benchmark import run_benchmark


def generate_benchmark_report(
    dataset: str,
    output_md: str,
    k: int,
    sqlite_path: str,
) -> str:
    inmemory = run_benchmark(
        dataset_path=dataset,
        backend="inmemory",
        k=k,
    )
    sqlite = run_benchmark(
        dataset_path=dataset,
        backend="sqlite",
        sqlite_path=sqlite_path,
        k=k,
    )

    def metrics_row(label: str, benchmark: dict[str, object]) -> str:
        metrics = benchmark["metrics"]
        assert isinstance(metrics, dict)
        return (
            f"| {label} | {metrics[f'recall@{k}']:.3f} | {metrics[f'ndcg@{k}']:.3f} | "
            f"{metrics['avg_composed_tokens']:.1f} |"
        )

    lines: list[str] = []
    lines.append("# Brainstem Retrieval Benchmark Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(UTC).isoformat()}")
    lines.append(f"Dataset: `{dataset}`")
    lines.append(f"Cutoff K: `{k}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Backend | Recall@K | nDCG@K | Avg Composed Tokens |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(metrics_row("inmemory", inmemory))
    lines.append(metrics_row("sqlite", sqlite))
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

    output_path = Path(output_md)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(output_path)
