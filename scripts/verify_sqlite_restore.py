#!/usr/bin/env python3
"""Create, backup, restore, and verify SQLite Brainstem data."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brainstem.model_registry import ModelRegistry, SQLiteModelRegistryStore
from brainstem.models import RecallRequest, RememberRequest
from brainstem.store import SQLiteRepository


def _seed_source(memory_db: Path, registry_db: Path) -> dict[str, Any]:
    repo = SQLiteRepository(str(memory_db))
    registry = ModelRegistry(store=SQLiteModelRegistryStore(str(registry_db)))

    remember = repo.remember(
        RememberRequest.model_validate(
            {
                "tenant_id": "t_restore",
                "agent_id": "a_restore",
                "scope": "team",
                "items": [
                    {
                        "type": "fact",
                        "text": "Restore verification memory survives backup and restore.",
                        "trust_level": "trusted_tool",
                    }
                ],
            }
        )
    )
    memory_id = remember.memory_ids[0]

    registry.record_signal(
        model_kind="reranker",
        version="reranker-baseline-v1",
        metric="recall_at_5",
        value=0.91,
        source="restore_verification",
        actor_agent_id="a_restore",
    )

    source_recall = repo.recall(
        RecallRequest.model_validate(
            {
                "tenant_id": "t_restore",
                "agent_id": "a_restore",
                "scope": "team",
                "query": "What survives backup and restore?",
                "budget": {"max_items": 5, "max_tokens": 1000},
            }
        )
    )
    source_history = registry.history("reranker", limit=20)

    repo.close()
    registry.close()

    return {
        "memory_id": memory_id,
        "source_recall_count": len(source_recall.items),
        "source_history_items": len(source_history["items"]),
    }


def _verify_restore(memory_db: Path, registry_db: Path, expected_memory_id: str) -> dict[str, Any]:
    repo = SQLiteRepository(str(memory_db))
    registry = ModelRegistry(store=SQLiteModelRegistryStore(str(registry_db)))

    recall = repo.recall(
        RecallRequest.model_validate(
            {
                "tenant_id": "t_restore",
                "agent_id": "a_restore",
                "scope": "team",
                "query": "What survives backup and restore?",
                "budget": {"max_items": 5, "max_tokens": 1000},
            }
        )
    )
    history = registry.history("reranker", limit=20)

    recall_ids = [item.memory_id for item in recall.items]
    passed = expected_memory_id in recall_ids and len(history["items"]) > 0

    repo.close()
    registry.close()

    return {
        "passed": passed,
        "restored_recall_count": len(recall.items),
        "restored_history_items": len(history["items"]),
        "restored_contains_seed_memory": expected_memory_id in recall_ids,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    source_memory = work_dir / "source_memory.db"
    source_registry = work_dir / "source_model_registry.db"
    restore_memory = work_dir / "restore_memory.db"
    restore_registry = work_dir / "restore_model_registry.db"
    backup_dir = work_dir / "backup"

    for path in (source_memory, source_registry, restore_memory, restore_registry):
        if path.exists():
            path.unlink()

    if backup_dir.exists():
        for child in backup_dir.iterdir():
            child.unlink()
    backup_dir.mkdir(parents=True, exist_ok=True)

    seeded = _seed_source(source_memory, source_registry)

    subprocess.run(
        [
            "bash",
            "scripts/backup_sqlite.sh",
            "--memory-db",
            str(source_memory),
            "--registry-db",
            str(source_registry),
            "--out-dir",
            str(backup_dir),
        ],
        check=True,
    )

    subprocess.run(
        [
            "bash",
            "scripts/restore_sqlite.sh",
            "--backup-dir",
            str(backup_dir),
            "--memory-db",
            str(restore_memory),
            "--registry-db",
            str(restore_registry),
        ],
        check=True,
    )

    verified = _verify_restore(
        restore_memory,
        restore_registry,
        expected_memory_id=str(seeded["memory_id"]),
    )

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "work_dir": str(work_dir),
        "seeded": seeded,
        "verified": verified,
        "pass": bool(verified["passed"]),
    }
    output = Path(args.output_json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify SQLite backup/restore path.")
    parser.add_argument("--work-dir", default=".data/restore-verify")
    parser.add_argument("--output-json", default=".data/restore-verify/verification.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = run(args)
    except Exception as exc:
        print(f"Restore verification failed: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote verification report to {args.output_json}")
    print(f"Restore verification status: {'PASS' if report['pass'] else 'FAIL'}")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

