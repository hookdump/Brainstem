.PHONY: install lint test run-api run-mcp docker-up docker-down docker-logs docker-smoke benchmark report

install:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev,postgres,mcp]"

lint:
	.venv/bin/ruff check .

test:
	.venv/bin/pytest -q

run-api:
	.venv/bin/brainstem-api

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
	PYTHONPATH=src .venv/bin/python scripts/benchmark_recall.py --backend inmemory --k 5

report:
	PYTHONPATH=src .venv/bin/python scripts/generate_benchmark_report.py --dataset benchmarks/retrieval_dataset.json --output-md reports/retrieval_benchmark.md --k 5
