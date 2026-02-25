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
    graph_max_expansion: int = 4,
    graph_half_life_hours: float = 168.0,
    graph_relation_weights: dict[str, float] | None = None,
) -> str:
    sqlite_target = Path(sqlite_path)
    sqlite_off_path = sqlite_target.with_name(f"{sqlite_target.stem}_off{sqlite_target.suffix}")
    sqlite_on_path = sqlite_target.with_name(f"{sqlite_target.stem}_on{sqlite_target.suffix}")
    sqlite_off_path.parent.mkdir(parents=True, exist_ok=True)
    for path in (sqlite_off_path, sqlite_on_path):
        if path.exists():
            path.unlink()

    inmemory_off = run_benchmark(
        dataset_path=dataset,
        backend="inmemory",
        k=k,
        graph_enabled=False,
    )
    inmemory_on = run_benchmark(
        dataset_path=dataset,
        backend="inmemory",
        k=k,
        graph_enabled=True,
        graph_max_expansion=graph_max_expansion,
        graph_half_life_hours=graph_half_life_hours,
        graph_relation_weights=graph_relation_weights,
    )
    sqlite_off = run_benchmark(
        dataset_path=dataset,
        backend="sqlite",
        sqlite_path=str(sqlite_off_path),
        k=k,
        graph_enabled=False,
    )
    sqlite_on = run_benchmark(
        dataset_path=dataset,
        backend="sqlite",
        sqlite_path=str(sqlite_on_path),
        k=k,
        graph_enabled=True,
        graph_max_expansion=graph_max_expansion,
        graph_half_life_hours=graph_half_life_hours,
        graph_relation_weights=graph_relation_weights,
    )

    def metrics_row(label: str, graph_label: str, benchmark: dict[str, object]) -> str:
        metrics = benchmark["metrics"]
        assert isinstance(metrics, dict)
        recall_value = metrics[f"recall@{k}"]
        ndcg_value = metrics[f"ndcg@{k}"]
        return (
            f"| {label} | {graph_label} | {recall_value:.3f} | {ndcg_value:.3f} | "
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
    lines.append("| Backend | Graph Mode | Recall@K | nDCG@K | Avg Composed Tokens |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    lines.append(metrics_row("inmemory", "off", inmemory_off))
    lines.append(metrics_row("inmemory", "on", inmemory_on))
    lines.append(metrics_row("sqlite", "off", sqlite_off))
    lines.append(metrics_row("sqlite", "on", sqlite_on))
    lines.append("")
    lines.append("## Graph Impact")
    lines.append("")

    def delta_row(
        backend: str,
        baseline: dict[str, object],
        graph_on: dict[str, object],
    ) -> str:
        base_metrics = baseline["metrics"]
        on_metrics = graph_on["metrics"]
        assert isinstance(base_metrics, dict)
        assert isinstance(on_metrics, dict)
        recall_delta = float(on_metrics[f"recall@{k}"]) - float(base_metrics[f"recall@{k}"])
        ndcg_delta = float(on_metrics[f"ndcg@{k}"]) - float(base_metrics[f"ndcg@{k}"])
        token_delta = float(on_metrics["avg_composed_tokens"]) - float(
            base_metrics["avg_composed_tokens"]
        )
        return (
            f"| {backend} | {recall_delta:+.3f} | {ndcg_delta:+.3f} | {token_delta:+.1f} |"
        )

    lines.append("| Backend | Recall Delta | nDCG Delta | Avg Tokens Delta |")
    lines.append("| --- | ---: | ---: | ---: |")
    lines.append(delta_row("inmemory", inmemory_off, inmemory_on))
    lines.append(delta_row("sqlite", sqlite_off, sqlite_on))
    lines.append("")
    lines.append("## Case-level Results (inmemory, graph on)")
    lines.append("")
    lines.append("| Case | Recall | nDCG | Tokens |")
    lines.append("| --- | ---: | ---: | ---: |")

    for case in inmemory_on["case_results"]:
        assert isinstance(case, dict)
        lines.append(
            f"| {case['name']} | {case['recall']:.3f} | {case['ndcg']:.3f} | "
            f"{case['composed_tokens']:.1f} |"
        )

    slice_metrics = inmemory_on.get("slice_metrics")
    if isinstance(slice_metrics, dict) and slice_metrics:
        lines.append("")
        lines.append("## Relation Slice Metrics (inmemory, graph on)")
        lines.append("")
        lines.append("| Tag | Cases | Recall@K | nDCG@K | Avg Tokens |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for tag, metrics in sorted(slice_metrics.items()):
            if not isinstance(metrics, dict):
                continue
            lines.append(
                f"| {tag} | {metrics['cases']:.0f} | {metrics[f'recall@{k}']:.3f} | "
                f"{metrics[f'ndcg@{k}']:.3f} | {metrics['avg_composed_tokens']:.1f} |"
            )

    output_path = Path(output_md)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(output_path)
