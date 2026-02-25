"""Performance regression utilities."""

from __future__ import annotations

import gc
import json
import math
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

import anyio

from brainstem.api import create_app
from brainstem.auth import AuthManager, AuthMode
from brainstem.store import InMemoryRepository


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    bounded = min(100.0, max(0.0, pct))
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(values)
    index = max(0, math.ceil((bounded / 100.0) * len(sorted_values)) - 1)
    return float(sorted_values[index])


def _latency_summary(latencies: list[float]) -> dict[str, float]:
    return {
        "count": float(len(latencies)),
        "avg": float(mean(latencies)) if latencies else 0.0,
        "p50": percentile(latencies, 50.0),
        "p95": percentile(latencies, 95.0),
        "p99": percentile(latencies, 99.0),
    }


async def _run_performance_regression_async(
    iterations: int,
    seed_count: int,
) -> dict[str, Any]:
    import httpx

    app = create_app(
        repository=InMemoryRepository(),
        auth_manager=AuthManager(mode=AuthMode.DISABLED),
    )
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://perf.test")

    tenant_id = "t_perf"
    agent_id = "a_perf"
    remember_latencies_ms: list[float] = []
    recall_latencies_ms: list[float] = []

    gc.collect()
    tracemalloc.start()
    start_current, start_peak = tracemalloc.get_traced_memory()

    async with client:
        for idx in range(max(0, seed_count)):
            await client.post(
                "/v0/memory/remember",
                json={
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "scope": "team",
                    "items": [
                        {
                            "type": "fact",
                            "text": (
                                "Seeded performance baseline fact "
                                f"{idx}: rollout constraints and incident policy."
                            ),
                            "trust_level": "trusted_tool",
                        }
                    ],
                },
            )

        for idx in range(max(0, iterations)):
            remember_started = perf_counter()
            remember_response = await client.post(
                "/v0/memory/remember",
                json={
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "scope": "team",
                    "items": [
                        {
                            "type": "fact",
                            "text": (
                                "Sustained remember workload fact "
                                f"{idx}: migration, pager, and budget context."
                            ),
                            "trust_level": "trusted_tool",
                        }
                    ],
                },
            )
            remember_response.raise_for_status()
            remember_latencies_ms.append((perf_counter() - remember_started) * 1000.0)

            recall_started = perf_counter()
            recall_response = await client.post(
                "/v0/memory/recall",
                json={
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "scope": "team",
                    "query": "What migration, pager, and budget constraints are known?",
                    "budget": {"max_items": 10, "max_tokens": 2000},
                },
            )
            recall_response.raise_for_status()
            recall_latencies_ms.append((perf_counter() - recall_started) * 1000.0)

    end_current, end_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    gc.collect()

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "config": {
            "iterations": float(iterations),
            "seed_count": float(seed_count),
        },
        "metrics": {
            "remember_ms": _latency_summary(remember_latencies_ms),
            "recall_ms": _latency_summary(recall_latencies_ms),
        },
        "memory": {
            "growth_bytes": float(max(0, end_current - start_current)),
            "peak_growth_bytes": float(max(0, end_peak - start_peak)),
        },
    }


def evaluate_budgets(
    summary: dict[str, Any],
    *,
    max_remember_p95_ms: float,
    max_recall_p95_ms: float,
    max_memory_growth_bytes: float,
) -> list[str]:
    violations: list[str] = []
    metrics = summary["metrics"]
    memory = summary["memory"]
    remember_p95 = float(metrics["remember_ms"]["p95"])
    recall_p95 = float(metrics["recall_ms"]["p95"])
    memory_growth = float(memory["growth_bytes"])

    if remember_p95 > max_remember_p95_ms:
        violations.append(
            f"remember_p95_ms_exceeded:{remember_p95:.3f}>{max_remember_p95_ms:.3f}"
        )
    if recall_p95 > max_recall_p95_ms:
        violations.append(
            f"recall_p95_ms_exceeded:{recall_p95:.3f}>{max_recall_p95_ms:.3f}"
        )
    if memory_growth > max_memory_growth_bytes:
        violations.append(
            f"memory_growth_exceeded:{memory_growth:.0f}>{max_memory_growth_bytes:.0f}"
        )
    return violations


