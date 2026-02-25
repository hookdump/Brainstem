# Brainstem TODO

Status date: February 25, 2026

## Active

- [x] Bootstrap repository docs (`README`, architecture, v0 spec).
- [x] Implement v0 API skeleton with memory endpoints.
- [x] Add initial tests and CI baseline.
- [x] Replace in-memory store with PostgreSQL + pgvector backend. (`#1`, baseline complete)
- [x] Add authn/authz middleware for tenant and scope enforcement. (`#2`)
- [x] Add retrieval metrics and tracing instrumentation. (`#5`)

## Next (High Priority)

- [x] Implement DB schema + migrations baseline from `BRAIN_V0_TECH_SPEC.md` (SQLite v0).
- [x] Add idempotency persistence in storage layer (SQLite backend).
- [x] Build baseline benchmark harness for Recall@K and token efficiency. (`#3`, local script)
- [x] Add baseline conflict tracking for contradictory facts in recall responses.
- [x] Add retention/TTL workflow support (`expires_at`) in memory ingestion and recall filtering.
- [x] Expand benchmark dataset and publish reproducible benchmark report. (`#3`)

## Later

- [x] Add MCP-native server transport (in addition to REST mirror). (`#7`, baseline)
- [x] Add async worker queue for reflection/train jobs. (`#4`, in-process baseline)
- [x] Add retention cleanup worker for expired memory items. (`#8`, async baseline)
- [x] Add Docker deployment and local compose stack. (`#18`)
- [x] Add retry policy and dead-letter tracking for async jobs. (`#17`, in-process baseline)
- [ ] Upgrade async job queue to distributed workers with persistent retries and DLQ.
- [ ] Harden MCP transport with auth/session security and integration fixtures. (`#19`)
- [x] Add CI job for Postgres integration test execution. (`#20`)
- [x] Add first-party CLI for admin and ops workflows. (`#21`)
- [ ] Add canary model registry for reranker/salience models.
- [ ] Add optional graph projection for relation-aware retrieval.
- [ ] Publish reproducible benchmark suite and leaderboard examples.

## Done

- [x] Created private GitHub repo: `hookdump/Brainstem`.
- [x] Initialized git + pushed `main` over SSH.
- [x] Drafted concept and v0 implementation specification documents.
- [x] Created roadmap issues in GitHub: `#1` to `#5`.
- [x] Opened bootstrap implementation PR: `#6` (`feat/bootstrap-v0` -> `main`).
- [x] Added SQLite persistent repository + migration script.
- [x] Added API-key auth mode and role-based endpoint authorization.
- [x] Expanded tests for auth and SQLite persistence.
- [x] Added retrieval eval harness (`scripts/benchmark_recall.py`) with tests.
- [x] Closed GitHub issue `#2` (auth middleware complete for v0).
- [x] Added TTL-aware retrieval and contradiction signaling in recall.
- [x] Added new backlog issues for retention cleanup and MCP transport (`#7`, `#8`).
- [x] Added observability baseline (`/v0/metrics` counters + latency summaries) with tests.
- [x] Added Postgres backend scaffold + pgvector migration baseline.
- [x] Published benchmark dataset and report artifact (`reports/retrieval_benchmark.md`).
- [x] Added async job baseline (`reflect`/`train`) with `/v0/jobs/{job_id}` polling.
- [x] Added recall stage timing metrics and structured trace logging.
- [x] Added retention cleanup job flow with purge counts and tests.
- [x] Added MCP tool-service baseline and MCP server entrypoint.
- [x] Added pgvector-assisted Postgres recall baseline and optional integration tests.
- [x] Added Docker/local compose deployment path with smoke tooling.
- [x] Added async retry attempts and dead-letter inspection endpoint.
- [x] Added dedicated CI job for Postgres integration tests.
- [x] Added first-party `brainstem` CLI plus backward-compatible script wrappers.
