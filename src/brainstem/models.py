"""API and domain models for Brainstem v0."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Scope(StrEnum):
    PRIVATE = "private"
    TEAM = "team"
    GLOBAL = "global"


class MemoryType(StrEnum):
    EVENT = "event"
    FACT = "fact"
    EPISODE = "episode"
    POLICY = "policy"


class TrustLevel(StrEnum):
    TRUSTED_TOOL = "trusted_tool"
    USER_CLAIM = "user_claim"
    UNTRUSTED_WEB = "untrusted_web"


class RememberInputItem(BaseModel):
    type: MemoryType
    text: str = Field(min_length=1, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=512)
    trust_level: TrustLevel = TrustLevel.USER_CLAIM
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    salience: float | None = Field(default=None, ge=0.0, le=1.0)
    expires_at: datetime | None = None


class RememberRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    scope: Scope = Scope.PRIVATE
    items: list[RememberInputItem] = Field(min_length=1, max_length=100)
    idempotency_key: str | None = Field(default=None, max_length=128)


class RememberResponse(BaseModel):
    accepted: int
    rejected: int
    memory_ids: list[str]
    warnings: list[str]


class RecallBudget(BaseModel):
    max_items: int = Field(default=12, ge=1, le=100)
    max_tokens: int = Field(default=1400, ge=64, le=32000)


class RecallFilters(BaseModel):
    trust_min: float = Field(default=0.0, ge=0.0, le=1.0)
    types: list[MemoryType] | None = None


class RecallRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=1024)
    scope: Scope = Scope.PRIVATE
    budget: RecallBudget = Field(default_factory=RecallBudget)
    filters: RecallFilters = Field(default_factory=RecallFilters)


class MemorySnippet(BaseModel):
    memory_id: str
    type: MemoryType
    text: str
    confidence: float
    salience: float
    source_ref: str | None
    created_at: datetime


class RecallResponse(BaseModel):
    items: list[MemorySnippet]
    composed_tokens_estimate: int
    conflicts: list[str]
    trace_id: str


class ReflectRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)
    window_hours: int = Field(default=24, ge=1, le=168)
    max_candidates: int = Field(default=8, ge=1, le=32)


class ReflectResponse(BaseModel):
    job_id: str
    status: Literal["queued", "completed"]
    candidate_facts: list[str]


class TrainRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    model_kind: Literal["reranker", "salience"]
    lookback_days: int = Field(default=14, ge=1, le=180)


class TrainResponse(BaseModel):
    job_id: str
    status: Literal["queued"]
    notes: str


class ForgetRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    agent_id: str = Field(min_length=1, max_length=128)


class ForgetResponse(BaseModel):
    memory_id: str
    deleted: bool


class MemoryDetails(BaseModel):
    memory_id: str
    tenant_id: str
    agent_id: str
    type: MemoryType
    scope: Scope
    text: str
    trust_level: TrustLevel
    confidence: float
    salience: float
    source_ref: str | None
    created_at: datetime
    expires_at: datetime | None = None


class JobStatusResponse(BaseModel):
    job_id: str
    kind: Literal["reflect", "train", "cleanup"]
    status: Literal["queued", "running", "completed", "failed"]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