def render_performance_markdown(
    summary: dict[str, Any],
    *,
    violations: list[str],
    budgets: dict[str, float],
) -> str:
    metrics = summary["metrics"]
    memory = summary["memory"]
    config = summary["config"]

    lines: list[str] = []
    lines.append("# Brainstem Performance Regression Report")
    lines.append("")
    lines.append(f"Generated: {summary['generated_at']}")
    lines.append(f"Iterations: {int(config['iterations'])}")
    lines.append(f"Seed count: {int(config['seed_count'])}")
    lines.append("")
    lines.append("## Latency")
    lines.append("")
    lines.append("| Operation | Avg (ms) | P50 (ms) | P95 (ms) | P99 (ms) |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    lines.append(
        f"| remember | {metrics['remember_ms']['avg']:.3f} | "
        f"{metrics['remember_ms']['p50']:.3f} | "
        f"{metrics['remember_ms']['p95']:.3f} | "
        f"{metrics['remember_ms']['p99']:.3f} |"
    )
    lines.append(
        f"| recall | {metrics['recall_ms']['avg']:.3f} | "
        f"{metrics['recall_ms']['p50']:.3f} | "
        f"{metrics['recall_ms']['p95']:.3f} | "
        f"{metrics['recall_ms']['p99']:.3f} |"
    )
    lines.append("")
    lines.append("## Memory")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    lines.append(f"| growth_bytes | {memory['growth_bytes']:.0f} |")
    lines.append(f"| peak_growth_bytes | {memory['peak_growth_bytes']:.0f} |")
    lines.append("")
    lines.append("## Budget Check")
    lines.append("")
    lines.append("| Budget | Threshold |")
    lines.append("| --- | ---: |")
    lines.append(f"| remember_p95_ms | {budgets['max_remember_p95_ms']:.3f} |")
    lines.append(f"| recall_p95_ms | {budgets['max_recall_p95_ms']:.3f} |")
    lines.append(f"| memory_growth_bytes | {budgets['max_memory_growth_bytes']:.0f} |")
    lines.append("")
    if violations:
        lines.append("Status: `FAIL`")
        lines.append("")
        lines.append("Violations:")
        for violation in violations:
            lines.append(f"- `{violation}`")
    else:
        lines.append("Status: `PASS`")
    lines.append("")
    return "\n".join(lines)


def run_performance_regression(
    *,
    iterations: int,
    seed_count: int,
    max_remember_p95_ms: float,
    max_recall_p95_ms: float,
    max_memory_growth_bytes: float,
) -> dict[str, Any]:
    summary = anyio.run(
        _run_performance_regression_async,
        iterations,
        seed_count,
    )
    violations = evaluate_budgets(
        summary,
        max_remember_p95_ms=max_remember_p95_ms,
        max_recall_p95_ms=max_recall_p95_ms,
        max_memory_growth_bytes=max_memory_growth_bytes,
    )
    return {
        "summary": summary,
        "budgets": {
            "max_remember_p95_ms": max_remember_p95_ms,
            "max_recall_p95_ms": max_recall_p95_ms,
            "max_memory_growth_bytes": max_memory_growth_bytes,
        },
        "violations": violations,
        "pass": not violations,
    }


def write_performance_artifacts(
    *,
    output_json: str,
    output_md: str,
    result: dict[str, Any],
) -> tuple[str, str]:
    output_json_path = Path(output_json)
    output_md_path = Path(output_md)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_md_path.parent.mkdir(parents=True, exist_ok=True)

    output_json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    output_md_path.write_text(
        render_performance_markdown(
            result["summary"],
            violations=result["violations"],
            budgets=result["budgets"],
        )
        + "\n",
        encoding="utf-8",
    )
    return str(output_json_path), str(output_md_path)
