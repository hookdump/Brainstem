"""Brainstem command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from brainstem.admin import init_postgres_db, init_sqlite_db
from brainstem.benchmark import run_benchmark
from brainstem.leaderboard import write_leaderboard_artifacts
from brainstem.main import run as run_api
from brainstem.reporting import generate_benchmark_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Brainstem operations CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("serve-api", help="Run Brainstem API server")

    sqlite = subparsers.add_parser("init-sqlite", help="Initialize SQLite database")
    sqlite.add_argument("--db", default="brainstem.db")
    sqlite.add_argument("--migration", default="migrations/0001_initial.sql")

    postgres = subparsers.add_parser("init-postgres", help="Initialize Postgres database")
    postgres.add_argument("--dsn", required=True)
    postgres.add_argument("--migration", default="migrations/0002_postgres_pgvector.sql")

    benchmark = subparsers.add_parser("benchmark", help="Run retrieval benchmark")
    benchmark.add_argument("--dataset", default="benchmarks/retrieval_dataset.json")
    benchmark.add_argument("--backend", choices=["inmemory", "sqlite"], default="inmemory")
    benchmark.add_argument("--sqlite-path", default=".data/benchmark.db")
    benchmark.add_argument("--k", type=int, default=5)
    benchmark.add_argument("--output-json", default="")
    benchmark.add_argument("--graph-enabled", action="store_true")
    benchmark.add_argument("--graph-max-expansion", type=int, default=4)

    report = subparsers.add_parser("report", help="Generate benchmark markdown report")
    report.add_argument("--dataset", default="benchmarks/retrieval_dataset.json")
    report.add_argument("--output-md", default="reports/retrieval_benchmark.md")
    report.add_argument("--sqlite-path", default=".data/benchmark-report.db")
    report.add_argument("--k", type=int, default=5)

    leaderboard = subparsers.add_parser(
        "leaderboard",
        help="Generate benchmark leaderboard JSON and markdown artifacts",
    )
    leaderboard.add_argument("--manifest", default="benchmarks/suite_manifest.json")
    leaderboard.add_argument("--output-dir", default="reports/leaderboard")
    leaderboard.add_argument("--sqlite-dir", default=".data/leaderboard")

    health = subparsers.add_parser("health", help="Run HTTP health check")
    health.add_argument("--url", default="http://localhost:8080/healthz")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "serve-api":
        run_api()
        return 0

    if args.command == "init-sqlite":
        path = init_sqlite_db(db_path=args.db, migration_path=args.migration)
        print(f"Initialized SQLite DB at {path}")
        return 0

    if args.command == "init-postgres":
        init_postgres_db(dsn=args.dsn, migration_path=args.migration)
        print(f"Applied migration {args.migration} to Postgres")
        return 0

    if args.command == "benchmark":
        result = run_benchmark(
            dataset_path=args.dataset,
            backend=args.backend,
            sqlite_path=args.sqlite_path,
            k=args.k,
            graph_enabled=args.graph_enabled,
            graph_max_expansion=args.graph_max_expansion,
        )
        if args.output_json:
            output = Path(args.output_json)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(f"Wrote benchmark output to {output}")
        print(json.dumps(result["metrics"], indent=2))
        return 0

    if args.command == "report":
        output = generate_benchmark_report(
            dataset=args.dataset,
            output_md=args.output_md,
            k=args.k,
            sqlite_path=args.sqlite_path,
        )
        print(f"Wrote benchmark report to {output}")
        return 0

    if args.command == "leaderboard":
        json_path, md_path = write_leaderboard_artifacts(
            manifest_path=args.manifest,
            output_dir=args.output_dir,
            sqlite_dir=args.sqlite_dir,
        )
        print(f"Wrote leaderboard JSON to {json_path}")
        print(f"Wrote leaderboard markdown to {md_path}")
        return 0

    if args.command == "health":
        try:
            with urlopen(args.url, timeout=5) as response:
                payload = response.read().decode("utf-8")
            print(payload)
            return 0
        except URLError as exc:
            print(f"Health check failed: {exc}", file=sys.stderr)
            return 1

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
