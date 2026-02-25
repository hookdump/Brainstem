"""Graph projection and recall expansion helpers."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

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

TEMPORAL_MARKERS = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
    "daily",
    "weekly",
    "monthly",
    "hourly",
    "minutes",
    "minute",
    "hours",
    "hour",
    "days",
    "day",
}

DEFAULT_RELATION_WEIGHTS: dict[str, float] = {
    "keyword": 1.0,
    "phrase": 1.4,
    "temporal": 1.2,
    "reference": 1.6,
}


def _normalize_relation_weights(
    relation_weights: Mapping[str, float] | None,
) -> dict[str, float]:
    weights = dict(DEFAULT_RELATION_WEIGHTS)
    if relation_weights is None:
        return weights
    for relation, value in relation_weights.items():
        key = str(relation).strip().lower()
        if key not in weights:
            raise ValueError(f"Unsupported relation weight key: {relation}")
        weights[key] = max(0.0, float(value))
    return weights


def parse_relation_weights_json(raw: str | None) -> dict[str, float] | None:
    if raw is None or not raw.strip():
        return None
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Relation weights must be a JSON object")
    parsed: dict[str, float] = {}
    for key, value in payload.items():
        if not isinstance(value, (int, float)):
            raise ValueError(f"Relation weight for {key!r} must be numeric")
        parsed[str(key)] = float(value)
    return parsed


def extract_relation_features(text: str) -> dict[str, set[str]]:
    raw_tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9#_-]+", text)]
    keywords = [
        token
        for token in raw_tokens
        if len(token) >= 3 and token not in STOPWORDS and not token.isdigit()
    ]
    keyword_features = set(keywords)
    phrase_features = {
        f"{left}_{right}"
        for left, right in zip(keywords, keywords[1:], strict=False)
        if left != right
    }
    temporal_features = {
        token for token in raw_tokens if token in TEMPORAL_MARKERS
    }
    temporal_features.update(
        {
            f"{match.group(1)}_{match.group(2)}"
            for match in re.finditer(
                r"\b(\d+)\s*(minute|minutes|hour|hours|day|days)\b",
                text.lower(),
            )
        }
    )
    reference_features = {
        token
        for token in raw_tokens
        if any(char.isdigit() for char in token)
        and any(char.isalpha() for char in token)
        and len(token) >= 3
    }

    features = {
        "keyword": keyword_features,
        "phrase": phrase_features,
        "temporal": temporal_features,
        "reference": reference_features,
    }
    return {kind: values for kind, values in features.items() if values}


def extract_relation_terms(text: str) -> set[str]:
    features = extract_relation_features(text)
    terms: set[str] = set()
    for values in features.values():
        terms.update(values)
    return terms


def _decay_multiplier(
    *,
    updated_at: datetime,
    now: datetime,
    half_life_hours: float,
) -> float:
    age_hours = max(0.0, (now - updated_at).total_seconds() / 3600.0)
    if half_life_hours <= 0:
        return 1.0
    return float(0.5 ** (age_hours / half_life_hours))


class InMemoryGraphStore:
    def __init__(
        self,
        half_life_hours: float = 168.0,
        relation_weights: Mapping[str, float] | None = None,
    ) -> None:
        self._lock = RLock()
        self._half_life_hours = max(1.0, half_life_hours)
        self._relation_weights = _normalize_relation_weights(relation_weights)
        self._terms: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        self._edges: dict[str, dict[str, dict[str, dict[str, tuple[float, datetime]]]]] = (
            defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
        )

    def project_memory(self, tenant_id: str, memory_id: str, text: str) -> None:
        features = extract_relation_features(text)
        if not features:
            return
        now = datetime.now(UTC)
        with self._lock:
            related_by_relation: dict[str, dict[str, float]] = defaultdict(
                lambda: defaultdict(float)
            )
            for relation, relation_terms in features.items():
                for term in relation_terms:
                    term_key = f"{relation}:{term}"
                    for existing in self._terms[tenant_id][term_key]:
                        if existing != memory_id:
                            related_by_relation[existing][relation] += 1.0
                    self._terms[tenant_id][term_key].add(memory_id)
            for related_id, relation_weights in related_by_relation.items():
                for relation, weight in relation_weights.items():
                    self._upsert_edge(tenant_id, memory_id, related_id, relation, weight, now)
                    self._upsert_edge(tenant_id, related_id, memory_id, relation, weight, now)

    def _upsert_edge(
        self,
        tenant_id: str,
        src_memory_id: str,
        dst_memory_id: str,
        relation: str,
        weight: float,
        now: datetime,
    ) -> None:
        existing = self._edges[tenant_id][src_memory_id][dst_memory_id].get(relation)
        previous_weight = existing[0] if existing is not None else 0.0
        self._edges[tenant_id][src_memory_id][dst_memory_id][relation] = (
            previous_weight + weight,
            now,
        )

    def related(
        self,
        tenant_id: str,
        memory_ids: Iterable[str],
        *,
        exclude_ids: set[str],
        limit: int,
    ) -> list[str]:
        now = datetime.now(UTC)
        with self._lock:
            scores: dict[str, float] = defaultdict(float)
            for memory_id in memory_ids:
                for related_id, relation_data in self._edges[tenant_id].get(memory_id, {}).items():
                    if related_id in exclude_ids:
                        continue
                    for relation, (weight, updated_at) in relation_data.items():
                        relation_weight = self._relation_weights.get(relation, 1.0)
                        scores[related_id] += (
                            weight
                            * relation_weight
                            * _decay_multiplier(
                                updated_at=updated_at,
                                now=now,
                                half_life_hours=self._half_life_hours,
                            )
                        )
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [memory_id for memory_id, _weight in ranked[:limit]]

    def query_candidates(
        self,
        tenant_id: str,
        text: str,
        *,
        exclude_ids: set[str],
        limit: int,
    ) -> list[str]:
        if limit <= 0:
            return []
        features = extract_relation_features(text)
        if not features:
            return []
        with self._lock:
            scores: dict[str, float] = defaultdict(float)
            for relation, terms in features.items():
                relation_weight = self._relation_weights.get(relation, 1.0)
                for term in terms:
                    term_key = f"{relation}:{term}"
                    for memory_id in self._terms[tenant_id].get(term_key, set()):
                        if memory_id in exclude_ids:
                            continue
                        scores[memory_id] += relation_weight
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [memory_id for memory_id, _score in ranked[:limit]]

    def close(self) -> None:
        return


class SQLiteGraphStore:
    def __init__(
        self,
        sqlite_path: str,
        half_life_hours: float = 168.0,
        relation_weights: Mapping[str, float] | None = None,
    ) -> None:
        self._sqlite_path = sqlite_path
        self._half_life_hours = max(1.0, half_life_hours)
        self._relation_weights = _normalize_relation_weights(relation_weights)
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
        features = extract_relation_features(text)
        if not features:
            return
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            related_by_relation: dict[str, dict[str, float]] = defaultdict(
                lambda: defaultdict(float)
            )
            for relation, relation_terms in features.items():
                for term in relation_terms:
                    term_key = f"{relation}:{term}"
                    rows = connection.execute(
                        """
                        SELECT memory_id FROM graph_terms
                        WHERE tenant_id = ? AND term = ?;
                        """,
                        (tenant_id, term_key),
                    ).fetchall()
                    for row in rows:
                        existing_id = str(row["memory_id"])
                        if existing_id != memory_id:
                            related_by_relation[existing_id][relation] += 1.0

                    connection.execute(
                        """
                        INSERT OR IGNORE INTO graph_terms (tenant_id, term, memory_id, created_at)
                        VALUES (?, ?, ?, ?);
                        """,
                        (tenant_id, term_key, memory_id, now),
                    )

            for related_id, relation_weights in related_by_relation.items():
                for relation, weight in relation_weights.items():
                    self._upsert_edge(
                        connection,
                        tenant_id,
                        memory_id,
                        related_id,
                        relation,
                        weight,
                        now,
                    )
                    self._upsert_edge(
                        connection,
                        tenant_id,
                        related_id,
                        memory_id,
                        relation,
                        weight,
                        now,
                    )

    def _upsert_edge(
        self,
        connection: sqlite3.Connection,
        tenant_id: str,
        src_memory_id: str,
        dst_memory_id: str,
        relation: str,
        weight: float,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO graph_edges (
                tenant_id, src_memory_id, dst_memory_id, relation, weight, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (tenant_id, src_memory_id, dst_memory_id, relation)
            DO UPDATE SET
                weight = graph_edges.weight + excluded.weight,
                created_at = excluded.created_at;
            """,
            (tenant_id, src_memory_id, dst_memory_id, relation, weight, now),
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
        params: list[object] = [tenant_id, *seeds]
        query = (
            "SELECT dst_memory_id, relation, weight, created_at "
            "FROM graph_edges "
            "WHERE tenant_id = ? "
            f"AND src_memory_id IN ({placeholders})"
        )
        if exclude_ids:
            query += f" AND dst_memory_id NOT IN ({', '.join('?' for _ in exclude_ids)})"
            params.extend(sorted(exclude_ids))
        query += ";"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        now = datetime.now(UTC)
        scored: dict[str, float] = defaultdict(float)
        for row in rows:
            dst_id = str(row["dst_memory_id"])
            relation = str(row["relation"])
            weight = float(row["weight"])
            created_at = datetime.fromisoformat(str(row["created_at"]))
            scored[dst_id] += (
                weight
                * self._relation_weights.get(relation, 1.0)
                * _decay_multiplier(
                    updated_at=created_at,
                    now=now,
                    half_life_hours=self._half_life_hours,
                )
            )
        ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)
        return [memory_id for memory_id, _score in ranked[:limit]]

    def query_candidates(
        self,
        tenant_id: str,
        text: str,
        *,
        exclude_ids: set[str],
        limit: int,
    ) -> list[str]:
        if limit <= 0:
            return []
        features = extract_relation_features(text)
        if not features:
            return []

        scored: dict[str, float] = defaultdict(float)
        with self._connect() as connection:
            for relation, terms in features.items():
                relation_weight = self._relation_weights.get(relation, 1.0)
                for term in terms:
                    term_key = f"{relation}:{term}"
                    rows = connection.execute(
                        """
                        SELECT memory_id FROM graph_terms
                        WHERE tenant_id = ? AND term = ?;
                        """,
                        (tenant_id, term_key),
                    ).fetchall()
                    for row in rows:
                        memory_id = str(row["memory_id"])
                        if memory_id in exclude_ids:
                            continue
                        scored[memory_id] += relation_weight

        ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)
        return [memory_id for memory_id, _score in ranked[:limit]]

    def close(self) -> None:
        return


