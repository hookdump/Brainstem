from __future__ import annotations

from pathlib import Path

from brainstem.model_registry import ModelRegistry, SQLiteModelRegistryStore


def test_sqlite_registry_persists_state_and_signals_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "registry.db"

    first = ModelRegistry(store=SQLiteModelRegistryStore(str(db_path)))
    first.register_canary(
        model_kind="reranker",
        version="reranker-canary-v9",
        rollout_percent=25,
        tenant_allowlist=["t_allow"],
        metadata={"note": "persisted"},
        actor_agent_id="a_admin",
    )
    first.record_signal(
        model_kind="reranker",
        version="reranker-canary-v9",
        metric="recall_at_5",
        value=0.91,
        source="suite",
        actor_agent_id="a_admin",
    )
    first.close()

    second = ModelRegistry(store=SQLiteModelRegistryStore(str(db_path)))
    try:
        state = second.get_state("reranker")
        assert state["canary_version"] == "reranker-canary-v9"
        assert state["rollout_percent"] == 25
        assert state["metadata"]["note"] == "persisted"
        summary = state["signal_summary"]["reranker-canary-v9"]
        assert summary["recall_at_5.count"] == 1.0

        history = second.history("reranker", limit=20)
        event_kinds = [item["event_kind"] for item in history["items"]]
        assert "register_canary" in event_kinds
        assert "record_signal" in event_kinds
    finally:
        second.close()
