from __future__ import annotations

import pytest

from brainstem.api import create_app
from brainstem.settings import Settings


def test_postgres_backend_requires_dsn() -> None:
    with pytest.raises(ValueError, match="BRAINSTEM_POSTGRES_DSN"):
        create_app(
            settings=Settings(
                store_backend="postgres",
                sqlite_path="brainstem.db",
                postgres_dsn=None,
                auth_mode="disabled",
                api_keys_json=None,
                job_backend="inprocess",
                job_sqlite_path=".data/jobs.db",
                job_worker_enabled=True,
                graph_enabled=False,
                graph_max_expansion=4,
                graph_half_life_hours=168.0,
                graph_relation_weights_json=None,
                model_registry_backend="sqlite",
                model_registry_sqlite_path=".data/model_registry.db",
                model_registry_signal_window=500,
            )
        )


def test_unknown_backend_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported BRAINSTEM_STORE_BACKEND"):
        create_app(
            settings=Settings(
                store_backend="unknown",
                sqlite_path="brainstem.db",
                postgres_dsn=None,
                auth_mode="disabled",
                api_keys_json=None,
                job_backend="inprocess",
                job_sqlite_path=".data/jobs.db",
                job_worker_enabled=True,
                graph_enabled=False,
                graph_max_expansion=4,
                graph_half_life_hours=168.0,
                graph_relation_weights_json=None,
                model_registry_backend="sqlite",
                model_registry_sqlite_path=".data/model_registry.db",
                model_registry_signal_window=500,
            )
        )


def test_unknown_job_backend_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported BRAINSTEM_JOB_BACKEND"):
        create_app(
            settings=Settings(
                store_backend="inmemory",
                sqlite_path="brainstem.db",
                postgres_dsn=None,
                auth_mode="disabled",
                api_keys_json=None,
                job_backend="unknown",
                job_sqlite_path=".data/jobs.db",
                job_worker_enabled=True,
                graph_enabled=False,
                graph_max_expansion=4,
                graph_half_life_hours=168.0,
                graph_relation_weights_json=None,
                model_registry_backend="sqlite",
                model_registry_sqlite_path=".data/model_registry.db",
                model_registry_signal_window=500,
            )
        )


def test_unknown_model_registry_backend_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported BRAINSTEM_MODEL_REGISTRY_BACKEND"):
        create_app(
            settings=Settings(
                store_backend="inmemory",
                sqlite_path="brainstem.db",
                postgres_dsn=None,
                auth_mode="disabled",
                api_keys_json=None,
                job_backend="inprocess",
                job_sqlite_path=".data/jobs.db",
                job_worker_enabled=True,
                graph_enabled=False,
                graph_max_expansion=4,
                graph_half_life_hours=168.0,
                graph_relation_weights_json=None,
                model_registry_backend="unknown",
                model_registry_sqlite_path=".data/model_registry.db",
                model_registry_signal_window=500,
            )
        )
