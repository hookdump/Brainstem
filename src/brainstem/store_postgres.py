"""PostgreSQL repository implementation for Brainstem."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any
from uuid import uuid4

from brainstem.models import (
    ForgetResponse,
    MemoryDetails,
    RecallRequest,
    RecallResponse,
    RememberRequest,
    RememberResponse,
    Scope,
)
from brainstem.service import infer_confidence, infer_salience, trust_score
from brainstem.store import (
    MemoryRecord,
    _can_delete,
    _can_read,
    _pack_recall,
    _to_details,
)
from brainstem.vector import hashed_embedding, vector_literal


class PostgresRepository:
    def __init__(self, dsn: str, ensure_schema: bool = True) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for Postgres backend. "
                "Install with `pip install psycopg[binary]`."
            ) from exc

        self._lock = RLock()
        self._connection = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
        if ensure_schema:
            self._init_schema()

    def _init_schema(self) -> None:
        statements = [
            "CREATE EXTENSION IF NOT EXISTS vector",
            """
            CREATE TABLE IF NOT EXISTS memory_items (
                memory_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                type TEXT NOT NULL,
                scope TEXT NOT NULL,
                text TEXT NOT NULL,
                trust_level TEXT NOT NULL,
                confidence DOUBLE PRECISION NOT NULL,
                salience DOUBLE PRECISION NOT NULL,
                source_ref TEXT,
                created_at TIMESTAMPTZ NOT NULL,
                expires_at TIMESTAMPTZ,
                tombstoned BOOLEAN NOT NULL DEFAULT FALSE,
                embedding VECTOR(1536)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS idempotency_records (
                tenant_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (tenant_id, idempotency_key)
            )
            """,
            (
                "CREATE INDEX IF NOT EXISTS idx_memory_tenant_created "
                "ON memory_items (tenant_id, created_at)"
            ),
            (
                "CREATE INDEX IF NOT EXISTS idx_memory_tenant_scope "
                "ON memory_items (tenant_id, scope)"
            ),
        ]
        with self._connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

    @staticmethod
    def _row_to_record(row: dict[str, Any]) -> MemoryRecord:
        created_at = row["created_at"]
        expires_at = row.get("expires_at")
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
            created_at=(
                created_at
                if isinstance(created_at, datetime)
                else datetime.fromisoformat(created_at)
            ),
            expires_at=(
                expires_at
                if isinstance(expires_at, datetime) or expires_at is None
                else datetime.fromisoformat(str(expires_at))
            ),
            tombstoned=bool(row["tombstoned"]),
        )

    def remember(self, payload: RememberRequest) -> RememberResponse:
        with self._lock, self._connection.cursor() as cursor:
            if payload.idempotency_key:
                cursor.execute(
                    """
                    SELECT response_json FROM idempotency_records
                    WHERE tenant_id = %s AND idempotency_key = %s
                    """,
                    (payload.tenant_id, payload.idempotency_key),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    original = RememberResponse.model_validate_json(str(existing["response_json"]))
                    return RememberResponse(
                        accepted=original.accepted,
                        rejected=original.rejected,
                        memory_ids=original.memory_ids,
                        warnings=original.warnings + ["idempotency_replay"],
                    )

            now = datetime.now(UTC)
            memory_ids: list[str] = []
            for item in payload.items:
                memory_id = f"mem_{uuid4().hex[:10]}"
                memory_ids.append(memory_id)
                cursor.execute(
                    """
                    INSERT INTO memory_items (
                        memory_id, tenant_id, agent_id, type, scope, text,
                        trust_level, confidence, salience, source_ref,
                        created_at, expires_at, embedding
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector)
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
                        item.expires_at,
                        vector_literal(hashed_embedding(item.text)),
                    ),
                )

            response = RememberResponse(
                accepted=len(memory_ids),
                rejected=0,
                memory_ids=memory_ids,
                warnings=[],
            )
            if payload.idempotency_key:
                cursor.execute(
                    """
                    INSERT INTO idempotency_records (
                        tenant_id, idempotency_key, response_json, created_at
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tenant_id, idempotency_key)
                    DO UPDATE SET
                        response_json = EXCLUDED.response_json,
                        created_at = EXCLUDED.created_at
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
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM memory_items
                WHERE tenant_id = %s AND memory_id = %s AND tombstoned = FALSE
                """,
                (tenant_id, memory_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            record = self._row_to_record(row)
            if not _can_read(agent_id, scope, record):
                return None
            return _to_details(record)

    def forget(self, tenant_id: str, agent_id: str, memory_id: str) -> ForgetResponse:
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM memory_items
                WHERE tenant_id = %s AND memory_id = %s AND tombstoned = FALSE
                """,
                (tenant_id, memory_id),
            )
            row = cursor.fetchone()
            if row is None:
                return ForgetResponse(memory_id=memory_id, deleted=False)
            record = self._row_to_record(row)
            if not _can_delete(agent_id, record):
                return ForgetResponse(memory_id=memory_id, deleted=False)
            cursor.execute(
                """
                UPDATE memory_items
                SET tombstoned = TRUE
                WHERE tenant_id = %s AND memory_id = %s
                """,
                (tenant_id, memory_id),
            )
            return ForgetResponse(memory_id=memory_id, deleted=True)

    def recall(self, payload: RecallRequest) -> RecallResponse:
        with self._lock, self._connection.cursor() as cursor:
            where_clauses = ["tenant_id = %s", "tombstoned = FALSE"]
            params: list[Any] = [payload.tenant_id]
            if payload.filters.types:
                where_clauses.append("type = ANY(%s)")
                params.append([memory_type.value for memory_type in payload.filters.types])

            where = " AND ".join(where_clauses)
            rows: list[dict[str, Any]]
            vector_query = (
                f"SELECT *, (embedding <=> %s::vector) AS vector_distance "
                f"FROM memory_items WHERE {where} "
                f"ORDER BY vector_distance ASC NULLS LAST "
                f"LIMIT 512"
            )
            try:
                query_vector = vector_literal(hashed_embedding(payload.query))
                cursor.execute(vector_query, [query_vector, *params])
                rows = cursor.fetchall()
            except Exception:
                fallback_query = f"SELECT * FROM memory_items WHERE {where}"
                cursor.execute(fallback_query, params)
                rows = cursor.fetchall()

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
        cutoff = datetime.now(UTC) - timedelta(hours=grace_hours)
        with self._lock, self._connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE memory_items
                SET tombstoned = TRUE
                WHERE tenant_id = %s
                  AND tombstoned = FALSE
                  AND expires_at IS NOT NULL
                  AND expires_at <= %s
                """,
                (tenant_id, cutoff),
            )
            rowcount = cursor.rowcount
        return int(rowcount if rowcount is not None else 0)

    def close(self) -> None:
        self._connection.close()
