# Brainstem TODO

Status date: February 25, 2026

## Active

- [x] Bootstrap repository docs (`README`, architecture, v0 spec).
- [x] Implement v0 API skeleton with memory endpoints.
- [x] Add initial tests and CI baseline.
- [ ] Replace in-memory store with PostgreSQL + pgvector backend. (`#1`)
- [ ] Add authn/authz middleware for tenant and scope enforcement. (`#2`)
- [ ] Add retrieval metrics and tracing instrumentation. (`#5`)

## Next (High Priority)

- [ ] Implement DB schema + migrations from `BRAIN_V0_TECH_SPEC.md`.
- [ ] Add idempotency persistence in storage layer.
- [ ] Add conflict tracking for contradictory facts.
- [ ] Add retention/TTL and deletion policy workflows.
- [ ] Build benchmark harness for Recall@K and token efficiency. (`#3`)

## Later

- [ ] Add MCP-native server transport (in addition to REST mirror).
- [ ] Add async worker queue for reflection/train jobs. (`#4`)
- [ ] Add canary model registry for reranker/salience models.
- [ ] Add optional graph projection for relation-aware retrieval.
- [ ] Publish reproducible benchmark suite and leaderboard examples.

## Done

- [x] Created private GitHub repo: `hookdump/Brainstem`.
- [x] Initialized git + pushed `main` over SSH.
- [x] Drafted concept and v0 implementation specification documents.
