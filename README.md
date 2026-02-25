<img width="2816" height="1536" alt="BRAINSTEM" src="https://github.com/user-attachments/assets/0cb59bfe-f95a-4571-9598-3416933eae86" />

Brainstem is a shared memory coprocessor for AI agents.

It lets multiple agents store, retrieve, and reuse context across sessions with:

- durable memory storage,
- scope-aware access (`private`, `team`, `global`),
- retrieval packing under token budgets,
- provenance and trust fields on memory items,
- optional API-key authorization with tenant/role enforcement.

## Current capabilities (v0)

- REST API with endpoints:
  - `remember`, `recall`, `compact`, `inspect`, `forget`, `reflect`, `train`
- Storage backends:
  - `inmemory` (fast local dev)
  - `sqlite` (persistent local baseline)
  - `postgres` (pgvector-enabled baseline)
- Postgres vector support:
  - deterministic hashed embeddings persisted to pgvector
  - vector-assisted candidate ordering for recall
- Role model:
  - `reader`, `writer`, `admin`
- Async job pipeline:
  - queued background execution for `reflect` and `train`
  - queued retention cleanup jobs
  - retry attempts + dead-letter tracking for failed jobs
  - status polling via job endpoint
- Memory quality baseline:
  - heuristic salience/confidence
  - contradiction signaling in recall output
  - retention support with `expires_at`
- Observability baseline:
  - per-route request counters and latency summaries
  - recall stage timings (`recall.auth`, `recall.store`)
  - `GET /v0/metrics` endpoint
- Tooling:
  - migration script for SQLite
  - retrieval benchmark harness (Recall@K, nDCG, token estimate)
  - MCP tool-service adapter and server entrypoint
  - MCP stdio end-to-end integration test harness
  - Docker + docker compose local stack
  - Makefile for common workflows
  - CI (`ruff` + strict `mypy` + unit tests + Postgres integration tests + MCP E2E tests)

## Quickstart

### 1) Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2) Run the API

```bash
brainstem serve-api
```

Service URL: `http://localhost:8080`

### 3) Run checks

```bash
ruff check .
PYTHONPATH=src mypy src tests
pytest
```

### 4) Containerized quickstart (Docker + Postgres + pgvector)

```bash
cp .env.example .env
docker compose up -d --build
bash scripts/smoke_docker_stack.sh
```

Stop stack:

```bash
docker compose down
```

### 5) Makefile shortcuts

```bash
make install
make lint
make typecheck
make test
make run-api
make run-worker
make docker-up
make docker-smoke
make docker-down
make leaderboard
make perf-regression
make backup-sqlite
make restore-sqlite
make verify-restore-sqlite
make release-prep VERSION=0.2.0
```

### 6) First-party CLI commands

```bash
brainstem serve-api
brainstem init-sqlite --db .data/brainstem.db
brainstem init-postgres --dsn "postgresql://postgres:postgres@localhost:5432/brainstem"
brainstem benchmark --backend sqlite --sqlite-path .data/bench.db --k 5
brainstem benchmark --dataset benchmarks/relation_heavy_dataset.json --backend sqlite --graph-enabled --k 4
brainstem report --output-md reports/retrieval_benchmark.md
brainstem leaderboard --manifest benchmarks/suite_manifest.json --output-dir reports/leaderboard
brainstem perf-regression --output-json reports/performance/perf_regression.json
brainstem health --url http://localhost:8080/healthz
```

### 7) Demo showcase

Run the sample project that writes and recalls shared context:

```bash
python demo/rest_context_showcase/run_demo.py
```

Run the coding-agent quickstart (concrete prompts + compacted context flow):

```bash
bash demo/agent_quickstart/scripts/run_quickstart.sh
```

## Configuration

Brainstem reads runtime config from environment variables:

- `BRAINSTEM_STORE_BACKEND`:
  - `inmemory` (default)
  - `sqlite`
  - `postgres`
- `BRAINSTEM_SQLITE_PATH`:
  - SQLite file path, default `brainstem.db`
