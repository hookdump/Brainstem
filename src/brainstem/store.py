"""In-memory repository used for v0 bootstrap."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
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
    tombstoned: bool = False


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

    def inspect(self, tenant_id: str, memory_id: str) -> MemoryDetails | None:
        with self._lock:
            record = self._records.get(memory_id)
            if record is None or record.tombstoned or record.tenant_id != tenant_id:
                return None
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
            )

    def forget(self, tenant_id: str, memory_id: str) -> ForgetResponse:
        with self._lock:
            record = self._records.get(memory_id)
            if record is None or record.tenant_id != tenant_id:
                return ForgetResponse(memory_id=memory_id, deleted=False)
            record.tombstoned = True
            return ForgetResponse(memory_id=memory_id, deleted=True)

    def recall(self, payload: RecallRequest) -> RecallResponse:
        with self._lock:
            candidates = [
                record
                for record in self._records.values()
                if self._can_read(payload.agent_id, payload.tenant_id, payload.scope, record)
                and trust_score(record.trust_level) >= payload.filters.trust_min
                and (
                    payload.filters.types is None
                    or record.type in {memory_type.value for memory_type in payload.filters.types}
                )
            ]

            scored = sorted(
                (
                    (self._recall_score(payload.query, record), record)
                    for record in candidates
                ),
                key=lambda item: item[0],
                reverse=True,
            )

            snippets: list[MemorySnippet] = []
            tokens = 0
            for _, record in scored:
                if len(snippets) >= payload.budget.max_items:
                    break
                item_tokens = estimate_tokens(record.text)
                if tokens + item_tokens > payload.budget.max_tokens:
                    continue
                snippets.append(
                    MemorySnippet(
                        memory_id=record.memory_id,
                        type=record.type,
                        text=record.text,
                        confidence=record.confidence,
                        salience=record.salience,
                        source_ref=record.source_ref,
                        created_at=record.created_at,
                    )
                )
                tokens += item_tokens

            return RecallResponse(
                items=snippets,
                composed_tokens_estimate=tokens,
                conflicts=[],
                trace_id=f"rec_{uuid4().hex[:8]}",
            )

    @staticmethod
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

    @staticmethod
    def _can_read(
        agent_id: str, tenant_id: str, requested_scope: Scope, record: MemoryRecord
    ) -> bool:
        if record.tombstoned or record.tenant_id != tenant_id:
            return False
        if record.scope is Scope.GLOBAL:
            return True
        if record.scope is Scope.TEAM and requested_scope in {Scope.TEAM, Scope.GLOBAL}:
            return True
        if record.scope is Scope.PRIVATE and record.agent_id == agent_id:
            return True
        return False
