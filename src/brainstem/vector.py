"""Deterministic lightweight embeddings for pgvector baseline."""

from __future__ import annotations

import math
import re

EMBEDDING_DIM = 1536


def hashed_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    values = [0.0] * dim
    tokens = re.findall(r"\w+", text.lower())
    if not tokens:
        return values

    for token in tokens:
        index = hash(token) % dim
        values[index] += 1.0

    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0:
        return values
    return [value / norm for value in values]


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in values) + "]"