- `BRAINSTEM_POSTGRES_DSN`:
  - required when backend is `postgres`
- `BRAINSTEM_AUTH_MODE`:
  - `disabled` (default)
  - `api_key`
- `BRAINSTEM_API_KEYS`:
  - required when `BRAINSTEM_AUTH_MODE=api_key`
  - JSON object mapping keys to `{tenant_id, agent_id, role}`
- `BRAINSTEM_MCP_AUTH_MODE`:
  - `token` (default)
  - `disabled` (local development only)
- `BRAINSTEM_MCP_TOKENS`:
  - required when `BRAINSTEM_MCP_AUTH_MODE=token`
  - JSON object mapping MCP tokens to `{tenant_id, agent_id, role}`
- `BRAINSTEM_JOB_BACKEND`:
  - `inprocess` (default)
  - `sqlite` (shared durable queue for multi-process workers)
- `BRAINSTEM_JOB_SQLITE_PATH`:
  - queue database path, default `.data/jobs.db`
- `BRAINSTEM_JOB_WORKER_ENABLED`:
  - `true` (default) runs embedded worker in API process
  - `false` enqueues only; use external worker process
- `BRAINSTEM_GRAPH_ENABLED`:
  - `false` (default)
  - `true` enables relation graph projection + recall expansion
- `BRAINSTEM_GRAPH_MAX_EXPANSION`:
  - max extra graph-related memories appended during recall (default `4`)
- `BRAINSTEM_GRAPH_HALF_LIFE_HOURS`:
  - recency half-life for graph edge decay (default `168`)
- `BRAINSTEM_GRAPH_RELATION_WEIGHTS`:
  - optional JSON override for relation scoring weights
  - defaults: `{"keyword":1.0,"phrase":1.4,"temporal":1.2,"reference":1.6}`
- `BRAINSTEM_MODEL_REGISTRY_BACKEND`:
  - `inmemory` (default)
  - `sqlite`
  - `postgres`
- `BRAINSTEM_MODEL_REGISTRY_SQLITE_PATH`:
  - persistent registry SQLite path, default `.data/model_registry.db`
- `BRAINSTEM_MODEL_REGISTRY_SIGNAL_WINDOW`:
  - max recent signals used for summary aggregation (default `500`)

Example:

```bash
export BRAINSTEM_STORE_BACKEND=sqlite
export BRAINSTEM_SQLITE_PATH=.data/brainstem.db
export BRAINSTEM_AUTH_MODE=api_key
export BRAINSTEM_API_KEYS='{
  "writer-key": {"tenant_id":"t_demo","agent_id":"a_writer","role":"writer"},
  "admin-key": {"tenant_id":"t_demo","agent_id":"a_admin","role":"admin"}
}'
brainstem serve-api
```

For PostgreSQL:

```bash
pip install -e ".[dev,postgres]"
export BRAINSTEM_STORE_BACKEND=postgres
export BRAINSTEM_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/brainstem"
brainstem serve-api
```

Legacy entrypoint still works:

```bash
brainstem-api
```

Optional Postgres integration test run:

```bash
export BRAINSTEM_TEST_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/brainstem"
pytest tests/test_postgres_integration.py -q
```

### Distributed async worker mode (shared SQLite queue)

Run API in enqueue-only mode:

```bash
export BRAINSTEM_JOB_BACKEND=sqlite
export BRAINSTEM_JOB_SQLITE_PATH=.data/jobs.db
export BRAINSTEM_JOB_WORKER_ENABLED=false
brainstem serve-api
```

Run worker in another terminal:

```bash
export BRAINSTEM_JOB_BACKEND=sqlite
export BRAINSTEM_JOB_SQLITE_PATH=.data/jobs.db
python scripts/job_worker.py
```

Single-shot worker run (useful for cron/k8s jobs):

```bash
python scripts/job_worker.py --once
```

## Endpoint reference

