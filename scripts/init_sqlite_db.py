#!/usr/bin/env python3
"""Initialize Brainstem SQLite database using migration SQL."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize Brainstem SQLite DB.")
    parser.add_argument("--db", default="brainstem.db", help="Path to SQLite database file.")
    parser.add_argument(
        "--migration",
        default="migrations/0001_initial.sql",
        help="Path to SQL migration file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sql = Path(args.migration).read_text(encoding="utf-8")
    connection = sqlite3.connect(str(db_path))
    try:
        connection.executescript(sql)
        connection.commit()
    finally:
        connection.close()
    print(f"Initialized SQLite DB at {db_path}")


if __name__ == "__main__":
    main()
