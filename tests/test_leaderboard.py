from __future__ import annotations

import json
from pathlib import Path

from brainstem.leaderboard import load_suite_manifest, write_leaderboard_artifacts


def test_load_suite_manifest() -> None:
    manifest = load_suite_manifest("benchmarks/suite_manifest.json")
    assert manifest["schema_version"] == "2026-02-25"
    assert len(manifest["suites"]) >= 1
    assert manifest["suites"][0]["id"] == "retrieval_core_v1"


def test_write_leaderboard_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "leaderboard"
    sqlite_dir = tmp_path / "sqlite"
    json_path, md_path = write_leaderboard_artifacts(
        manifest_path="benchmarks/suite_manifest.json",
        output_dir=str(output_dir),
        sqlite_dir=str(sqlite_dir),
    )

    json_file = Path(json_path)
    md_file = Path(md_path)
    assert json_file.exists()
    assert md_file.exists()

    payload = json.loads(json_file.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "2026-02-25"
    assert len(payload["suites"]) >= 1

    markdown = md_file.read_text(encoding="utf-8")
    assert "Brainstem Benchmark Leaderboard" in markdown
    assert "Contribution Guide" in markdown