- `GET /healthz`
- `GET /v0/meta`
- `GET /v0/metrics`
- `POST /v0/memory/remember`
- `POST /v0/memory/recall`
- `POST /v0/memory/compact`
- `GET /v0/memory/{memory_id}?tenant_id=...&agent_id=...&scope=...`
- `DELETE /v0/memory/{memory_id}`
- `POST /v0/memory/reflect`
- `POST /v0/memory/train`
- `POST /v0/memory/cleanup`
- `GET /v0/jobs/{job_id}?tenant_id=...&agent_id=...`
- `GET /v0/jobs/dead_letters?tenant_id=...&agent_id=...`
- `GET /v0/models/{model_kind}?tenant_id=...&agent_id=...`
- `GET /v0/models/{model_kind}/history?tenant_id=...&agent_id=...`
- `POST /v0/models/{model_kind}/canary/register`
- `POST /v0/models/{model_kind}/canary/promote`
- `POST /v0/models/{model_kind}/canary/rollback`
- `POST /v0/models/{model_kind}/signals`

When auth mode is `api_key`, include:

```bash
-H "x-brainstem-api-key: <key>"
```

## Usage examples

### Remember

```bash
curl -s -X POST http://localhost:8080/v0/memory/remember \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "t_demo",
    "agent_id": "a_writer",
    "scope": "team",
    "items": [
      {
        "type": "fact",
        "text": "Migration must complete before April planning cycle.",
        "trust_level": "trusted_tool",
        "source_ref": "trace_8742"
      }
    ]
  }' | jq
```

### Recall

```bash
curl -s -X POST http://localhost:8080/v0/memory/recall \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "t_demo",
    "agent_id": "a_writer",
    "scope": "team",
    "query": "What migration constraints were defined?",
    "budget": {"max_items": 8, "max_tokens": 1200}
  }' | jq
```

Recall responses include routed model metadata:
- `model_version`
- `model_route` (`active`, `canary_percent`, or `canary_allowlist`)

### Compact context (sync)

```bash
curl -s -X POST http://localhost:8080/v0/memory/compact \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "t_demo",
    "agent_id": "a_writer",
    "scope": "team",
    "query": "Summarize migration and rollout constraints",
    "max_source_items": 16,
    "input_max_tokens": 4000,
    "target_tokens": 600,
    "output_type": "episode"
  }' | jq
```

### Inspect

```bash
curl -s "http://localhost:8080/v0/memory/<memory_id>?tenant_id=t_demo&agent_id=a_writer&scope=team" | jq
```

### Forget

```bash
curl -s -X DELETE http://localhost:8080/v0/memory/<memory_id> \
  -H "content-type: application/json" \
  -d '{"tenant_id":"t_demo","agent_id":"a_writer"}' | jq
```

### Reflect (async) + Job status

```bash
curl -s -X POST http://localhost:8080/v0/memory/reflect \
  -H "content-type: application/json" \
  -d '{"tenant_id":"t_demo","agent_id":"a_writer","window_hours":24,"max_candidates":8}' | jq
```

Use the returned `job_id`:

```bash
curl -s "http://localhost:8080/v0/jobs/<job_id>?tenant_id=t_demo&agent_id=a_writer" | jq
```

### Cleanup expired memory (async)

```bash
curl -s -X POST http://localhost:8080/v0/memory/cleanup \
  -H "content-type: application/json" \
  -d '{"tenant_id":"t_demo","grace_hours":0}' | jq
```

### Inspect dead-letter jobs

```bash
curl -s "http://localhost:8080/v0/jobs/dead_letters?tenant_id=t_demo&agent_id=a_admin" | jq
```

### Register canary model + promote/rollback

Register canary:

```bash
curl -s -X POST http://localhost:8080/v0/models/reranker/canary/register \
  -H "content-type: application/json" \
  -d '{
    "tenant_id":"t_demo",
    "agent_id":"a_admin",
    "version":"reranker-canary-v2",
    "rollout_percent":10,
    "tenant_allowlist":["t_demo"]
  }' | jq
```

Promote canary to active:

```bash
curl -s -X POST http://localhost:8080/v0/models/reranker/canary/promote \
  -H "content-type: application/json" \
  -d '{"tenant_id":"t_demo","agent_id":"a_admin"}' | jq
```

