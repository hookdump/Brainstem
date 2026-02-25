#!/usr/bin/env python3
"""Brainstem REST showcase script."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _request_json(
    *,
    base_url: str,
    path: str,
    method: str,
    payload: dict[str, Any] | None,
    params: dict[str, str] | None,
    api_key: str | None,
) -> dict[str, Any]:
    query = ""
    if params:
        query = "?" + urllib.parse.urlencode(params)
    url = base_url.rstrip("/") + path + query

    headers = {"content-type": "application/json"}
    if api_key:
        headers["x-brainstem-api-key"] = api_key

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(url=url, method=method, headers=headers, data=data)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc


def _print_step(title: str, payload: dict[str, Any]) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2))


def run(args: argparse.Namespace) -> int:
    tenant_id = args.tenant_id
    agent_a = args.agent_a
    agent_b = args.agent_b
    scope = args.scope

    remember_a = _request_json(
        base_url=args.base_url,
        path="/v0/memory/remember",
        method="POST",
        api_key=args.api_key,
        params=None,
        payload={
            "tenant_id": tenant_id,
            "agent_id": agent_a,
            "scope": scope,
            "items": [
                {
                    "type": "fact",
                    "text": "Service rollout must finish before Friday planning review.",
                    "trust_level": "trusted_tool",
                    "source_ref": "demo:rollout:constraint",
                },
                {
                    "type": "policy",
                    "text": "Pager rota for overnight incidents starts at #ops-oncall.",
                    "trust_level": "trusted_tool",
                    "source_ref": "demo:policy:pager",
                },
            ],
        },
    )
    _print_step("Remember (agent-a)", remember_a)

    remember_b = _request_json(
        base_url=args.base_url,
        path="/v0/memory/remember",
        method="POST",
        api_key=args.api_key,
        params=None,
        payload={
            "tenant_id": tenant_id,
            "agent_id": agent_b,
            "scope": scope,
            "items": [
                {
                    "type": "fact",
                    "text": "Budget alert threshold is 18 percent week-over-week increase.",
                    "trust_level": "trusted_tool",
                    "source_ref": "demo:billing:threshold",
                }
            ],
        },
    )
    _print_step("Remember (agent-b)", remember_b)

    recall = _request_json(
        base_url=args.base_url,
        path="/v0/memory/recall",
        method="POST",
        api_key=args.api_key,
        params=None,
        payload={
            "tenant_id": tenant_id,
            "agent_id": agent_a,
            "scope": scope,
            "query": "Summarize rollout constraints, pager path, and budget alerts.",
            "budget": {"max_items": 6, "max_tokens": 1500},
        },
    )
    _print_step("Recall", recall)

    first_memory_id = str(recall["items"][0]["memory_id"])
    inspect = _request_json(
        base_url=args.base_url,
        path=f"/v0/memory/{first_memory_id}",
        method="GET",
        api_key=args.api_key,
        params={"tenant_id": tenant_id, "agent_id": agent_a, "scope": scope},
        payload=None,
    )
    _print_step("Inspect first recalled memory", inspect)

    if args.reflect:
        reflect = _request_json(
            base_url=args.base_url,
            path="/v0/memory/reflect",
            method="POST",
            api_key=args.api_key,
            params=None,
            payload={
                "tenant_id": tenant_id,
                "agent_id": agent_a,
                "window_hours": 24,
                "max_candidates": 4,
            },
        )
        _print_step("Reflect submit", reflect)
        job_id = str(reflect["job_id"])
        final_status: dict[str, Any] | None = None
        for _ in range(args.reflect_polls):
            status = _request_json(
                base_url=args.base_url,
                path=f"/v0/jobs/{job_id}",
                method="GET",
                api_key=args.api_key,
                params={"tenant_id": tenant_id, "agent_id": agent_a},
                payload=None,
            )
            final_status = status
            if status.get("status") in {"completed", "failed"}:
                break
            time.sleep(args.reflect_poll_interval)
        if final_status is not None:
            _print_step("Reflect final status", final_status)

    print("\nDemo complete.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Brainstem REST showcase.")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--tenant-id", default="t_demo_showcase")
    parser.add_argument("--agent-a", default="a_demo_writer")
    parser.add_argument(
        "--agent-b",
        default="a_demo_writer",
        help="Use a different id to showcase multi-agent memory sharing.",
    )
    parser.add_argument("--scope", default="team", choices=["private", "team", "global"])
    parser.add_argument("--reflect", action="store_true")
    parser.add_argument("--reflect-polls", type=int, default=30)
    parser.add_argument("--reflect-poll-interval", type=float, default=0.1)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as exc:
        print(f"Demo failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

