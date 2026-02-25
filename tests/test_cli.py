from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Literal
from urllib.error import URLError

import pytest

from brainstem import cli


def test_cli_serve_api_invokes_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"value": False}

    def _run() -> None:
        called["value"] = True

    monkeypatch.setattr(cli, "run_api", _run)
    status = cli.main(["serve-api"])
    assert status == 0
    assert called["value"] is True


def test_cli_init_sqlite_creates_db(tmp_path: Path) -> None:
    db_path = tmp_path / "brainstem.db"
    migration = tmp_path / "migration.sql"
    migration.write_text("CREATE TABLE demo(id INTEGER PRIMARY KEY);", encoding="utf-8")

    status = cli.main(
        ["init-sqlite", "--db", str(db_path), "--migration", str(migration)]
    )
    assert status == 0
    assert db_path.exists()

    with sqlite3.connect(str(db_path)) as connection:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='demo';"
        ).fetchone()
    assert row == ("demo",)


def test_cli_benchmark_writes_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_json = tmp_path / "benchmark.json"
    status = cli.main(
        [
            "benchmark",
            "--dataset",
            "benchmarks/retrieval_dataset.json",
            "--backend",
            "inmemory",
            "--k",
            "5",
            "--output-json",
            str(output_json),
        ]
    )
    assert status == 0
    assert output_json.exists()

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["backend"] == "inmemory"
    assert "recall@5" in payload["metrics"]

    stdout = capsys.readouterr().out
    assert "Wrote benchmark output" in stdout


def test_cli_report_writes_markdown(tmp_path: Path) -> None:
    output_md = tmp_path / "report.md"
    sqlite_path = tmp_path / "report.db"
    status = cli.main(
        [
            "report",
            "--dataset",
            "benchmarks/retrieval_dataset.json",
            "--output-md",
            str(output_md),
            "--sqlite-path",
            str(sqlite_path),
            "--k",
            "5",
        ]
    )
    assert status == 0
    assert output_md.exists()
    assert "Brainstem Retrieval Benchmark Report" in output_md.read_text(encoding="utf-8")


def test_cli_leaderboard_writes_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "leaderboard"
    sqlite_dir = tmp_path / "sqlite"
    status = cli.main(
        [
            "leaderboard",
            "--manifest",
            "benchmarks/suite_manifest.json",
            "--output-dir",
            str(output_dir),
            "--sqlite-dir",
            str(sqlite_dir),
        ]
    )
    assert status == 0
    assert (output_dir / "leaderboard.json").exists()
    assert (output_dir / "leaderboard.md").exists()


def test_cli_perf_regression_writes_artifacts(tmp_path: Path) -> None:
    output_json = tmp_path / "perf.json"
    output_md = tmp_path / "perf.md"
    status = cli.main(
        [
            "perf-regression",
            "--iterations",
            "8",
            "--seed-count",
            "4",
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
        ]
    )
    assert status == 0
    assert output_json.exists()
    assert output_md.exists()
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["pass"] is True


def test_cli_health_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> Literal[False]:
            return False

        def read(self) -> bytes:
            return b'{"status":"ok"}'

    monkeypatch.setattr(cli, "urlopen", lambda *_args, **_kwargs: _Response())
    status = cli.main(["health", "--url", "http://example.test/healthz"])
    assert status == 0
    assert '{"status":"ok"}' in capsys.readouterr().out


def test_cli_health_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _fail(*_args: object, **_kwargs: object) -> object:
        raise URLError("boom")

    monkeypatch.setattr(cli, "urlopen", _fail)
    status = cli.main(["health", "--url", "http://example.test/healthz"])
    assert status == 1
    assert "Health check failed" in capsys.readouterr().err
