"""Canary model registry for reranker/salience rollout."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any


@dataclass(slots=True)
class SignalRecord:
    version: str
    metric: str
    value: float
    source: str | None
    created_at: datetime


@dataclass(slots=True)
class ModelState:
    active_version: str
    canary_version: str | None = None
    rollout_percent: int = 0
    tenant_allowlist: set[str] = field(default_factory=set)
    signals: list[SignalRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ModelRegistry:
    def __init__(self) -> None:
        self._lock = RLock()
        self._states: dict[str, ModelState] = {
            "reranker": ModelState(active_version="reranker-baseline-v1"),
            "salience": ModelState(active_version="salience-baseline-v1"),
        }

    def get_state(self, model_kind: str) -> dict[str, Any]:
        with self._lock:
            state = self._require_state(model_kind)
            return self._serialize_state(model_kind, state)

    def register_canary(
        self,
        model_kind: str,
        version: str,
        rollout_percent: int = 10,
        tenant_allowlist: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if rollout_percent < 0 or rollout_percent > 100:
            raise ValueError("rollout_percent_out_of_range")

        with self._lock:
            state = self._require_state(model_kind)
            state.canary_version = version
            state.rollout_percent = rollout_percent
            state.tenant_allowlist = set(tenant_allowlist or [])
            state.metadata = metadata or {}
            state.updated_at = datetime.now(UTC)
            return self._serialize_state(model_kind, state)

    def promote_canary(self, model_kind: str) -> dict[str, Any]:
        with self._lock:
            state = self._require_state(model_kind)
            if state.canary_version is None:
                raise ValueError("canary_not_set")
            state.active_version = state.canary_version
            state.canary_version = None
            state.rollout_percent = 0
            state.tenant_allowlist = set()
            state.updated_at = datetime.now(UTC)
            return self._serialize_state(model_kind, state)

    def rollback_canary(self, model_kind: str) -> dict[str, Any]:
        with self._lock:
            state = self._require_state(model_kind)
            state.canary_version = None
            state.rollout_percent = 0
            state.tenant_allowlist = set()
            state.updated_at = datetime.now(UTC)
            return self._serialize_state(model_kind, state)

    def record_signal(
        self,
        model_kind: str,
        version: str,
        metric: str,
        value: float,
        source: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._require_state(model_kind)
            state.signals.append(
                SignalRecord(
                    version=version,
                    metric=metric,
                    value=value,
                    source=source,
                    created_at=datetime.now(UTC),
                )
            )
            state.signals = state.signals[-500:]
            state.updated_at = datetime.now(UTC)
            return self._serialize_state(model_kind, state)

    def select_version(self, model_kind: str, tenant_id: str) -> tuple[str, str]:
        with self._lock:
            state = self._require_state(model_kind)
            if state.canary_version is None:
                return state.active_version, "active"
            if tenant_id in state.tenant_allowlist:
                return state.canary_version, "canary_allowlist"
            if state.rollout_percent <= 0:
                return state.active_version, "active"
            bucket = _stable_bucket(key=f"{model_kind}:{tenant_id}")
            if bucket < state.rollout_percent:
                return state.canary_version, "canary_percent"
            return state.active_version, "active"

    def _require_state(self, model_kind: str) -> ModelState:
        if model_kind not in self._states:
            raise ValueError("unsupported_model_kind")
        return self._states[model_kind]

    @staticmethod
    def _serialize_state(model_kind: str, state: ModelState) -> dict[str, Any]:
        summary: dict[str, dict[str, float]] = {}
        for signal in state.signals:
            version_metrics = summary.setdefault(signal.version, {})
            key = f"{signal.metric}.avg"
            count_key = f"{signal.metric}.count"
            prior_sum = version_metrics.get(key, 0.0) * version_metrics.get(count_key, 0.0)
            prior_count = version_metrics.get(count_key, 0.0)
            new_count = prior_count + 1.0
            version_metrics[count_key] = new_count
            version_metrics[key] = (prior_sum + signal.value) / new_count

        return {
            "model_kind": model_kind,
            "active_version": state.active_version,
            "canary_version": state.canary_version,
            "rollout_percent": state.rollout_percent,
            "tenant_allowlist": sorted(state.tenant_allowlist),
            "metadata": state.metadata,
            "signal_summary": summary,
            "updated_at": state.updated_at.isoformat(),
        }


def _stable_bucket(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100
