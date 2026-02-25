"""Canary model registry with persistent state and audit history."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Protocol


@dataclass(slots=True)
class SignalRecord:
    version: str
    metric: str
    value: float
    source: str | None
    created_at: datetime


@dataclass(slots=True)
class RegistryEvent:
    event_kind: str
    actor_agent_id: str | None
    payload: dict[str, Any]
    created_at: datetime


@dataclass(slots=True)
class ModelState:
    active_version: str
    canary_version: str | None = None
    rollout_percent: int = 0
    tenant_allowlist: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _clone_state(state: ModelState) -> ModelState:
    return ModelState(
        active_version=state.active_version,
        canary_version=state.canary_version,
        rollout_percent=state.rollout_percent,
        tenant_allowlist=set(state.tenant_allowlist),
        metadata=dict(state.metadata),
        updated_at=state.updated_at,
    )


def _stable_bucket(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


class ModelRegistryStore(Protocol):
    def load_states(self) -> dict[str, ModelState]: ...

    def upsert_state(self, model_kind: str, state: ModelState) -> None: ...

    def insert_signal(self, model_kind: str, signal: SignalRecord) -> None: ...

    def list_signals(
        self,
        model_kind: str,
        *,
        limit: int,
        version: str | None = None,
    ) -> list[SignalRecord]: ...

    def append_event(self, model_kind: str, event: RegistryEvent) -> None: ...

    def list_events(
        self,
        model_kind: str,
        *,
        limit: int,
    ) -> list[RegistryEvent]: ...

    def close(self) -> None: ...


class InMemoryModelRegistryStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._states: dict[str, ModelState] = {}
        self._signals: dict[str, list[SignalRecord]] = {}
        self._events: dict[str, list[RegistryEvent]] = {}

    def load_states(self) -> dict[str, ModelState]:
        with self._lock:
            return {kind: _clone_state(state) for kind, state in self._states.items()}

    def upsert_state(self, model_kind: str, state: ModelState) -> None:
        with self._lock:
            self._states[model_kind] = _clone_state(state)

    def insert_signal(self, model_kind: str, signal: SignalRecord) -> None:
        with self._lock:
            self._signals.setdefault(model_kind, []).append(signal)

    def list_signals(
        self,
        model_kind: str,
        *,
        limit: int,
        version: str | None = None,
    ) -> list[SignalRecord]:
        with self._lock:
            signals = list(self._signals.get(model_kind, []))
        if version is not None:
            signals = [signal for signal in signals if signal.version == version]
        signals.sort(key=lambda signal: signal.created_at, reverse=True)
        return signals[: max(1, limit)]

    def append_event(self, model_kind: str, event: RegistryEvent) -> None:
        with self._lock:
            self._events.setdefault(model_kind, []).append(event)

    def list_events(
        self,
        model_kind: str,
        *,
        limit: int,
    ) -> list[RegistryEvent]:
        with self._lock:
            events = list(self._events.get(model_kind, []))
        events.sort(key=lambda event: event.created_at, reverse=True)
        return events[: max(1, limit)]

    def close(self) -> None:
        return


class SQLiteModelRegistryStore:
    def __init__(self, sqlite_path: str) -> None:
        self._lock = RLock()
        db_path = Path(sqlite_path)
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(db_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS model_registry_state (
                    model_kind TEXT PRIMARY KEY,
                    active_version TEXT NOT NULL,
                    canary_version TEXT,
                    rollout_percent INTEGER NOT NULL,
                    tenant_allowlist_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS model_registry_signal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_kind TEXT NOT NULL,
                    version TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL NOT NULL,
                    source TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_model_registry_signal_kind_created
                    ON model_registry_signal (model_kind, created_at DESC);

                CREATE TABLE IF NOT EXISTS model_registry_event (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_kind TEXT NOT NULL,
                    event_kind TEXT NOT NULL,
                    actor_agent_id TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_model_registry_event_kind_created
                    ON model_registry_event (model_kind, created_at DESC);
                """
            )

    def load_states(self) -> dict[str, ModelState]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT model_kind, active_version, canary_version, rollout_percent,
                       tenant_allowlist_json, metadata_json, updated_at
                FROM model_registry_state;
                """
            ).fetchall()
        states: dict[str, ModelState] = {}
        for row in rows:
            allowlist = json.loads(str(row["tenant_allowlist_json"]))
            metadata = json.loads(str(row["metadata_json"]))
            states[str(row["model_kind"])] = ModelState(
                active_version=str(row["active_version"]),
                canary_version=(
                    str(row["canary_version"]) if row["canary_version"] is not None else None
                ),
                rollout_percent=int(row["rollout_percent"]),
                tenant_allowlist=set(allowlist if isinstance(allowlist, list) else []),
                metadata=metadata if isinstance(metadata, dict) else {},
                updated_at=datetime.fromisoformat(str(row["updated_at"])),
            )
        return states

    def upsert_state(self, model_kind: str, state: ModelState) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO model_registry_state (
                    model_kind, active_version, canary_version, rollout_percent,
                    tenant_allowlist_json, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_kind) DO UPDATE SET
                    active_version = excluded.active_version,
                    canary_version = excluded.canary_version,
                    rollout_percent = excluded.rollout_percent,
                    tenant_allowlist_json = excluded.tenant_allowlist_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    model_kind,
                    state.active_version,
                    state.canary_version,
                    state.rollout_percent,
                    json.dumps(sorted(state.tenant_allowlist)),
                    json.dumps(state.metadata),
                    state.updated_at.isoformat(),
                ),
            )

    def insert_signal(self, model_kind: str, signal: SignalRecord) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO model_registry_signal (
                    model_kind, version, metric, value, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    model_kind,
                    signal.version,
                    signal.metric,
                    signal.value,
                    signal.source,
                    signal.created_at.isoformat(),
                ),
            )

    def list_signals(
        self,
        model_kind: str,
        *,
        limit: int,
        version: str | None = None,
    ) -> list[SignalRecord]:
        bounded = max(1, limit)
        with self._lock:
            if version is None:
                rows = self._connection.execute(
                    """
                    SELECT version, metric, value, source, created_at
                    FROM model_registry_signal
                    WHERE model_kind = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?;
                    """,
                    (model_kind, bounded),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT version, metric, value, source, created_at
                    FROM model_registry_signal
                    WHERE model_kind = ? AND version = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?;
                    """,
                    (model_kind, version, bounded),
                ).fetchall()
        return [
            SignalRecord(
                version=str(row["version"]),
                metric=str(row["metric"]),
                value=float(row["value"]),
                source=str(row["source"]) if row["source"] is not None else None,
                created_at=datetime.fromisoformat(str(row["created_at"])),
            )
            for row in rows
        ]

    def append_event(self, model_kind: str, event: RegistryEvent) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO model_registry_event (
                    model_kind, event_kind, actor_agent_id, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (
                    model_kind,
                    event.event_kind,
                    event.actor_agent_id,
                    json.dumps(event.payload),
                    event.created_at.isoformat(),
                ),
            )

    def list_events(
        self,
        model_kind: str,
        *,
        limit: int,
    ) -> list[RegistryEvent]:
        bounded = max(1, limit)
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT event_kind, actor_agent_id, payload_json, created_at
                FROM model_registry_event
                WHERE model_kind = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?;
                """,
                (model_kind, bounded),
            ).fetchall()
        events: list[RegistryEvent] = []
        for row in rows:
            payload = json.loads(str(row["payload_json"]))
            events.append(
                RegistryEvent(
                    event_kind=str(row["event_kind"]),
                    actor_agent_id=(
                        str(row["actor_agent_id"]) if row["actor_agent_id"] is not None else None
                    ),
                    payload=payload if isinstance(payload, dict) else {},
                    created_at=datetime.fromisoformat(str(row["created_at"])),
                )
            )
        return events

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class PostgresModelRegistryStore:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "psycopg is required for Postgres model registry persistence. "
                "Install with `pip install -e \".[postgres]\"`."
            ) from exc

        self._lock = RLock()
        self._connection = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
        self._init_schema()

    def _init_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS model_registry_state (
                model_kind TEXT PRIMARY KEY,
                active_version TEXT NOT NULL,
                canary_version TEXT,
                rollout_percent INTEGER NOT NULL,
                tenant_allowlist_json JSONB NOT NULL,
                metadata_json JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS model_registry_signal (
                id BIGSERIAL PRIMARY KEY,
                model_kind TEXT NOT NULL,
                version TEXT NOT NULL,
                metric TEXT NOT NULL,
                value DOUBLE PRECISION NOT NULL,
                source TEXT,
                created_at TIMESTAMPTZ NOT NULL
            );
            """,
            (
                "CREATE INDEX IF NOT EXISTS idx_model_registry_signal_kind_created "
                "ON model_registry_signal (model_kind, created_at DESC)"
            ),
            """
            CREATE TABLE IF NOT EXISTS model_registry_event (
                id BIGSERIAL PRIMARY KEY,
                model_kind TEXT NOT NULL,
                event_kind TEXT NOT NULL,
                actor_agent_id TEXT,
                payload_json JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            );
            """,
            (
                "CREATE INDEX IF NOT EXISTS idx_model_registry_event_kind_created "
                "ON model_registry_event (model_kind, created_at DESC)"
            ),
        ]
        with self._connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    def load_states(self) -> dict[str, ModelState]:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT model_kind, active_version, canary_version, rollout_percent,
                       tenant_allowlist_json, metadata_json, updated_at
                FROM model_registry_state;
                """
            )
            rows = cursor.fetchall()
        states: dict[str, ModelState] = {}
        for row in rows:
            allowlist = row.get("tenant_allowlist_json")
            metadata = row.get("metadata_json")
            updated_at = row["updated_at"]
            states[str(row["model_kind"])] = ModelState(
                active_version=str(row["active_version"]),
                canary_version=(
                    str(row["canary_version"]) if row["canary_version"] is not None else None
                ),
                rollout_percent=int(row["rollout_percent"]),
                tenant_allowlist=set(allowlist if isinstance(allowlist, list) else []),
                metadata=metadata if isinstance(metadata, dict) else {},
                updated_at=(
                    updated_at
                    if isinstance(updated_at, datetime)
                    else datetime.fromisoformat(str(updated_at))
                ),
            )
        return states

    def upsert_state(self, model_kind: str, state: ModelState) -> None:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO model_registry_state (
                    model_kind, active_version, canary_version, rollout_percent,
                    tenant_allowlist_json, metadata_json, updated_at
                ) VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (model_kind) DO UPDATE SET
                    active_version = EXCLUDED.active_version,
                    canary_version = EXCLUDED.canary_version,
                    rollout_percent = EXCLUDED.rollout_percent,
                    tenant_allowlist_json = EXCLUDED.tenant_allowlist_json,
                    metadata_json = EXCLUDED.metadata_json,
                    updated_at = EXCLUDED.updated_at;
                """,
                (
                    model_kind,
                    state.active_version,
                    state.canary_version,
                    state.rollout_percent,
                    json.dumps(sorted(state.tenant_allowlist)),
                    json.dumps(state.metadata),
                    state.updated_at,
                ),
            )

    def insert_signal(self, model_kind: str, signal: SignalRecord) -> None:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO model_registry_signal (
                    model_kind, version, metric, value, source, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s);
                """,
                (
                    model_kind,
                    signal.version,
                    signal.metric,
                    signal.value,
                    signal.source,
                    signal.created_at,
                ),
            )

    def list_signals(
        self,
        model_kind: str,
        *,
        limit: int,
        version: str | None = None,
    ) -> list[SignalRecord]:
        bounded = max(1, limit)
        with self._lock, self._connection.cursor() as cursor:
            if version is None:
                cursor.execute(
                    """
                    SELECT version, metric, value, source, created_at
                    FROM model_registry_signal
                    WHERE model_kind = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s;
                    """,
                    (model_kind, bounded),
                )
            else:
                cursor.execute(
                    """
                    SELECT version, metric, value, source, created_at
                    FROM model_registry_signal
                    WHERE model_kind = %s AND version = %s
                    ORDER BY created_at DESC, id DESC
                    LIMIT %s;
                    """,
                    (model_kind, version, bounded),
                )
            rows = cursor.fetchall()

        return [
            SignalRecord(
                version=str(row["version"]),
                metric=str(row["metric"]),
                value=float(row["value"]),
                source=str(row["source"]) if row["source"] is not None else None,
                created_at=(
                    row["created_at"]
                    if isinstance(row["created_at"], datetime)
                    else datetime.fromisoformat(str(row["created_at"]))
                ),
            )
            for row in rows
        ]

    def append_event(self, model_kind: str, event: RegistryEvent) -> None:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO model_registry_event (
                    model_kind, event_kind, actor_agent_id, payload_json, created_at
                ) VALUES (%s, %s, %s, %s::jsonb, %s);
                """,
                (
                    model_kind,
                    event.event_kind,
                    event.actor_agent_id,
                    json.dumps(event.payload),
                    event.created_at,
                ),
            )

    def list_events(
        self,
        model_kind: str,
        *,
        limit: int,
    ) -> list[RegistryEvent]:
        bounded = max(1, limit)
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT event_kind, actor_agent_id, payload_json, created_at
                FROM model_registry_event
                WHERE model_kind = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s;
                """,
                (model_kind, bounded),
            )
            rows = cursor.fetchall()

        events: list[RegistryEvent] = []
        for row in rows:
            payload = row.get("payload_json")
            events.append(
                RegistryEvent(
                    event_kind=str(row["event_kind"]),
                    actor_agent_id=(
                        str(row["actor_agent_id"]) if row["actor_agent_id"] is not None else None
                    ),
                    payload=payload if isinstance(payload, dict) else {},
                    created_at=(
                        row["created_at"]
                        if isinstance(row["created_at"], datetime)
                        else datetime.fromisoformat(str(row["created_at"]))
                    ),
                )
            )
        return events

    def close(self) -> None:
        with self._lock:
            self._connection.close()


class ModelRegistry:
    def __init__(
        self,
        store: ModelRegistryStore | None = None,
        signal_window: int = 500,
    ) -> None:
        self._lock = RLock()
        self._signal_window = max(1, signal_window)
        self._store = store if store is not None else InMemoryModelRegistryStore()
        defaults = {
            "reranker": ModelState(active_version="reranker-baseline-v1"),
            "salience": ModelState(active_version="salience-baseline-v1"),
        }
        loaded = self._store.load_states()
        for kind, default_state in defaults.items():
            if kind not in loaded:
                loaded[kind] = default_state
                self._store.upsert_state(kind, default_state)
        self._states = loaded

    def get_state(self, model_kind: str) -> dict[str, Any]:
        with self._lock:
            state = self._require_state(model_kind)
            signals = self._store.list_signals(model_kind, limit=self._signal_window)
            return self._serialize_state(model_kind, state, signals)

    def register_canary(
        self,
        model_kind: str,
        version: str,
        rollout_percent: int = 10,
        tenant_allowlist: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        actor_agent_id: str | None = None,
    ) -> dict[str, Any]:
        if rollout_percent < 0 or rollout_percent > 100:
            raise ValueError("rollout_percent_out_of_range")

        with self._lock:
            state = self._require_state(model_kind)
            state.canary_version = version
            state.rollout_percent = rollout_percent
            state.tenant_allowlist = set(tenant_allowlist or [])
            state.metadata = metadata or {}
            state.updated_at = datetime.now(UTC)
            self._store.upsert_state(model_kind, state)
            self._store.append_event(
                model_kind,
                RegistryEvent(
                    event_kind="register_canary",
                    actor_agent_id=actor_agent_id,
                    payload={
                        "version": version,
                        "rollout_percent": rollout_percent,
                        "tenant_allowlist": sorted(state.tenant_allowlist),
                        "metadata": state.metadata,
                    },
                    created_at=datetime.now(UTC),
                ),
            )
            signals = self._store.list_signals(model_kind, limit=self._signal_window)
            return self._serialize_state(model_kind, state, signals)

    def promote_canary(
        self,
        model_kind: str,
        actor_agent_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._require_state(model_kind)
            if state.canary_version is None:
                raise ValueError("canary_not_set")
            previous_active = state.active_version
            state.active_version = state.canary_version
            state.canary_version = None
            state.rollout_percent = 0
            state.tenant_allowlist = set()
            state.updated_at = datetime.now(UTC)
            self._store.upsert_state(model_kind, state)
            self._store.append_event(
                model_kind,
                RegistryEvent(
                    event_kind="promote_canary",
                    actor_agent_id=actor_agent_id,
                    payload={
                        "previous_active_version": previous_active,
                        "new_active_version": state.active_version,
                    },
                    created_at=datetime.now(UTC),
                ),
            )
            signals = self._store.list_signals(model_kind, limit=self._signal_window)
            return self._serialize_state(model_kind, state, signals)

    def rollback_canary(
        self,
        model_kind: str,
        actor_agent_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._require_state(model_kind)
            previous_canary = state.canary_version
            state.canary_version = None
            state.rollout_percent = 0
            state.tenant_allowlist = set()
            state.updated_at = datetime.now(UTC)
            self._store.upsert_state(model_kind, state)
            self._store.append_event(
                model_kind,
                RegistryEvent(
                    event_kind="rollback_canary",
                    actor_agent_id=actor_agent_id,
                    payload={"previous_canary_version": previous_canary},
                    created_at=datetime.now(UTC),
                ),
            )
            signals = self._store.list_signals(model_kind, limit=self._signal_window)
            return self._serialize_state(model_kind, state, signals)

    def record_signal(
        self,
        model_kind: str,
        version: str,
        metric: str,
        value: float,
        source: str | None = None,
        actor_agent_id: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._require_state(model_kind)
            signal = SignalRecord(
                version=version,
                metric=metric,
                value=value,
                source=source,
                created_at=datetime.now(UTC),
            )
            self._store.insert_signal(model_kind, signal)
            state.updated_at = datetime.now(UTC)
            self._store.upsert_state(model_kind, state)
            self._store.append_event(
                model_kind,
                RegistryEvent(
                    event_kind="record_signal",
                    actor_agent_id=actor_agent_id,
                    payload={
                        "version": version,
                        "metric": metric,
                        "value": value,
                        "source": source,
                    },
                    created_at=datetime.now(UTC),
                ),
            )
            signals = self._store.list_signals(model_kind, limit=self._signal_window)
            return self._serialize_state(model_kind, state, signals)

    def select_version(self, model_kind: str, tenant_id: str) -> tuple[str, str]:
        with self._lock:
            state = self._require_state(model_kind)
            if state.canary_version is None:
                return state.active_version, "active"
            if tenant_id in state.tenant_allowlist:
                return state.canary_version, "canary_allowlist"
            if state.rollout_percent <= 0:
                return state.active_version, "active"
            bucket = _stable_bucket(key=f"{model_kind}:{tenant_id}")
            if bucket < state.rollout_percent:
                return state.canary_version, "canary_percent"
            return state.active_version, "active"

    def history(self, model_kind: str, limit: int = 100) -> dict[str, Any]:
        with self._lock:
            _ = self._require_state(model_kind)
            bounded = max(1, limit)
            events = self._store.list_events(model_kind, limit=bounded)
            signals = self._store.list_signals(model_kind, limit=bounded)
        entries: list[dict[str, Any]] = []
        for event in events:
            entries.append(
                {
                    "kind": "event",
                    "event_kind": event.event_kind,
                    "actor_agent_id": event.actor_agent_id,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                    "version": None,
                    "metric": None,
                    "value": None,
                    "source": None,
                }
            )
        for signal in signals:
            entries.append(
                {
                    "kind": "signal",
                    "event_kind": "record_signal",
                    "actor_agent_id": None,
                    "payload": None,
                    "created_at": signal.created_at.isoformat(),
                    "version": signal.version,
                    "metric": signal.metric,
                    "value": signal.value,
                    "source": signal.source,
                }
            )
        entries.sort(key=lambda item: str(item["created_at"]), reverse=True)
        return {"model_kind": model_kind, "items": entries[:bounded]}

    def close(self) -> None:
        self._store.close()

    def _require_state(self, model_kind: str) -> ModelState:
        if model_kind not in self._states:
            raise ValueError("unsupported_model_kind")
        return self._states[model_kind]

    @staticmethod
    def _serialize_state(
        model_kind: str,
        state: ModelState,
        signals: list[SignalRecord],
    ) -> dict[str, Any]:
        summary: dict[str, dict[str, float]] = {}
        for signal in signals:
            version_metrics = summary.setdefault(signal.version, {})
            key = f"{signal.metric}.avg"
            count_key = f"{signal.metric}.count"
            prior_sum = version_metrics.get(key, 0.0) * version_metrics.get(count_key, 0.0)
            prior_count = version_metrics.get(count_key, 0.0)
            new_count = prior_count + 1.0
            version_metrics[count_key] = new_count
            version_metrics[key] = (prior_sum + signal.value) / new_count

        return {
            "model_kind": model_kind,
            "active_version": state.active_version,
            "canary_version": state.canary_version,
            "rollout_percent": state.rollout_percent,
            "tenant_allowlist": sorted(state.tenant_allowlist),
            "metadata": state.metadata,
            "signal_summary": summary,
            "updated_at": state.updated_at.isoformat(),
        }
