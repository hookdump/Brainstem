from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from brainstem.performance import (
    evaluate_budgets,
    percentile,
    render_performance_markdown,
    run_performance_regression,
    write_performance_artifacts,
)


def test_percentile() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(values, 50.0) == 30.0
    assert percentile(values, 95.0) == 50.0
    assert percentile(values, 0.0) == 10.0


def test_evaluate_budgets_detects_violations() -> None:
    summary = {
        "metrics": {
            "remember_ms": {"p95": 300.0},
            "recall_ms": {"p95": 350.0},
        },
        "memory": {"growth_bytes": 90_000_000.0},
    }
    violations = evaluate_budgets(
        summary,
        max_remember_p95_ms=250.0,
        max_recall_p95_ms=250.0,
        max_memory_growth_bytes=80_000_000.0,
    )
    assert any("remember_p95_ms_exceeded" in violation for violation in violations)
    assert any("recall_p95_ms_exceeded" in violation for violation in violations)
    assert any("memory_growth_exceeded" in violation for violation in violations)


def test_run_performance_regression_smoke(tmp_path: Path) -> None:
    result = run_performance_regression(
        iterations=8,
        seed_count=4,
        max_remember_p95_ms=10_000.0,
        max_recall_p95_ms=10_000.0,
        max_memory_growth_bytes=200_000_000.0,
    )
    assert "summary" in result
    assert "violations" in result
    assert "pass" in result
    summary = result["summary"]
    assert summary["metrics"]["remember_ms"]["count"] == 8.0
    assert summary["metrics"]["recall_ms"]["count"] == 8.0

    json_path, md_path = write_performance_artifacts(
        output_json=str(tmp_path / "perf.json"),
        output_md=str(tmp_path / "perf.md"),
        result=result,
    )
    json_payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert "summary" in json_payload
    markdown = Path(md_path).read_text(encoding="utf-8")
    assert "Brainstem Performance Regression Report" in markdown
    assert "Status: `PASS`" in markdown


def test_render_performance_markdown_with_failures() -> None:
    summary = {
        "generated_at": "2026-02-25T00:00:00+00:00",
        "config": {"iterations": 5.0, "seed_count": 2.0},
        "metrics": {
            "remember_ms": {"avg": 1.0, "p50": 1.0, "p95": 2.0, "p99": 2.0},
            "recall_ms": {"avg": 1.0, "p50": 1.0, "p95": 2.0, "p99": 2.0},
        },
        "memory": {"growth_bytes": 100.0, "peak_growth_bytes": 120.0},
    }
    md = render_performance_markdown(
        summary,
        violations=["remember_p95_ms_exceeded:2.0>1.0"],
        budgets={
            "max_remember_p95_ms": 1.0,
            "max_recall_p95_ms": 1.0,
            "max_memory_growth_bytes": 50.0,
        },
    )
    assert "Status: `FAIL`" in md
    assert "remember_p95_ms_exceeded" in md


def test_performance_script_wrapper(tmp_path: Path) -> None:
    output_json = tmp_path / "perf-script.json"
    output_md = tmp_path / "perf-script.md"
    subprocess.run(
        [
            sys.executable,
            "scripts/run_performance_regression.py",
            "--iterations",
            "6",
            "--seed-count",
            "2",
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
            "--max-remember-p95-ms",
            "10000",
            "--max-recall-p95-ms",
            "10000",
            "--max-memory-growth-bytes",
            "200000000",
        ],
        check=True,
    )
    assert output_json.exists()
    assert output_md.exists()
