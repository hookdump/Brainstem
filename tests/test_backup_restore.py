from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from brainstem.model_registry import ModelRegistry, SQLiteModelRegistryStore
from brainstem.models import RecallRequest, RememberRequest
from brainstem.store import SQLiteRepository


def _seed_sqlite(memory_db: Path, registry_db: Path) -> str:
    repo = SQLiteRepository(str(memory_db))
    registry = ModelRegistry(store=SQLiteModelRegistryStore(str(registry_db)))
    remember = repo.remember(
        RememberRequest.model_validate(
            {
                "tenant_id": "t_backup",
                "agent_id": "a_backup",
                "scope": "team",
                "items": [
                    {
                        "type": "fact",
                        "text": "backup restore regression seed",
                        "trust_level": "trusted_tool",
                    }
                ],
            }
        )
    )
    registry.record_signal(
        model_kind="reranker",
        version="reranker-baseline-v1",
        metric="recall_at_5",
        value=0.75,
        source="test",
    )
    memory_id = remember.memory_ids[0]
    repo.close()
    registry.close()
    return memory_id


def test_sqlite_backup_restore_scripts(tmp_path: Path) -> None:
    source_memory = tmp_path / "source_memory.db"
    source_registry = tmp_path / "source_registry.db"
    restore_memory = tmp_path / "restore_memory.db"
    restore_registry = tmp_path / "restore_registry.db"
    backup_dir = tmp_path / "backup"

    expected_memory_id = _seed_sqlite(source_memory, source_registry)

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
    assert (backup_dir / "memory.db").exists()
    assert (backup_dir / "model_registry.db").exists()
    assert (backup_dir / "manifest.json").exists()
    assert (backup_dir / "checksums.txt").exists()

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
    assert restore_memory.exists()
    assert restore_registry.exists()

    restored_repo = SQLiteRepository(str(restore_memory))
    recall = restored_repo.recall(
        RecallRequest.model_validate(
            {
                "tenant_id": "t_backup",
                "agent_id": "a_backup",
                "scope": "team",
                "query": "backup restore regression seed",
                "budget": {"max_items": 5, "max_tokens": 1000},
            }
        )
    )
    restored_repo.close()
    assert any(item.memory_id == expected_memory_id for item in recall.items)

    restored_registry = ModelRegistry(store=SQLiteModelRegistryStore(str(restore_registry)))
    history = restored_registry.history("reranker", limit=20)
    restored_registry.close()
    assert len(history["items"]) > 0


def test_verify_sqlite_restore_script(tmp_path: Path) -> None:
    output_json = tmp_path / "verify.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/verify_sqlite_restore.py",
            "--work-dir",
            str(tmp_path / "work"),
            "--output-json",
            str(output_json),
        ],
        check=True,
    )
    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["pass"] is True
    assert report["verified"]["restored_contains_seed_memory"] is True

