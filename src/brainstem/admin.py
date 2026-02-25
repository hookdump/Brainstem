"""Administrative utility functions for Brainstem."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def init_sqlite_db(db_path: str, migration_path: str) -> str:
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    sql = Path(migration_path).read_text(encoding="utf-8")
    connection = sqlite3.connect(str(db_file))
    try:
        connection.executescript(sql)
        connection.commit()
    finally:
        connection.close()
    return str(db_file)


def init_postgres_db(dsn: str, migration_path: str) -> None:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "psycopg is required for Postgres admin operations. "
            "Install with `pip install -e \".[postgres]\"`."
        ) from exc

    sql = Path(migration_path).read_text(encoding="utf-8")
    with psycopg.connect(dsn, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql)
