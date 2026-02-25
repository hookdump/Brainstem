"""Context compaction workflow for token-efficient memory summaries."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from brainstem.models import (
    CompactRequest,
    CompactResponse,
    RecallRequest,
    RememberRequest,
    TrustLevel,
)
from brainstem.service import estimate_tokens
from brainstem.store import MemoryRepository


def _snippet_score(*, salience: float, confidence: float, created_at: datetime) -> float:
    age_hours = max(0.0, (datetime.now(UTC) - created_at).total_seconds() / 3600.0)
    recency_bonus = 1.0 / (1.0 + (age_hours / 24.0))
    return salience * 0.50 + confidence * 0.35 + recency_bonus * 0.15


def _split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text.strip())
    return [chunk.strip() for chunk in chunks if chunk and chunk.strip()]


def _normalize_sentence(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return normalized.strip(" .!?")


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    words = text.split()
    approx_word_limit = max(1, int(max_tokens / 1.3))
    if len(words) <= approx_word_limit:
        return text.strip()
    clipped = " ".join(words[:approx_word_limit]).strip()
    return f"{clipped} ..."


def _compose_summary(
    *,
    request: CompactRequest,
    source_items: list[tuple[str, str, float, float, datetime]],
) -> tuple[str, int, list[str], bool]:
    header = f'Compacted context for query "{request.query.strip()}":'
    header_tokens = estimate_tokens(header)
    if header_tokens >= request.target_tokens:
        trimmed_header = _truncate_to_tokens(header, request.target_tokens)
        output_tokens = estimate_tokens(trimmed_header) if trimmed_header else 0
        return trimmed_header, output_tokens, [], True

    ordered = sorted(
        source_items,
        key=lambda item: _snippet_score(
            salience=item[2],
            confidence=item[3],
            created_at=item[4],
        ),
        reverse=True,
    )

    tokens = header_tokens
    lines: list[str] = []
    used_ids: list[str] = []
    used_ids_set: set[str] = set()
    seen_sentences: set[str] = set()
    truncated = False
    for memory_id, text, _salience, _confidence, _created_at in ordered:
        snippet_used = False
        for sentence in _split_sentences(text):
            normalized = _normalize_sentence(sentence)
            if not normalized or normalized in seen_sentences:
                continue
            candidate = f"- {sentence}"
            candidate_tokens = estimate_tokens(candidate)
            if tokens + candidate_tokens > request.target_tokens:
                truncated = True
                continue
            lines.append(candidate)
            tokens += candidate_tokens
            seen_sentences.add(normalized)
            snippet_used = True
        if snippet_used and memory_id not in used_ids_set:
            used_ids.append(memory_id)
            used_ids_set.add(memory_id)

    if not lines and ordered:
        available_body_tokens = max(1, request.target_tokens - header_tokens)
        fallback = _truncate_to_tokens(ordered[0][1], available_body_tokens)
        if fallback:
            lines.append(f"- {fallback}")
            used_ids = [ordered[0][0]]
            tokens = estimate_tokens(header) + estimate_tokens(lines[0])
            truncated = True

    if not lines:
        return "", 0, [], True

    summary_text = "\n".join([header, *lines])
    return summary_text, estimate_tokens(summary_text), used_ids, truncated


def compact_context(repository: MemoryRepository, payload: CompactRequest) -> CompactResponse:
    recall = repository.recall(
        RecallRequest.model_validate(
            {
                "tenant_id": payload.tenant_id,
                "agent_id": payload.agent_id,
                "scope": payload.scope,
                "query": payload.query,
                "budget": {
                    "max_items": payload.max_source_items,
                    "max_tokens": payload.input_max_tokens,
                },
            }
        )
    )

    source_items = [
        (
            item.memory_id,
            item.text,
            item.salience,
            item.confidence,
            item.created_at,
        )
        for item in recall.items
    ]
    input_tokens = sum(estimate_tokens(item[1]) for item in source_items)
    if not source_items:
        return CompactResponse(
            created_memory_id=None,
            source_memory_ids=[],
            source_count=0,
            input_tokens_estimate=0,
            output_tokens_estimate=0,
            reduction_ratio=0.0,
            summary_text="",
            warnings=["no_source_memories"],
        )

    summary_text, output_tokens, source_memory_ids, truncated = _compose_summary(
        request=payload,
        source_items=source_items,
    )
    warnings: list[str] = []
    if not summary_text:
        return CompactResponse(
            created_memory_id=None,
            source_memory_ids=[],
            source_count=0,
            input_tokens_estimate=input_tokens,
            output_tokens_estimate=0,
            reduction_ratio=0.0,
            summary_text="",
            warnings=["summary_generation_failed"],
        )
    if truncated:
        warnings.append("summary_truncated")
    if output_tokens > payload.target_tokens:
        warnings.append("summary_over_target_tokens")

    source_hint = ",".join(source_memory_ids[:3])
    source_ref = payload.source_ref or f"compaction:{len(source_memory_ids)}:{source_hint}"
    remember_payload = RememberRequest.model_validate(
        {
            "tenant_id": payload.tenant_id,
            "agent_id": payload.agent_id,
            "scope": payload.scope,
            "items": [
                {
                    "type": payload.output_type.value,
                    "text": summary_text,
                    "trust_level": TrustLevel.TRUSTED_TOOL.value,
                    "source_ref": source_ref[:512],
                    "expires_at": (
                        payload.expires_at.isoformat() if payload.expires_at is not None else None
                    ),
                }
            ],
        }
    )
    remember_result = repository.remember(remember_payload)
    created_memory_id = remember_result.memory_ids[0] if remember_result.memory_ids else None

    reduction_ratio = 0.0
    if input_tokens > 0:
        reduction_ratio = max(0.0, min(1.0, 1.0 - (output_tokens / input_tokens)))

    return CompactResponse(
        created_memory_id=created_memory_id,
        source_memory_ids=source_memory_ids,
        source_count=len(source_memory_ids),
        input_tokens_estimate=input_tokens,
        output_tokens_estimate=output_tokens,
        reduction_ratio=round(reduction_ratio, 4),
        summary_text=summary_text,
        warnings=warnings,
    )
