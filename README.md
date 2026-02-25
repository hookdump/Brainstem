# Brainstem

Brainstem is a shared memory coprocessor for AI agents.

It lets multiple agents store, retrieve, and reuse context across sessions with:

- durable memory storage,
- scope-aware access (`private`, `team`, `global`),
- retrieval packing under token budgets,
- provenance and trust fields on memory items,
- optional API-key authorization with tenant/role enforcement.

## Current capabilities (v0)

- REST API with endpoints:
  - `remember`, `recall`, `inspect`, `forget`, `reflect`, `train`
- Storage backends:
  - `inmemory` (fast local dev)
  - `sqlite` (persistent local baseline)
  - `postgres` (pgvector-ready scaffold)
- Role model:
  - `reader`, `writer`, `admin`
- Async job pipeline:
  - queued background execution for `reflect` and `train`
  - status polling via job endpoint
- Memory quality baseline:
  - heuristic salience/confidence
  - contradiction signaling in recall output
  - retention support with `expires_at`
- Observability baseline:
  - per-route request counters and latency summaries
  - `GET /v0/metrics` endpoint
- Tooling:
  - migration script for SQLite
  - retrieval benchmark harness (Recall@K, nDCG, token estimate)
  - CI (`ruff` + `pytest`)

## Quickstart

### 1) Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2) Run the API

```bash
brainstem-api
```

Service URL: `http://localhost:8080`

### 3) Run checks

```bash
ruff check .
pytest
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

Example:

```bash
export BRAINSTEM_STORE_BACKEND=sqlite
export BRAINSTEM_SQLITE_PATH=.data/brainstem.db
export BRAINSTEM_AUTH_MODE=api_key
export BRAINSTEM_API_KEYS='{
  "writer-key": {"tenant_id":"t_demo","agent_id":"a_writer","role":"writer"},
  "admin-key": {"tenant_id":"t_demo","agent_id":"a_admin","role":"admin"}
}'
brainstem-api
```

For PostgreSQL:

```bash
pip install -e ".[dev,postgres]"
export BRAINSTEM_STORE_BACKEND=postgres
export BRAINSTEM_POSTGRES_DSN="postgresql://postgres:postgres@localhost:5432/brainstem"
brainstem-api
```

## Endpoint reference

- `GET /healthz`
- `GET /v0/meta`
- `GET /v0/metrics`
- `POST /v0/memory/remember`
- `POST /v0/memory/recall`
- `GET /v0/memory/{memory_id}?tenant_id=...&agent_id=...&scope=...`
- `DELETE /v0/memory/{memory_id}`
- `POST /v0/memory/reflect`
- `POST /v0/memory/train`
- `GET /v0/jobs/{job_id}?tenant_id=...&agent_id=...`

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

## Migrations and benchmark tools

Initialize SQLite schema:

```bash
python scripts/init_sqlite_db.py --db .data/brainstem.db
```

Initialize PostgreSQL schema:

```bash
./scripts/init_postgres_db.sh "postgresql://postgres:postgres@localhost:5432/brainstem"
```

Run retrieval benchmark:

```bash
python scripts/benchmark_recall.py --backend inmemory --k 5
python scripts/benchmark_recall.py --backend sqlite --sqlite-path .data/benchmark.db --k 5
```

Generate a markdown benchmark artifact:

```bash
python scripts/generate_benchmark_report.py \
  --dataset benchmarks/retrieval_dataset.json \
  --output-md reports/retrieval_benchmark.md \
  --k 5
```

## Repository docs

- [BRAIN_ARCHITECTURE.md](./BRAIN_ARCHITECTURE.md)
- [BRAIN_V0_TECH_SPEC.md](./BRAIN_V0_TECH_SPEC.md)
- [TODO.md](./TODO.md)
- [CONTRIBUTING.md](./CONTRIBUTING.md)

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

TBD.
