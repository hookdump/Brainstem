"""Runtime settings for Brainstem."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    store_backend: str
    sqlite_path: str
    postgres_dsn: str | None
    auth_mode: str
    api_keys_json: str | None


def load_settings() -> Settings:
    return Settings(
        store_backend=os.getenv("BRAINSTEM_STORE_BACKEND", "inmemory").lower(),
        sqlite_path=os.getenv("BRAINSTEM_SQLITE_PATH", "brainstem.db"),
        postgres_dsn=os.getenv("BRAINSTEM_POSTGRES_DSN"),
        auth_mode=os.getenv("BRAINSTEM_AUTH_MODE", "disabled").lower(),
        api_keys_json=os.getenv("BRAINSTEM_API_KEYS"),
    )
