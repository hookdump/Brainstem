"""Memory scoring utilities."""

from __future__ import annotations

import re

from brainstem.models import MemoryType, TrustLevel

_HIGH_IMPORTANCE_TOKENS = {
    "must",
    "required",
    "deadline",
    "blocked",
    "constraint",
    "critical",
    "policy",
    "security",
    "cannot",
}

_LOW_CONFIDENCE_TOKENS = {"maybe", "might", "possibly", "unsure", "guess"}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def estimate_tokens(text: str) -> int:
    # Rough approximation to keep request packing deterministic.
    words = len(re.findall(r"\w+", text))
    return max(1, int(words * 1.3))


def infer_salience(text: str, memory_type: MemoryType, provided: float | None = None) -> float:
    if provided is not None:
        return clamp(provided)

    base = {
        MemoryType.EVENT: 0.45,
        MemoryType.FACT: 0.70,
        MemoryType.EPISODE: 0.60,
        MemoryType.POLICY: 0.90,
    }[memory_type]
    lowered = text.lower()
    token_boost = sum(token in lowered for token in _HIGH_IMPORTANCE_TOKENS) * 0.03
    return clamp(base + token_boost, low=0.05, high=0.99)


def infer_confidence(
    text: str, trust_level: TrustLevel, provided: float | None = None
) -> float:
    if provided is not None:
        return clamp(provided)

    base = {
        TrustLevel.TRUSTED_TOOL: 0.82,
        TrustLevel.USER_CLAIM: 0.66,
        TrustLevel.UNTRUSTED_WEB: 0.38,
    }[trust_level]
    lowered = text.lower()
    uncertainty_penalty = sum(token in lowered for token in _LOW_CONFIDENCE_TOKENS) * 0.05
    return clamp(base - uncertainty_penalty, low=0.05, high=0.98)


def trust_score(trust_level: TrustLevel | str) -> float:
    key = trust_level.value if isinstance(trust_level, TrustLevel) else trust_level
    return {
        "trusted_tool": 1.0,
        "user_claim": 0.7,
        "untrusted_web": 0.35,
    }[key]
