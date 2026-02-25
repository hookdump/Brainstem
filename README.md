# Brainstem

Brainstem is a shared memory coprocessor for AI agents.

It gives agent systems persistent, auditable, and budget-aware memory across sessions and across multiple cooperating agents.

## Why this project

Most agent systems either:

- overpay by stuffing huge histories into context windows, or
- lose continuity between sessions.

Brainstem aims to provide a third path:

- structured long-term memory,
- hybrid retrieval (lexical + semantic),
- provenance-first context composition,
- optional trainable reranking/salience modules.

## Current status

`v0 bootstrap` is implemented in this repository:

- FastAPI service skeleton
- Core memory APIs: `remember`, `recall`, `inspect`, `forget`, `reflect`, `train`
- In-memory repository implementation (for fast iteration)
- Tests and CI baseline
- Roadmap and architecture specs

## Repository docs

- [BRAIN_ARCHITECTURE.md](./BRAIN_ARCHITECTURE.md)
- [BRAIN_V0_TECH_SPEC.md](./BRAIN_V0_TECH_SPEC.md)
- [TODO.md](./TODO.md)
- [CONTRIBUTING.md](./CONTRIBUTING.md)

## Quickstart

### 1) Create environment and install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2) Run the API

```bash
brainstem-api
```

The service runs on `http://localhost:8080`.

### 3) Run tests

```bash
pytest
```

### 4) Try the API

```bash
curl -s http://localhost:8080/healthz | jq
```

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

```bash
curl -s -X POST http://localhost:8080/v0/memory/recall \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "t_demo",
    "agent_id": "a_writer",
    "query": "What migration constraints were defined?",
    "scope": "team"
  }' | jq
```

## Architecture snapshot

```text
Clients (agents)
  -> Brain Gateway (auth, tenancy, policy)
  -> Write pipeline (normalize, score, index)
  -> Memory stores (events/facts/episodes + vector + lexical)
  -> Retrieval composer (hybrid retrieval + budget packing + provenance)
```

For details, see `BRAIN_V0_TECH_SPEC.md`.

## Development workflow

This project follows an issue-first flow:

1. Open/assign a GitHub issue.
2. Create a branch from `main`:
   - `feat/<issue-number>-short-name`
   - `fix/<issue-number>-short-name`
3. Implement with tests.
4. Open a PR using the PR template.
5. Merge after CI and review.

## Planned roadmap

- v0.1: in-memory service + API contracts
- v0.2: PostgreSQL + pgvector + migrations
- v0.3: retrieval eval harness and metrics dashboards
- v0.4: async reflection jobs and trainable reranker

## License

TBD.