Rollback canary:

```bash
curl -s -X POST http://localhost:8080/v0/models/reranker/canary/rollback \
  -H "content-type: application/json" \
  -d '{"tenant_id":"t_demo","agent_id":"a_admin"}' | jq
```

Record model evaluation signal:

```bash
curl -s -X POST http://localhost:8080/v0/models/reranker/signals \
  -H "content-type: application/json" \
  -d '{
    "tenant_id":"t_demo",
    "agent_id":"a_admin",
    "version":"reranker-canary-v2",
    "metric":"recall_at_5",
    "value":0.93,
    "source":"benchmark_suite"
  }' | jq
```

Read model registry audit history:

```bash
curl -s "http://localhost:8080/v0/models/reranker/history?tenant_id=t_demo&agent_id=a_admin&limit=50" | jq
```

Rollout/rollback mechanics:
1. Tenants in `tenant_allowlist` always route to canary.
2. Remaining tenants use deterministic tenant hashing against `rollout_percent`.
3. Promotion moves canary to active and clears rollout controls.
4. Rollback clears canary slot and keeps current active version unchanged.

Model registry persistence guidance:
1. Use `BRAINSTEM_MODEL_REGISTRY_BACKEND=sqlite` and back up
   `BRAINSTEM_MODEL_REGISTRY_SQLITE_PATH` with your regular snapshot process.
2. For Postgres, set `BRAINSTEM_MODEL_REGISTRY_BACKEND=postgres`; registry data
   is stored in `model_registry_state`, `model_registry_signal`, and
   `model_registry_event`.
3. Restore should include both state and signal/event tables to preserve audit trail.

## Migrations and benchmark tools

Initialize SQLite schema:

```bash
brainstem init-sqlite --db .data/brainstem.db
```

Initialize PostgreSQL schema:

```bash
brainstem init-postgres --dsn "postgresql://postgres:postgres@localhost:5432/brainstem"
```

Run retrieval benchmark:

```bash
brainstem benchmark --backend inmemory --k 5
brainstem benchmark --backend sqlite --sqlite-path .data/benchmark.db --k 5
brainstem benchmark --backend sqlite --graph-enabled --graph-max-expansion 4 --k 5
brainstem benchmark --dataset benchmarks/relation_heavy_dataset.json --backend sqlite --graph-enabled --k 4
brainstem benchmark --graph-enabled --graph-relation-weights '{"reference": 2.0}' --k 5
```

Generate a markdown benchmark artifact:

```bash
brainstem report \
  --dataset benchmarks/retrieval_dataset.json \
  --output-md reports/retrieval_benchmark.md \
  --k 5
```

Generate reproducible leaderboard artifacts from suite manifest:

```bash
brainstem leaderboard \
  --manifest benchmarks/suite_manifest.json \
  --output-dir reports/leaderboard \
  --sqlite-dir .data/leaderboard
```

Leaderboard markdown now includes:
- per-suite ranking for `graph=off/on`,
- graph quality delta dashboard (`on - off`) per backend,
- relation-slice deltas for suites with tagged cases.

CI generates the same leaderboard outputs on each run and uploads them as the
`benchmark-leaderboard` workflow artifact.

Run sustained performance regression checks:

```bash
brainstem perf-regression \
  --iterations 200 \
  --seed-count 100 \
  --output-json reports/performance/perf_regression.json \
  --output-md reports/performance/perf_regression.md
```

The dedicated `Performance Regression` workflow runs weekly and on manual
dispatch, uploads JSON/markdown artifacts, and fails if configured budgets are
exceeded.

## Backup and restore

SQLite quick commands:

```bash
bash scripts/backup_sqlite.sh --memory-db .data/brainstem.db --registry-db .data/model_registry.db --out-dir backups/sqlite/latest
bash scripts/restore_sqlite.sh --backup-dir backups/sqlite/latest --memory-db .data/brainstem.db --registry-db .data/model_registry.db
python scripts/verify_sqlite_restore.py --work-dir .data/restore-verify --output-json .data/restore-verify/verification.json
```

