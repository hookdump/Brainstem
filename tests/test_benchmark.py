from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from brainstem.benchmark import load_benchmark_dataset, run_benchmark


def test_load_benchmark_dataset() -> None:
    dataset = load_benchmark_dataset("benchmarks/retrieval_dataset.json")
    assert dataset["tenant_id"] == "bench_tenant"
    assert len(dataset["seeds"]) >= 8
    assert len(dataset["cases"]) >= 10


def test_run_benchmark_inmemory() -> None:
    output = run_benchmark(
        dataset_path="benchmarks/retrieval_dataset.json",
        backend="inmemory",
        k=5,
    )
    assert output["backend"] == "inmemory"
    assert output["case_count"] >= 10
    metrics = output["metrics"]
    assert 0.0 <= metrics["recall@5"] <= 1.0
    assert 0.0 <= metrics["ndcg@5"] <= 1.0


def test_generate_benchmark_report_script(tmp_path: Path) -> None:
    report_path = tmp_path / "report.md"
    subprocess.run(
        [
            sys.executable,
            "scripts/generate_benchmark_report.py",
            "--dataset",
            "benchmarks/retrieval_dataset.json",
            "--output-md",
            str(report_path),
            "--k",
            "5",
            "--sqlite-path",
            str(tmp_path / "bench.db"),
        ],
        check=True,
    )
    content = report_path.read_text(encoding="utf-8")
    assert "Brainstem Retrieval Benchmark Report" in content
    assert "| Backend | Recall@K | nDCG@K | Avg Composed Tokens |" in content


def test_generate_leaderboard_script(tmp_path: Path) -> None:
    output_dir = tmp_path / "leaderboard"
    sqlite_dir = tmp_path / "leaderboard-db"
    subprocess.run(
        [
            sys.executable,
            "scripts/generate_leaderboard.py",
            "--manifest",
            "benchmarks/suite_manifest.json",
            "--output-dir",
            str(output_dir),
            "--sqlite-dir",
            str(sqlite_dir),
        ],
        check=True,
    )
    assert (output_dir / "leaderboard.json").exists()
    assert (output_dir / "leaderboard.md").exists()
