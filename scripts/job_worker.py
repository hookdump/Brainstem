#!/usr/bin/env python3
"""Brainstem distributed job worker."""

from __future__ import annotations

import argparse
import signal
import time

from brainstem.jobs import JobManager
from brainstem.settings import Settings, load_settings
from brainstem.store import InMemoryRepository, MemoryRepository, SQLiteRepository
from brainstem.store_postgres import PostgresRepository


def _create_repository(settings: Settings) -> MemoryRepository:
    if settings.store_backend == "inmemory":
        return InMemoryRepository()
    if settings.store_backend == "sqlite":
        return SQLiteRepository(settings.sqlite_path)
    if settings.store_backend == "postgres":
        if not settings.postgres_dsn:
            raise ValueError(
                "BRAINSTEM_POSTGRES_DSN is required when BRAINSTEM_STORE_BACKEND=postgres"
            )
        return PostgresRepository(settings.postgres_dsn)
    raise ValueError(f"unsupported BRAINSTEM_STORE_BACKEND: {settings.store_backend}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Brainstem async job worker.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one queued job and exit.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.2,
        help="Polling interval in seconds when queue is empty.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = load_settings()
    if settings.job_backend != "sqlite":
        raise SystemExit(
            "Worker process requires BRAINSTEM_JOB_BACKEND=sqlite for shared queue mode."
        )

    manager = JobManager(
        repository=_create_repository(settings),
        sqlite_path=settings.job_sqlite_path,
        start_worker=False,
        poll_interval_s=args.poll_interval,
    )

    stop = {"value": False}

    def _signal_handler(_signum: int, _frame: object) -> None:
        stop["value"] = True
        manager.close()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        if args.once:
            processed = manager.process_next()
            print("processed" if processed else "idle")
            return 0

        while not stop["value"]:
            processed = manager.process_next()
            if not processed:
                time.sleep(args.poll_interval)
        return 0
    finally:
        manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