class PostgresGraphStore:
    def __init__(
        self,
        dsn: str,
        half_life_hours: float = 168.0,
        relation_weights: Mapping[str, float] | None = None,
    ) -> None:
        self._dsn = dsn
        self._half_life_hours = max(1.0, half_life_hours)
        self._relation_weights = _normalize_relation_weights(relation_weights)
        self._init_schema()

    def _connect(self) -> Any:
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
        features = extract_relation_features(text)
        if not features:
            return
        with self._connect() as connection:
            with connection.cursor() as cursor:
                related_by_relation: dict[str, dict[str, float]] = defaultdict(
                    lambda: defaultdict(float)
                )
                for relation, relation_terms in features.items():
                    for term in relation_terms:
                        term_key = f"{relation}:{term}"
                        cursor.execute(
                            """
                            SELECT memory_id FROM graph_terms
                            WHERE tenant_id = %s AND term = %s;
                            """,
                            (tenant_id, term_key),
                        )
                        for (existing_id,) in cursor.fetchall():
                            existing = str(existing_id)
                            if existing != memory_id:
                                related_by_relation[existing][relation] += 1.0
                        cursor.execute(
                            """
                            INSERT INTO graph_terms (tenant_id, term, memory_id, created_at)
                            VALUES (%s, %s, %s, NOW())
                            ON CONFLICT DO NOTHING;
                            """,
                            (tenant_id, term_key, memory_id),
                        )
                for related_id, relation_weights in related_by_relation.items():
                    for relation, weight in relation_weights.items():
                        self._upsert_edge(
                            cursor, tenant_id, memory_id, related_id, relation, weight
                        )
                        self._upsert_edge(
                            cursor, tenant_id, related_id, memory_id, relation, weight
                        )

    def _upsert_edge(
        self,
        cursor: Any,
        tenant_id: str,
        src: str,
        dst: str,
        relation: str,
        weight: float,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO graph_edges (
                tenant_id, src_memory_id, dst_memory_id, relation, weight, created_at
            ) VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (tenant_id, src_memory_id, dst_memory_id, relation)
            DO UPDATE SET
                weight = graph_edges.weight + EXCLUDED.weight,
                created_at = EXCLUDED.created_at;
            """,
            (tenant_id, src, dst, relation, weight),
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
                        SELECT dst_memory_id, relation, weight, created_at
                        FROM graph_edges
                        WHERE tenant_id = %s
                          AND src_memory_id = ANY(%s)
                          AND NOT (dst_memory_id = ANY(%s));
                        """,
                        (tenant_id, seeds, sorted(exclude_ids)),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT dst_memory_id, relation, weight, created_at
                        FROM graph_edges
                        WHERE tenant_id = %s
                          AND src_memory_id = ANY(%s);
                        """,
                        (tenant_id, seeds),
                    )
                rows = cursor.fetchall()
        now = datetime.now(UTC)
        scored: dict[str, float] = defaultdict(float)
        for row in rows:
            dst_id = str(row[0])
            relation = str(row[1])
            weight = float(row[2])
            created_at = (
                row[3]
                if isinstance(row[3], datetime)
                else datetime.fromisoformat(str(row[3]))
            )
            scored[dst_id] += (
                weight
                * self._relation_weights.get(relation, 1.0)
                * _decay_multiplier(
                    updated_at=created_at,
                    now=now,
                    half_life_hours=self._half_life_hours,
                )
            )
        ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)
        return [memory_id for memory_id, _score in ranked[:limit]]

    def query_candidates(
        self,
        tenant_id: str,
        text: str,
        *,
        exclude_ids: set[str],
        limit: int,
    ) -> list[str]:
        if limit <= 0:
            return []
        features = extract_relation_features(text)
        if not features:
            return []

        scored: dict[str, float] = defaultdict(float)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for relation, terms in features.items():
                    relation_weight = self._relation_weights.get(relation, 1.0)
                    for term in terms:
                        term_key = f"{relation}:{term}"
                        cursor.execute(
                            """
                            SELECT memory_id
                            FROM graph_terms
                            WHERE tenant_id = %s AND term = %s;
                            """,
                            (tenant_id, term_key),
                        )
                        for (memory_id,) in cursor.fetchall():
                            candidate = str(memory_id)
                            if candidate in exclude_ids:
                                continue
                            scored[candidate] += relation_weight

        ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)
        return [memory_id for memory_id, _score in ranked[:limit]]

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
        expansion_budget = min(self._max_expansion, max(0, payload.budget.max_items // 2))
        base_max_items = payload.budget.max_items
        if expansion_budget > 0 and payload.budget.max_items > 1:
            base_max_items = max(1, payload.budget.max_items - expansion_budget)
        base_budget = payload.budget.model_copy(update={"max_items": base_max_items})
        base_payload = (
            payload
            if base_max_items == payload.budget.max_items
            else payload.model_copy(update={"budget": base_budget})
        )
        response = self._repository.recall(base_payload)
        remaining_slots = min(
            expansion_budget,
            max(0, payload.budget.max_items - len(response.items)),
        )
        if remaining_slots <= 0:
            return response

        seed_ids = [item.memory_id for item in response.items]
        exclude_ids = set(seed_ids)
        query_seed_candidates = self._graph_store.query_candidates(
            tenant_id=payload.tenant_id,
            text=payload.query,
            exclude_ids=exclude_ids,
            limit=max(remaining_slots * 2, self._max_expansion * 2, 4),
        )
        for candidate in query_seed_candidates:
            if candidate not in seed_ids:
                seed_ids.append(candidate)

        related_ids = self._graph_store.related(
            tenant_id=payload.tenant_id,
            memory_ids=seed_ids,
            exclude_ids=exclude_ids,
            limit=max(remaining_slots * 2, self._max_expansion * 2, 4),
        )
        if not related_ids and not query_seed_candidates:
            return response

        query_seed_set = set(query_seed_candidates)
        candidate_ids: list[str] = []
        for memory_id in related_ids:
            if (
                memory_id in exclude_ids
                or memory_id in query_seed_set
                or memory_id in candidate_ids
            ):
                continue
            candidate_ids.append(memory_id)
        for memory_id in related_ids:
            if memory_id in exclude_ids or memory_id in candidate_ids:
                continue
            candidate_ids.append(memory_id)
        for memory_id in query_seed_candidates:
            if memory_id in exclude_ids or memory_id in candidate_ids:
                continue
            candidate_ids.append(memory_id)
        if not candidate_ids:
            return response

        expanded_items = list(response.items)
        composed_tokens = response.composed_tokens_estimate
        for memory_id in candidate_ids:
            if len(expanded_items) >= payload.budget.max_items:
                break
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
