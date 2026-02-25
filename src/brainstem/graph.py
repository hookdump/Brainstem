"""Graph projection and recall expansion helpers."""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from brainstem.models import MemorySnippet, RecallRequest, RecallResponse
from brainstem.store import MemoryRepository

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "with",
}


def extract_relation_terms(text: str) -> set[str]:
    terms = {
        token
        for token in re.findall(r"[a-z0-9]{3,}", text.lower())
        if token not in STOPWORDS and not token.isdigit()
    }
    return terms


class InMemoryGraphStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._terms: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._edges: dict[str, dict[str, dict[str, float]]] = defaultdict(
            lambda: defaultdict(dict)
        )

    def project_memory(self, tenant_id: str, memory_id: str, text: str) -> None:
        terms = extract_relation_terms(text)
        if not terms:
            return
        with self._lock:
            related_weights: dict[str, float] = defaultdict(float)
            for term in terms:
                for existing in self._terms[tenant_id][term]:
                    if existing != memory_id:
                        related_weights[existing] += 1.0
                self._terms[tenant_id][term].add(memory_id)
            for related_id, weight in related_weights.items():
                self._edges[tenant_id][memory_id][related_id] = (
                    self._edges[tenant_id][memory_id].get(related_id, 0.0) + weight
                )
                self._edges[tenant_id][related_id][memory_id] = (
                    self._edges[tenant_id][related_id].get(memory_id, 0.0) + weight
                )

    def related(
        self,
        tenant_id: str,
        memory_ids: Iterable[str],
        *,
        exclude_ids: set[str],
        limit: int,
    ) -> list[str]:
        with self._lock:
            scores: dict[str, float] = defaultdict(float)
            for memory_id in memory_ids:
                for related_id, weight in self._edges[tenant_id].get(memory_id, {}).items():
                    if related_id in exclude_ids:
                        continue
                    scores[related_id] += weight
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [memory_id for memory_id, _weight in ranked[:limit]]

    def close(self) -> None:
        return


class SQLiteGraphStore:
    def __init__(self, sqlite_path: str) -> None:
        self._sqlite_path = sqlite_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        db_path = Path(self._sqlite_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(db_path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_terms (
                    tenant_id TEXT NOT NULL,
                    term TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, term, memory_id)
                );
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS graph_edges (
                    tenant_id TEXT NOT NULL,
                    src_memory_id TEXT NOT NULL,
                    dst_memory_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    weight REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (tenant_id, src_memory_id, dst_memory_id, relation)
                );
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_graph_edges_src
                ON graph_edges (tenant_id, src_memory_id);
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_graph_terms_term
                ON graph_terms (tenant_id, term);
                """
            )

    def project_memory(self, tenant_id: str, memory_id: str, text: str) -> None:
        terms = extract_relation_terms(text)
        if not terms:
            return
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            related_weights: dict[str, float] = defaultdict(float)
            for term in terms:
                rows = connection.execute(
                    """
                    SELECT memory_id FROM graph_terms
                    WHERE tenant_id = ? AND term = ?;
                    """,
                    (tenant_id, term),
                ).fetchall()
                for row in rows:
                    existing_id = str(row["memory_id"])
                    if existing_id != memory_id:
                        related_weights[existing_id] += 1.0

                connection.execute(
                    """
                    INSERT OR IGNORE INTO graph_terms (tenant_id, term, memory_id, created_at)
                    VALUES (?, ?, ?, ?);
                    """,
                    (tenant_id, term, memory_id, now),
                )

            for related_id, weight in related_weights.items():
                self._upsert_edge(connection, tenant_id, memory_id, related_id, weight, now)
                self._upsert_edge(connection, tenant_id, related_id, memory_id, weight, now)

    def _upsert_edge(
        self,
        connection: sqlite3.Connection,
        tenant_id: str,
        src_memory_id: str,
        dst_memory_id: str,
        weight: float,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO graph_edges (
                tenant_id, src_memory_id, dst_memory_id, relation, weight, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id, src_memory_id, dst_memory_id, relation)
            DO UPDATE SET weight = graph_edges.weight + excluded.weight;
            """,
            (tenant_id, src_memory_id, dst_memory_id, "shared_term", weight, now),
        )

    def related(
        self,
        tenant_id: str,
        memory_ids: Iterable[str],
        *,
        exclude_ids: set[str],
        limit: int,
    ) -> list[str]:
        seeds = list(memory_ids)
        if not seeds or limit <= 0:
            return []
        placeholders = ", ".join("?" for _ in seeds)
        exclude_clause = ""
        params: list[object] = [tenant_id, *seeds]
        if exclude_ids:
            exclude_clause = f"AND dst_memory_id NOT IN ({', '.join('?' for _ in exclude_ids)})"
            params.extend(sorted(exclude_ids))
        params.append(limit)
        query = (
            "SELECT dst_memory_id, SUM(weight) AS score "
            "FROM graph_edges "
            "WHERE tenant_id = ? "
            f"AND src_memory_id IN ({placeholders}) "
            f"{exclude_clause} "
            "GROUP BY dst_memory_id "
            "ORDER BY score DESC "
            "LIMIT ?;"
        )
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [str(row["dst_memory_id"]) for row in rows]

    def close(self) -> None:
        return


class PostgresGraphStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._init_schema()

    def _connect(self):
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "psycopg is required for Postgres graph store support. "
                "Install with `pip install -e \".[postgres]\"`."
            ) from exc
        return psycopg.connect(self._dsn, autocommit=True)

    def _init_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS graph_terms (
                        tenant_id TEXT NOT NULL,
                        term TEXT NOT NULL,
                        memory_id TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (tenant_id, term, memory_id)
                    );
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS graph_edges (
                        tenant_id TEXT NOT NULL,
                        src_memory_id TEXT NOT NULL,
                        dst_memory_id TEXT NOT NULL,
                        relation TEXT NOT NULL,
                        weight DOUBLE PRECISION NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        PRIMARY KEY (tenant_id, src_memory_id, dst_memory_id, relation)
                    );
                    """
                )

    def project_memory(self, tenant_id: str, memory_id: str, text: str) -> None:
        terms = extract_relation_terms(text)
        if not terms:
            return
        with self._connect() as connection:
            with connection.cursor() as cursor:
                related_weights: dict[str, float] = defaultdict(float)
                for term in terms:
                    cursor.execute(
                        """
                        SELECT memory_id FROM graph_terms
                        WHERE tenant_id = %s AND term = %s;
                        """,
                        (tenant_id, term),
                    )
                    for (existing_id,) in cursor.fetchall():
                        existing = str(existing_id)
                        if existing != memory_id:
                            related_weights[existing] += 1.0
                    cursor.execute(
                        """
                        INSERT INTO graph_terms (tenant_id, term, memory_id, created_at)
                        VALUES (%s, %s, %s, NOW())
                        ON CONFLICT DO NOTHING;
                        """,
                        (tenant_id, term, memory_id),
                    )
                for related_id, weight in related_weights.items():
                    self._upsert_edge(cursor, tenant_id, memory_id, related_id, weight)
                    self._upsert_edge(cursor, tenant_id, related_id, memory_id, weight)

    def _upsert_edge(self, cursor, tenant_id: str, src: str, dst: str, weight: float) -> None:
        cursor.execute(
            """
            INSERT INTO graph_edges (
                tenant_id, src_memory_id, dst_memory_id, relation, weight, created_at
            ) VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (tenant_id, src_memory_id, dst_memory_id, relation)
            DO UPDATE SET weight = graph_edges.weight + EXCLUDED.weight;
            """,
            (tenant_id, src, dst, "shared_term", weight),
        )

    def related(
        self,
        tenant_id: str,
        memory_ids: Iterable[str],
        *,
        exclude_ids: set[str],
        limit: int,
    ) -> list[str]:
        seeds = list(memory_ids)
        if not seeds or limit <= 0:
            return []
        with self._connect() as connection:
            with connection.cursor() as cursor:
                if exclude_ids:
                    cursor.execute(
                        """
                        SELECT dst_memory_id, SUM(weight) AS score
                        FROM graph_edges
                        WHERE tenant_id = %s
                          AND src_memory_id = ANY(%s)
                          AND NOT (dst_memory_id = ANY(%s))
                        GROUP BY dst_memory_id
                        ORDER BY score DESC
                        LIMIT %s;
                        """,
                        (tenant_id, seeds, sorted(exclude_ids), limit),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT dst_memory_id, SUM(weight) AS score
                        FROM graph_edges
                        WHERE tenant_id = %s
                          AND src_memory_id = ANY(%s)
                        GROUP BY dst_memory_id
                        ORDER BY score DESC
                        LIMIT %s;
                        """,
                        (tenant_id, seeds, limit),
                    )
                rows = cursor.fetchall()
        return [str(row[0]) for row in rows]

    def close(self) -> None:
        return


class GraphAugmentedRepository:
    def __init__(
        self,
        repository: MemoryRepository,
        graph_store: InMemoryGraphStore | SQLiteGraphStore | PostgresGraphStore,
        max_expansion: int = 4,
    ) -> None:
        self._repository = repository
        self._graph_store = graph_store
        self._max_expansion = max(0, max_expansion)

    def recall(self, payload: RecallRequest) -> RecallResponse:
        response = self._repository.recall(payload)
        remaining_slots = min(
            self._max_expansion,
            max(0, payload.budget.max_items - len(response.items)),
        )
        if remaining_slots <= 0:
            return response

        seed_ids = [item.memory_id for item in response.items]
        exclude_ids = set(seed_ids)
        related_ids = self._graph_store.related(
            tenant_id=payload.tenant_id,
            memory_ids=seed_ids,
            exclude_ids=exclude_ids,
            limit=remaining_slots,
        )
        if not related_ids:
            return response

        expanded_items = list(response.items)
        composed_tokens = response.composed_tokens_estimate
        for memory_id in related_ids:
            details = self._repository.inspect(
                tenant_id=payload.tenant_id,
                agent_id=payload.agent_id,
                scope=payload.scope,
                memory_id=memory_id,
            )
            if details is None:
                continue
            snippet = MemorySnippet(
                memory_id=details.memory_id,
                type=details.type,
                text=details.text,
                confidence=details.confidence,
                salience=details.salience,
                source_ref=details.source_ref,
                created_at=details.created_at,
            )
            estimated_tokens = max(1, len(snippet.text.split()))
            if composed_tokens + estimated_tokens > payload.budget.max_tokens:
                continue
            expanded_items.append(snippet)
            composed_tokens += estimated_tokens

        return RecallResponse(
            items=expanded_items,
            composed_tokens_estimate=composed_tokens,
            conflicts=response.conflicts,
            trace_id=response.trace_id,
            model_version=response.model_version,
            model_route=response.model_route,
        )
