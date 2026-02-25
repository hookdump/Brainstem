from __future__ import annotations

from brainstem.vector import EMBEDDING_DIM, hashed_embedding, vector_literal


def test_hashed_embedding_shape_and_normalization() -> None:
    values = hashed_embedding("alpha beta gamma alpha")
    assert len(values) == EMBEDDING_DIM
    squared_norm = sum(value * value for value in values)
    assert 0.99 <= squared_norm <= 1.01


def test_vector_literal_format() -> None:
    literal = vector_literal([0.5, 0.25, 0.0])
    assert literal == "[0.500000,0.250000,0.000000]"
