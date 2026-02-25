"""Repository implementations for Brainstem memory storage."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Protocol
from uuid import uuid4

from brainstem.models import (
    ForgetResponse,
    MemoryDetails,
    MemorySnippet,
    RecallRequest,
    RecallResponse,
    RememberRequest,
    RememberResponse,
    Scope,
)
from brainstem.service import (
    estimate_tokens,
    infer_confidence,
    infer_salience,
    trust_score,
)


class MemoryRepository(Protocol):
    def remember(self, payload: RememberRequest) -> RememberResponse: ...

    def inspect(
        self, tenant_id: str, agent_id: str, scope: Scope, memory_id: str
    ) -> MemoryDetails | None: ...

    def forget(self, tenant_id: str, agent_id: str, memory_id: str) -> ForgetResponse: ...

    def recall(self, payload: RecallRequest) -> RecallResponse: ...

    def purge_expired(self, tenant_id: str, grace_hours: int = 0) -> int: ...


@dataclass(slots=True)
class MemoryRecord:
    memory_id: str
    tenant_id: str
    agent_id: str
    type: str
    scope: Scope
    text: str
    trust_level: str
    confidence: float
    salience: float
    source_ref: str | None
    created_at: datetime
    expires_at: datetime | None
    tombstoned: bool = False


def _can_read(agent_id: str, requested_scope: Scope, record: MemoryRecord) -> bool:
    if record.tombstoned:
        return False
    if record.expires_at is not None and datetime.now(UTC) >= record.expires_at:
        return False
    if record.scope is Scope.GLOBAL:
        return True
    if record.scope is Scope.TEAM and requested_scope in {Scope.TEAM, Scope.GLOBAL}:
        return True
    if record.scope is Scope.PRIVATE and record.agent_id == agent_id:
        return True
    return False


def _can_delete(agent_id: str, record: MemoryRecord) -> bool:
    if record.tombstoned:
        return False
    if record.scope is Scope.PRIVATE and record.agent_id != agent_id:
        return False
    return True


def _recall_score(query: str, record: MemoryRecord) -> float:
    query_tokens = set(re.findall(r"\w+", query.lower()))
    if not query_tokens:
        return 0.0
    text_tokens = set(re.findall(r"\w+", record.text.lower()))
    lexical_overlap = len(query_tokens.intersection(text_tokens)) / len(query_tokens)
    recency_seconds = max((datetime.now(UTC) - record.created_at).total_seconds(), 1.0)
    recency_bonus = 1.0 / (1.0 + (recency_seconds / 3600.0))
    return (
        lexical_overlap * 0.45
        + record.salience * 0.25
        + record.confidence * 0.20
        + trust_score(record.trust_level) * 0.07
        + recency_bonus * 0.03
    )


def _to_snippet(record: MemoryRecord) -> MemorySnippet:
    return MemorySnippet(
        memory_id=record.memory_id,
        type=record.type,
        text=record.text,
        confidence=record.confidence,
        salience=record.salience,
        source_ref=record.source_ref,
        created_at=record.created_at,
    )


def _to_details(record: MemoryRecord) -> MemoryDetails:
    return MemoryDetails(
        memory_id=record.memory_id,
        tenant_id=record.tenant_id,
        agent_id=record.agent_id,
        type=record.type,
        scope=record.scope,
        text=record.text,
        trust_level=record.trust_level,
        confidence=record.confidence,
        salience=record.salience,
        source_ref=record.source_ref,
        created_at=record.created_at,
        expires_at=record.expires_at,
    )


def _has_negation(text: str) -> bool:
    negation_markers = (" not ", " no ", " never ", " cannot ", " can't ", " without ")
    lowered = f" {text.lower()} "
    return any(marker in lowered for marker in negation_markers)


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _detect_conflicts(records: list[MemoryRecord]) -> list[str]:
    conflicts: list[str] = []
    fact_records = [record for record in records if record.type == "fact"]
    for left_index, left in enumerate(fact_records):
        for right in fact_records[left_index + 1 :]:
            left_tokens = _token_set(left.text)
            right_tokens = _token_set(right.text)
            if not left_tokens or not right_tokens:
                continue
            overlap = len(left_tokens.intersection(right_tokens)) / len(
                left_tokens.union(right_tokens)
            )
            if overlap < 0.5:
                continue
            if _has_negation(left.text) == _has_negation(right.text):
                continue
            conflicts.append(
                f"possible_conflict:{left.memory_id}:{right.memory_id}"
            )
    return conflicts


def _pack_recall(payload: RecallRequest, candidates: list[MemoryRecord]) -> RecallResponse:
    scored = sorted(
        ((_recall_score(payload.query, record), record) for record in candidates),
        key=lambda item: item[0],
        reverse=True,
    )

    snippets: list[MemorySnippet] = []
    selected: list[MemoryRecord] = []
    tokens = 0
    for _, record in scored:
        if len(snippets) >= payload.budget.max_items:
            break
        item_tokens = estimate_tokens(record.text)
        if tokens + item_tokens > payload.budget.max_tokens:
            continue
        snippets.append(_to_snippet(record))
        selected.append(record)
        tokens += item_tokens

    return RecallResponse(
        items=snippets,
        composed_tokens_estimate=tokens,
        conflicts=_detect_conflicts(selected),
        trace_id=f"rec_{uuid4().hex[:8]}",
    )


class InMemoryRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self._records: dict[str, MemoryRecord] = {}
        self._idempotency: dict[tuple[str, str], RememberResponse] = {}

    def remember(self, payload: RememberRequest) -> RememberResponse:
        with self._lock:
            if payload.idempotency_key:
                key = (payload.tenant_id, payload.idempotency_key)
                existing = self._idempotency.get(key)
                if existing is not None:
                    return RememberResponse(
                        accepted=existing.accepted,
                        rejected=existing.rejected,
                        memory_ids=existing.memory_ids,
                        warnings=existing.warnings + ["idempotency_replay"],
                    )

            memory_ids: list[str] = []
            now = datetime.now(UTC)
            for item in payload.items:
                memory_id = f"mem_{uuid4().hex[:10]}"
                record = MemoryRecord(
                    memory_id=memory_id,
                    tenant_id=payload.tenant_id,
                    agent_id=payload.agent_id,
                    type=item.type.value,
                    scope=payload.scope,
                    text=item.text.strip(),
                    trust_level=item.trust_level.value,
                    confidence=infer_confidence(
                        text=item.text, trust_level=item.trust_level, provided=item.confidence
                    ),
                    salience=infer_salience(
                        text=item.text, memory_type=item.type, provided=item.salience
                    ),
                    source_ref=item.source_ref,
                    created_at=now,
                    expires_at=item.expires_at,
                )
                self._records[memory_id] = record
                memory_ids.append(memory_id)

            response = RememberResponse(
                accepted=len(memory_ids),
                rejected=0,
                memory_ids=memory_ids,
                warnings=[],
            )
            if payload.idempotency_key:
                self._idempotency[(payload.tenant_id, payload.idempotency_key)] = response
            return response

    def inspect(
        self, tenant_id: str, agent_id: str, scope: Scope, memory_id: str
    ) -> MemoryDetails | None:
        with self._lock:
            record = self._records.get(memory_id)
            if record is None or record.tenant_id != tenant_id:
                return None
            if not _can_read(agent_id, scope, record):
                return None
            return _to_details(record)

    def forget(self, tenant_id: str, agent_id: str, memory_id: str) -> ForgetResponse:
        with self._lock:
            record = self._records.get(memory_id)
            if record is None or record.tenant_id != tenant_id:
                return ForgetResponse(memory_id=memory_id, deleted=False)
            if not _can_delete(agent_id, record):
                return ForgetResponse(memory_id=memory_id, deleted=False)
            record.tombstoned = True
            return ForgetResponse(memory_id=memory_id, deleted=True)

    def recall(self, payload: RecallRequest) -> RecallResponse:
        with self._lock:
            allowed_types = (
                None
                if payload.filters.types is None
                else {memory_type.value for memory_type in payload.filters.types}
            )
            candidates = [
                record
                for record in self._records.values()
                if record.tenant_id == payload.tenant_id
                and _can_read(payload.agent_id, payload.scope, record)
                and trust_score(record.trust_level) >= payload.filters.trust_min
                and (allowed_types is None or record.type in allowed_types)
            ]
            return _pack_recall(payload, candidates)

    def purge_expired(self, tenant_id: str, grace_hours: int = 0) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=grace_hours)
        purged = 0
        with self._lock:
            for record in self._records.values():
                if record.tenant_id != tenant_id:
                    continue
                if record.tombstoned or record.expires_at is None:
                    continue
                if record.expires_at <= cutoff:
                    record.tombstoned = True
                    purged += 1
        return purged


class SQLiteRepository:
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
                CREATE TABLE IF NOT EXISTS memory_items (
                    memory_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    text TEXT NOT NULL,
                    trust_level TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    salience REAL NOT NULL,
                    source_ref TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    tombstoned INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_memory_tenant_created
                    ON memory_items (tenant_id, created_at);

                CREATE INDEX IF NOT EXISTS idx_memory_tenant_scope
                    ON memory_items (tenant_id, scope);

                CREATE TABLE IF NOT EXISTS idempotency_records (
                    tenant_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, idempotency_key)
                );
                """
            )
            info = self._connection.execute("PRAGMA table_info(memory_items)").fetchall()
            columns = {str(row["name"]) for row in info}
            if "expires_at" not in columns:
                self._connection.execute("ALTER TABLE memory_items ADD COLUMN expires_at TEXT")

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=str(row["memory_id"]),
            tenant_id=str(row["tenant_id"]),
            agent_id=str(row["agent_id"]),
            type=str(row["type"]),
            scope=Scope(str(row["scope"])),
            text=str(row["text"]),
            trust_level=str(row["trust_level"]),
            confidence=float(row["confidence"]),
            salience=float(row["salience"]),
            source_ref=str(row["source_ref"]) if row["source_ref"] is not None else None,
            created_at=datetime.fromisoformat(str(row["created_at"])),
            expires_at=(
                datetime.fromisoformat(str(row["expires_at"]))
                if row["expires_at"] is not None
                else None
            ),
            tombstoned=bool(int(row["tombstoned"])),
        )

    def remember(self, payload: RememberRequest) -> RememberResponse:
        with self._lock, self._connection:
            if payload.idempotency_key:
                existing = self._connection.execute(
                    """
                    SELECT response_json FROM idempotency_records
                    WHERE tenant_id = ? AND idempotency_key = ?
                    """,
                    (payload.tenant_id, payload.idempotency_key),
                ).fetchone()
                if existing is not None:
                    original = RememberResponse.model_validate_json(str(existing["response_json"]))
                    return RememberResponse(
                        accepted=original.accepted,
                        rejected=original.rejected,
                        memory_ids=original.memory_ids,
                        warnings=original.warnings + ["idempotency_replay"],
                    )

            now = datetime.now(UTC).isoformat()
            memory_ids: list[str] = []
            for item in payload.items:
                memory_id = f"mem_{uuid4().hex[:10]}"
                memory_ids.append(memory_id)
                self._connection.execute(
                    """
                    INSERT INTO memory_items (
                        memory_id, tenant_id, agent_id, type, scope, text,
                        trust_level, confidence, salience, source_ref, created_at, tombstoned
                        , expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        memory_id,
                        payload.tenant_id,
                        payload.agent_id,
                        item.type.value,
                        payload.scope.value,
                        item.text.strip(),
                        item.trust_level.value,
                        infer_confidence(
                            text=item.text,
                            trust_level=item.trust_level,
                            provided=item.confidence,
                        ),
                        infer_salience(
                            text=item.text,
                            memory_type=item.type,
                            provided=item.salience,
                        ),
                        item.source_ref,
                        now,
                        item.expires_at.isoformat() if item.expires_at else None,
                    ),
                )

            response = RememberResponse(
                accepted=len(memory_ids),
                rejected=0,
                memory_ids=memory_ids,
                warnings=[],
            )
            if payload.idempotency_key:
                self._connection.execute(
                    """
                    INSERT OR REPLACE INTO idempotency_records (
                        tenant_id, idempotency_key, response_json, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        payload.tenant_id,
                        payload.idempotency_key,
                        response.model_dump_json(),
                        now,
                    ),
                )
            return response

    def inspect(
        self, tenant_id: str, agent_id: str, scope: Scope, memory_id: str
    ) -> MemoryDetails | None:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT * FROM memory_items
                WHERE tenant_id = ? AND memory_id = ? AND tombstoned = 0
                """,
                (tenant_id, memory_id),
            ).fetchone()
            if row is None:
                return None
            record = self._row_to_record(row)
            if not _can_read(agent_id, scope, record):
                return None
            return _to_details(record)

    def forget(self, tenant_id: str, agent_id: str, memory_id: str) -> ForgetResponse:
        with self._lock, self._connection:
            row = self._connection.execute(
                """
                SELECT * FROM memory_items
                WHERE tenant_id = ? AND memory_id = ? AND tombstoned = 0
                """,
                (tenant_id, memory_id),
            ).fetchone()
            if row is None:
                return ForgetResponse(memory_id=memory_id, deleted=False)
            record = self._row_to_record(row)
            if not _can_delete(agent_id, record):
                return ForgetResponse(memory_id=memory_id, deleted=False)
            self._connection.execute(
                """
                UPDATE memory_items SET tombstoned = 1
                WHERE tenant_id = ? AND memory_id = ?
                """,
                (tenant_id, memory_id),
            )
            return ForgetResponse(memory_id=memory_id, deleted=True)

    def recall(self, payload: RecallRequest) -> RecallResponse:
        with self._lock:
            query = """
                SELECT * FROM memory_items
                WHERE tenant_id = ? AND tombstoned = 0
            """
            params: list[str] = [payload.tenant_id]
            if payload.filters.types:
                placeholders = ",".join("?" for _ in payload.filters.types)
                query = f"{query} AND type IN ({placeholders})"
                params.extend(memory_type.value for memory_type in payload.filters.types)

            rows = self._connection.execute(query, params).fetchall()
            candidates: list[MemoryRecord] = []
            for row in rows:
                record = self._row_to_record(row)
                if not _can_read(payload.agent_id, payload.scope, record):
                    continue
                if trust_score(record.trust_level) < payload.filters.trust_min:
                    continue
                candidates.append(record)

            return _pack_recall(payload, candidates)

    def purge_expired(self, tenant_id: str, grace_hours: int = 0) -> int:
        cutoff = (datetime.now(UTC) - timedelta(hours=grace_hours)).isoformat()
        with self._lock, self._connection:
            cursor = self._connection.execute(
                """
                UPDATE memory_items
                SET tombstoned = 1
                WHERE tenant_id = ?
                  AND tombstoned = 0
                  AND expires_at IS NOT NULL
                  AND expires_at <= ?
                """,
                (tenant_id, cutoff),
            )
            return int(cursor.rowcount)

    def close(self) -> None:
        self._connection.close()
