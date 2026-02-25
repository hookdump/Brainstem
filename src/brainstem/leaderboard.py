"""Benchmark suite + leaderboard generation utilities."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from brainstem.benchmark import run_benchmark


class SuiteManifestEntry(TypedDict):
    id: str
    dataset_path: str
    k: int
    backends: list[str]
    graph_modes: list[str]
    focus_tags: NotRequired[list[str]]
    graph_max_expansion: NotRequired[int]
    graph_half_life_hours: NotRequired[float]
    graph_relation_weights: NotRequired[dict[str, float]]


class SuiteManifest(TypedDict):
    schema_version: str
    suites: list[SuiteManifestEntry]


def load_suite_manifest(path: str) -> SuiteManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Suite manifest must be a JSON object")
    suites = payload.get("suites")
    if not isinstance(suites, list) or not suites:
        raise ValueError("Suite manifest must contain a non-empty `suites` list")

    parsed_suites: list[SuiteManifestEntry] = []
    for suite in suites:
        if not isinstance(suite, dict):
            raise ValueError("Suite entries must be JSON objects")
        raw_modes = [str(mode).lower() for mode in list(suite.get("graph_modes", ["off", "on"]))]
        graph_modes = [mode for mode in raw_modes if mode in {"off", "on"}]
        if not graph_modes:
            raise ValueError("Suite `graph_modes` must include `off` and/or `on`")
        graph_relation_weights = suite.get("graph_relation_weights")
        if graph_relation_weights is not None and not isinstance(graph_relation_weights, dict):
            raise ValueError("Suite `graph_relation_weights` must be a JSON object")
        parsed_weights = (
            {str(key): float(value) for key, value in graph_relation_weights.items()}
            if isinstance(graph_relation_weights, dict)
            else None
        )
        parsed_entry = SuiteManifestEntry(
            id=str(suite["id"]),
            dataset_path=str(suite["dataset_path"]),
            k=int(suite.get("k", 5)),
            backends=[str(backend) for backend in list(suite["backends"])],
            graph_modes=graph_modes,
        )
        focus_tags = suite.get("focus_tags")
        if focus_tags is not None:
            parsed_entry["focus_tags"] = [str(tag) for tag in list(focus_tags)]
        half_life = suite.get("graph_half_life_hours")
        if half_life is not None:
            parsed_entry["graph_half_life_hours"] = float(half_life)
        graph_max_expansion = suite.get("graph_max_expansion")
        if graph_max_expansion is not None:
            parsed_entry["graph_max_expansion"] = int(graph_max_expansion)
        if parsed_weights is not None:
            parsed_entry["graph_relation_weights"] = parsed_weights
        parsed_suites.append(
            parsed_entry
        )
    return SuiteManifest(
        schema_version=str(payload.get("schema_version", "unknown")),
        suites=parsed_suites,
    )


def _build_graph_dashboard(
    runs: list[dict[str, Any]],
    k: int,
    focus_tags: list[str],
) -> list[dict[str, Any]]:
    runs_by_backend_mode: dict[tuple[str, str], dict[str, Any]] = {}
    backends: set[str] = set()
    for run in runs:
        backend = str(run["backend"])
        graph_mode = str(run["graph_mode"])
        backends.add(backend)
        runs_by_backend_mode[(backend, graph_mode)] = run

    dashboard: list[dict[str, Any]] = []
    recall_key = f"recall@{k}"
    ndcg_key = f"ndcg@{k}"
    for backend in sorted(backends):
        off = runs_by_backend_mode.get((backend, "off"))
        on = runs_by_backend_mode.get((backend, "on"))
        if off is None or on is None:
            continue
        off_metrics = off["metrics"]
        on_metrics = on["metrics"]
        assert isinstance(off_metrics, dict)
        assert isinstance(on_metrics, dict)

        slices_delta: dict[str, dict[str, float]] = {}
        off_slices = off.get("slice_metrics", {})
        on_slices = on.get("slice_metrics", {})
        if isinstance(off_slices, dict) and isinstance(on_slices, dict):
            for tag in focus_tags:
                off_slice = off_slices.get(tag)
                on_slice = on_slices.get(tag)
                if not isinstance(off_slice, dict) or not isinstance(on_slice, dict):
                    continue
                slices_delta[tag] = {
                    recall_key: float(on_slice.get(recall_key, 0.0))
                    - float(off_slice.get(recall_key, 0.0)),
                    ndcg_key: float(on_slice.get(ndcg_key, 0.0))
                    - float(off_slice.get(ndcg_key, 0.0)),
                    "avg_composed_tokens": float(on_slice.get("avg_composed_tokens", 0.0))
                    - float(off_slice.get("avg_composed_tokens", 0.0)),
                }

        dashboard.append(
            {
                "backend": backend,
                "overall": {
                    recall_key: float(on_metrics[recall_key]) - float(off_metrics[recall_key]),
                    ndcg_key: float(on_metrics[ndcg_key]) - float(off_metrics[ndcg_key]),
                    "avg_composed_tokens": float(on_metrics["avg_composed_tokens"])
                    - float(off_metrics["avg_composed_tokens"]),
                },
                "slices": slices_delta,
            }
        )
    return dashboard


def build_leaderboard(
    manifest_path: str,
    sqlite_dir: str,
) -> dict[str, Any]:
    manifest = load_suite_manifest(manifest_path)
    sqlite_base = Path(sqlite_dir)
    sqlite_base.mkdir(parents=True, exist_ok=True)

    suites_output: list[dict[str, Any]] = []
    for suite in manifest["suites"]:
        suite_runs: list[dict[str, Any]] = []
        focus_tags = [tag for tag in suite.get("focus_tags", [])]
        graph_max_expansion = int(suite.get("graph_max_expansion", 4))
        graph_half_life_hours = float(suite.get("graph_half_life_hours", 168.0))
        graph_relation_weights = suite.get("graph_relation_weights")

        for backend in suite["backends"]:
            for graph_mode in suite["graph_modes"]:
                sqlite_path = sqlite_base / f"{suite['id']}_{backend}_{graph_mode}.db"
                if sqlite_path.exists():
                    sqlite_path.unlink()
                benchmark = run_benchmark(
                    dataset_path=suite["dataset_path"],
                    backend=backend,
                    sqlite_path=str(sqlite_path),
                    k=suite["k"],
                    graph_enabled=graph_mode == "on",
                    graph_max_expansion=graph_max_expansion,
                    graph_half_life_hours=graph_half_life_hours,
                    graph_relation_weights=graph_relation_weights,
                )
                metrics = benchmark["metrics"]
                assert isinstance(metrics, dict)
                suite_runs.append(
                    {
                        "backend": backend,
                        "graph_mode": graph_mode,
                        "graph_enabled": graph_mode == "on",
                        "k": suite["k"],
                        "dataset_path": suite["dataset_path"],
                        "case_count": benchmark["case_count"],
                        "seed_count": benchmark["seed_count"],
                        "metrics": {
                            f"recall@{suite['k']}": metrics[f"recall@{suite['k']}"],
                            f"ndcg@{suite['k']}": metrics[f"ndcg@{suite['k']}"],
                            "avg_composed_tokens": metrics["avg_composed_tokens"],
                        },
                        "slice_metrics": benchmark.get("slice_metrics", {}),
                    }
                )
        suite_runs.sort(
            key=lambda run: (
                float(run["metrics"][f"recall@{suite['k']}"]),
                float(run["metrics"][f"ndcg@{suite['k']}"]),
            ),
            reverse=True,
        )
        graph_dashboard = _build_graph_dashboard(
            runs=suite_runs,
            k=suite["k"],
            focus_tags=focus_tags,
        )
        suites_output.append(
            {
                "id": suite["id"],
                "dataset_path": suite["dataset_path"],
                "k": suite["k"],
                "graph_modes": suite["graph_modes"],
                "focus_tags": focus_tags,
                "runs": suite_runs,
                "graph_dashboard": graph_dashboard,
            }
        )

    return {
        "schema_version": manifest["schema_version"],
        "generated_at": datetime.now(UTC).isoformat(),
        "suites": suites_output,
    }


def render_leaderboard_markdown(leaderboard: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Brainstem Benchmark Leaderboard")
    lines.append("")
    lines.append(f"Generated: {leaderboard['generated_at']}")
    lines.append(f"Manifest schema version: {leaderboard['schema_version']}")
    lines.append("")

    suites = leaderboard["suites"]
    assert isinstance(suites, list)
    for suite in suites:
        assert isinstance(suite, dict)
        suite_id = str(suite["id"])
        dataset_path = str(suite["dataset_path"])
        k = int(suite["k"])
        lines.append(f"## Suite: `{suite_id}`")
        lines.append("")
        lines.append(f"Dataset: `{dataset_path}`")
        lines.append(f"Cutoff K: `{k}`")
        lines.append("")
        lines.append("| Rank | Backend | Graph | Recall@K | nDCG@K | Avg Tokens | Cases |")
        lines.append("| ---: | --- | --- | ---: | ---: | ---: | ---: |")
        runs = suite["runs"]
        assert isinstance(runs, list)
        for idx, run in enumerate(runs, start=1):
            assert isinstance(run, dict)
            metrics = run["metrics"]
            assert isinstance(metrics, dict)
            lines.append(
                f"| {idx} | {run['backend']} | {run['graph_mode']} | "
                f"{metrics[f'recall@{k}']:.3f} | {metrics[f'ndcg@{k}']:.3f} | "
                f"{metrics['avg_composed_tokens']:.1f} | {run['case_count']} |"
            )
        lines.append("")
        dashboard = suite.get("graph_dashboard")
        if isinstance(dashboard, list) and dashboard:
            lines.append("### Graph Quality Dashboard")
            lines.append("")
            lines.append(
                "| Backend | Recall Delta (on-off) | nDCG Delta (on-off) | Avg Tokens Delta |"
            )
            lines.append("| --- | ---: | ---: | ---: |")
            for entry in dashboard:
                assert isinstance(entry, dict)
                overall = entry["overall"]
                assert isinstance(overall, dict)
                lines.append(
                    f"| {entry['backend']} | {overall[f'recall@{k}']:+.3f} | "
                    f"{overall[f'ndcg@{k}']:+.3f} | {overall['avg_composed_tokens']:+.1f} |"
                )
            lines.append("")
            focus_tags = suite.get("focus_tags")
            if isinstance(focus_tags, list) and focus_tags:
                lines.append("### Relation Slice Deltas")
                lines.append("")
                lines.append("| Backend | Tag | Recall Delta | nDCG Delta | Avg Tokens Delta |")
                lines.append("| --- | --- | ---: | ---: | ---: |")
                any_slice = False
                for entry in dashboard:
                    assert isinstance(entry, dict)
                    slices = entry.get("slices")
                    if not isinstance(slices, dict):
                        continue
                    for tag in focus_tags:
                        slice_metrics = slices.get(tag)
                        if not isinstance(slice_metrics, dict):
                            continue
                        any_slice = True
                        lines.append(
                            f"| {entry['backend']} | {tag} | "
                            f"{slice_metrics[f'recall@{k}']:+.3f} | "
                            f"{slice_metrics[f'ndcg@{k}']:+.3f} | "
                            f"{slice_metrics['avg_composed_tokens']:+.1f} |"
                        )
                if not any_slice:
                    lines.append("| n/a | n/a | +0.000 | +0.000 | +0.0 |")
                lines.append("")

    lines.append("## Contribution Guide")
    lines.append("")
    lines.append("1. Add/modify suite definitions in `benchmarks/suite_manifest.json`.")
    lines.append("2. Run `brainstem leaderboard` and commit updated artifacts if needed.")
    lines.append("3. Share metric deltas in your PR description for reproducibility.")
    lines.append("")
    return "\n".join(lines)


def write_leaderboard_artifacts(
    manifest_path: str,
    output_dir: str,
    sqlite_dir: str,
) -> tuple[str, str]:
    leaderboard = build_leaderboard(
        manifest_path=manifest_path,
        sqlite_dir=sqlite_dir,
    )
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    json_path = output_path / "leaderboard.json"
    md_path = output_path / "leaderboard.md"

    json_path.write_text(json.dumps(leaderboard, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_leaderboard_markdown(leaderboard) + "\n", encoding="utf-8")
    return str(json_path), str(md_path)
