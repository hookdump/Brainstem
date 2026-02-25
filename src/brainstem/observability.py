"""Simple observability primitives for Brainstem."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean
from threading import RLock
from time import perf_counter


@dataclass(frozen=True, slots=True)
class RequestMetric:
    method: str
    path: str
    status_code: int
    duration_ms: float


class MetricsStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._request_count = 0
        self._status_counts: dict[str, int] = defaultdict(int)
        self._route_counts: dict[str, int] = defaultdict(int)
        self._route_latencies: dict[str, list[float]] = defaultdict(list)
        self._pipeline_latencies: dict[str, list[float]] = defaultdict(list)

    def record(self, metric: RequestMetric) -> None:
        key = f"{metric.method} {metric.path}"
        status_bucket = f"{metric.status_code // 100}xx"
        with self._lock:
            self._request_count += 1
            self._status_counts[status_bucket] += 1
            self._route_counts[key] += 1
            self._route_latencies[key].append(metric.duration_ms)

    def record_pipeline_timing(self, stage: str, timing_ms: float) -> None:
        with self._lock:
            self._pipeline_latencies[stage].append(timing_ms)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            latency_summary = {
                route: {
                    "count": len(values),
                    "avg_ms": round(mean(values), 2),
                    "max_ms": round(max(values), 2),
                }
                for route, values in self._route_latencies.items()
                if values
            }
            pipeline_summary = {
                stage: {
                    "count": len(values),
                    "avg_ms": round(mean(values), 2),
                    "max_ms": round(max(values), 2),
                }
                for stage, values in self._pipeline_latencies.items()
                if values
            }
            return {
                "request_count": self._request_count,
                "status_counts": dict(self._status_counts),
                "route_counts": dict(self._route_counts),
                "route_latency_ms": latency_summary,
                "pipeline_latency_ms": pipeline_summary,
            }


def duration_ms(start_time: float) -> float:
    return (perf_counter() - start_time) * 1000.0
