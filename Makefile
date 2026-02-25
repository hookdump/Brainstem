.PHONY: install lint test run-api run-worker run-mcp docker-up docker-down docker-logs docker-smoke benchmark report leaderboard perf-regression backup-sqlite restore-sqlite verify-restore-sqlite release-prep

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev,postgres,mcp]"

lint:
	.venv/bin/ruff check .

test:
	.venv/bin/pytest -q

run-api:
	.venv/bin/brainstem serve-api

run-worker:
	PYTHONPATH=src .venv/bin/python scripts/job_worker.py

run-mcp:
	PYTHONPATH=src .venv/bin/python scripts/mcp_server.py

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api

docker-smoke:
	bash scripts/smoke_docker_stack.sh

benchmark:
	.venv/bin/brainstem benchmark --backend inmemory --k 5

report:
	.venv/bin/brainstem report --dataset benchmarks/retrieval_dataset.json --output-md reports/retrieval_benchmark.md --k 5

leaderboard:
	.venv/bin/brainstem leaderboard --manifest benchmarks/suite_manifest.json --output-dir reports/leaderboard --sqlite-dir .data/leaderboard

perf-regression:
	.venv/bin/brainstem perf-regression --output-json reports/performance/perf_regression.json --output-md reports/performance/perf_regression.md

backup-sqlite:
	bash scripts/backup_sqlite.sh --memory-db .data/brainstem.db --registry-db .data/model_registry.db --out-dir backups/sqlite/latest

restore-sqlite:
	bash scripts/restore_sqlite.sh --backup-dir backups/sqlite/latest --memory-db .data/brainstem.db --registry-db .data/model_registry.db

verify-restore-sqlite:
	PYTHONPATH=src .venv/bin/python scripts/verify_sqlite_restore.py --work-dir .data/restore-verify --output-json .data/restore-verify/verification.json

release-prep:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make release-prep VERSION=0.2.0"; exit 1; fi
	PYTHONPATH=src .venv/bin/python scripts/prepare_release.py --version $(VERSION)
