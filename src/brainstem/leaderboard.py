"""Benchmark suite + leaderboard generation utilities."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from brainstem.benchmark import run_benchmark


class SuiteManifestEntry(TypedDict):
    id: str
    dataset_path: str
    k: int
    backends: list[str]


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
        parsed_suites.append(
            SuiteManifestEntry(
                id=str(suite["id"]),
                dataset_path=str(suite["dataset_path"]),
                k=int(suite.get("k", 5)),
                backends=[str(backend) for backend in list(suite["backends"])],
            )
        )
    return SuiteManifest(
        schema_version=str(payload.get("schema_version", "unknown")),
        suites=parsed_suites,
    )


def build_leaderboard(
    manifest_path: str,
    sqlite_dir: str,
) -> dict[str, Any]:
    manifest = load_suite_manifest(manifest_path)
    sqlite_base = Path(sqlite_dir)
    sqlite_base.mkdir(parents=True, exist_ok=True)

    suites_output: list[dict[str, Any]] = []
    for suite in manifest["suites"]:
        backend_runs: list[dict[str, Any]] = []
        for backend in suite["backends"]:
            sqlite_path = sqlite_base / f"{suite['id']}_{backend}.db"
            benchmark = run_benchmark(
                dataset_path=suite["dataset_path"],
                backend=backend,
                sqlite_path=str(sqlite_path),
                k=suite["k"],
            )
            metrics = benchmark["metrics"]
            assert isinstance(metrics, dict)
            backend_runs.append(
                {
                    "backend": backend,
                    "k": suite["k"],
                    "dataset_path": suite["dataset_path"],
                    "case_count": benchmark["case_count"],
                    "seed_count": benchmark["seed_count"],
                    "metrics": {
                        f"recall@{suite['k']}": metrics[f"recall@{suite['k']}"],
                        f"ndcg@{suite['k']}": metrics[f"ndcg@{suite['k']}"],
                        "avg_composed_tokens": metrics["avg_composed_tokens"],
                    },
                }
            )
        backend_runs.sort(
            key=lambda run: (
                float(run["metrics"][f"recall@{suite['k']}"]),
                float(run["metrics"][f"ndcg@{suite['k']}"]),
            ),
            reverse=True,
        )
        suites_output.append(
            {
                "id": suite["id"],
                "dataset_path": suite["dataset_path"],
                "k": suite["k"],
                "runs": backend_runs,
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
        lines.append("| Rank | Backend | Recall@K | nDCG@K | Avg Tokens | Cases |")
        lines.append("| ---: | --- | ---: | ---: | ---: | ---: |")
        runs = suite["runs"]
        assert isinstance(runs, list)
        for idx, run in enumerate(runs, start=1):
            assert isinstance(run, dict)
            metrics = run["metrics"]
            assert isinstance(metrics, dict)
            lines.append(
                f"| {idx} | {run['backend']} | "
                f"{metrics[f'recall@{k}']:.3f} | {metrics[f'ndcg@{k}']:.3f} | "
                f"{metrics['avg_composed_tokens']:.1f} | {run['case_count']} |"
            )
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