Postgres quick commands:

```bash
bash scripts/backup_postgres.sh --dsn "postgresql://postgres:postgres@localhost:5432/brainstem" --out-dir backups/postgres/latest
bash scripts/restore_postgres.sh --dsn "postgresql://postgres:postgres@localhost:5432/brainstem" --backup-file backups/postgres/latest/brainstem.pgdump
```

For full playbook, see `ops/BACKUP_RESTORE.md`.

## Release automation

Prepare local release artifacts:

```bash
make release-prep VERSION=0.2.0
```

This updates:

- `pyproject.toml` version
- `CHANGELOG.md` (prepends a generated entry from commit history)
- `.release-notes.md` (used by release workflow)

Publish a release from GitHub:

1. Run workflow `Release` (manual dispatch) on `main`.
2. Enter `version` (`MAJOR.MINOR.PATCH`).
3. Optionally enable `publish_to_pypi`.

### When to enable graph mode

Enable graph mode when memory entries share entities/terms and you want recall
to include relation-adjacent context (for example runbooks, policies, and
incident artifacts that reference the same system names). Keep it disabled for
minimal-latency deployments where strict lexical/vector ranking is sufficient.

Run HTTP health check:

```bash
brainstem health --url http://localhost:8080/healthz
```

Compatibility wrappers remain available:

```bash
python scripts/init_sqlite_db.py --db .data/brainstem.db
python scripts/benchmark_recall.py --backend inmemory --k 5
python scripts/generate_benchmark_report.py --dataset benchmarks/retrieval_dataset.json
python scripts/generate_leaderboard.py --manifest benchmarks/suite_manifest.json
python scripts/run_performance_regression.py --iterations 200 --seed-count 100
python scripts/verify_sqlite_restore.py --work-dir .data/restore-verify
python scripts/prepare_release.py --version 0.2.0
```

Run MCP server transport:

```bash
pip install -e ".[dev,mcp]"
export BRAINSTEM_MCP_AUTH_MODE=token
export BRAINSTEM_MCP_TOKENS='{
  "mcp-writer": {"tenant_id":"t_demo","agent_id":"a_writer","role":"writer"},
  "mcp-admin": {"tenant_id":"t_demo","agent_id":"a_admin","role":"admin"}
}'
python scripts/mcp_server.py
```

Run MCP end-to-end integration tests:

```bash
pip install -e ".[dev,mcp]"
pytest tests/test_mcp_integration_e2e.py -q
```

The CI workflow runs the same MCP E2E suite in the `mcp-integration` job.

MCP tools require auth by default. Include a token in payload metadata:

```json
{
  "auth_token": "mcp-writer",
  "scope": "team",
  "query": "What constraints do we already know?"
}
```

An alternative token envelope is also accepted:

```json
{
  "_session": {"token": "mcp-writer"},
  "scope": "team",
  "query": "What constraints do we already know?"
}
```

## Repository docs

- [planning/README.md](./planning/README.md)
- [planning/BRAIN_ARCHITECTURE.md](./planning/BRAIN_ARCHITECTURE.md)
- [planning/BRAIN_V0_TECH_SPEC.md](./planning/BRAIN_V0_TECH_SPEC.md)
- [demo/README.md](./demo/README.md)
- [TODO.md](./TODO.md)
- [CONTRIBUTING.md](./CONTRIBUTING.md)
- [MAINTAINERS.md](./MAINTAINERS.md)
- [ops/BACKUP_RESTORE.md](./ops/BACKUP_RESTORE.md)
- [CHANGELOG.md](./CHANGELOG.md)

## Workflow

This repo is managed issue-first:

1. create/pick a GitHub issue,
2. branch from `main`,
3. implement + test,
4. open/update PR,
5. review and merge.

## Roadmap snapshot

- `v0.2`: PostgreSQL + pgvector backend
- `v0.3`: richer benchmark corpus + observability dashboards
- `v0.4`: async job workers for reflect/train
- `v0.5`: MCP-native server transport

## License

MIT. See [LICENSE](./LICENSE).
