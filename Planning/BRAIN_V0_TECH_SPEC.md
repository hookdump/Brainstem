# Brainstem v0 Technical Specification

Status: Draft v0.1  
Date: February 25, 2026  
Owner: hookdump/Brainstem

## 1. Purpose

Brainstem v0 is a shared memory coprocessor for AI agents. It provides:

- durable memory across sessions,
- multi-agent shared context with strict tenancy boundaries,
- budget-aware context retrieval for LLM prompts,
- optional asynchronous training modules (reranking/salience), not full end-to-end online model training.

This spec converts the concept doc into an implementation-ready blueprint.

## 2. Scope

### In scope (v0)

- MCP server with memory tools (`remember`, `recall`, `inspect`, `forget`, `reflect`, `train`).
- Core write/read memory pipeline.
- Hybrid retrieval (BM25 + vector + lightweight rerank).
- Provenance + trust labels on all memory objects.
- Per-tenant policy controls and role-based access.
- Async jobs for summarization/reflection and initial training loops.
- Metrics/evals for memory quality and token efficiency.

### Out of scope (v0)

- Fully autonomous online continual training of a large shared base model.
- Cross-tenant parameter sharing by default.
- General autonomous execution engine (Brainstem is memory infrastructure, not task agent runtime).

## 3. Design Goals

### Primary goals

- Reduce prompt token usage while improving answer quality.
- Preserve continuity across sessions and across cooperating agents.
- Maintain inspectable memory provenance and safety controls.

### Non-goals

- Replace foundation model reasoning.
- Guarantee perfect recall from untrusted or conflicting sources.

### Success metrics

- `>=20%` median token reduction for long-horizon tasks.
- `>=15%` improvement on curated cross-session task benchmark.
- `p95 recall latency <= 350ms` at 100 QPS (single region baseline).
- `<1%` unauthorized memory access incidents (target 0, enforced by tests).

## 4. System Architecture

```text
Agent Client(s)
  - OpenAI Agents SDK / Anthropic client / custom orchestration
  - communicates via MCP and optional REST

        |
        v
Brain Gateway
  - authn/authz, tenancy routing, quotas, audit events

        +--> Memory Write Pipeline
        |      - schema normalization
        |      - trust assignment
        |      - salience scoring
        |      - dedupe/conflict handling
        |
        +--> Memory Storage Layer
        |      - PostgreSQL (events/facts/episodes/policy)
        |      - pgvector index
        |      - BM25/keyword index
        |      - optional graph projection
        |
        +--> Retrieval & Context Composer
        |      - hybrid candidate generation
        |      - reranking + policy filter
        |      - budget-aware packing
        |
        +--> Worker Jobs
               - reflection (episode generation)
               - model training (reranker/salience)
               - eval runner
```

## 5. Component Contracts

### 5.1 Gateway

Responsibilities:

- JWT/API-key validation.
- Tenant and scope checks.
- Request shaping and limits (`max_items`, `max_tokens`, payload size).
- Idempotency key support for write calls.

Rejection conditions:

- missing `tenant_id`,
- scope escalation attempt (`private` to `team/global` without role),
- invalid trust override.

### 5.2 Write Pipeline

Stages:

1. normalize input objects into canonical memory schema,
2. classify memory type (`event`, `fact`, `episode`, `policy`),
3. compute salience score (`0..1`) and initial confidence (`0..1`),
4. embed text payload and update indexes,
5. append immutable audit log.

### 5.3 Retrieval/Composer

Algorithm:

1. lexical search (BM25) top `K1`,
2. vector search top `K2`,
3. merge + dedupe by semantic hash/entity overlap,
4. optional graph expansion (related entities/constraints),
5. rerank with lightweight model,
6. enforce policy/trust filter,
7. pack to token budget with diversity constraints.

Output:

- memory snippets,
- citations/provenance ids,
- confidence summary,
- unresolved conflicts list (if contradictory facts found).

## 6. API Specification

### 6.1 MCP Tools

#### `brain.remember`

Input:

```json
{
  "tenant_id": "t_123",
  "agent_id": "a_ops",
  "scope": "team",
  "items": [
    {
      "type": "event",
      "text": "User requires migration completion before April planning cycle.",
      "source_ref": "trace_8742",
      "trust_level": "trusted_tool"
    }
  ],
  "idempotency_key": "f6f8f2dd-5d78-4ec4-bfc5-d6ab6e7dc64b"
}
```

Output:

```json
{
  "accepted": 1,
  "rejected": 0,
  "memory_ids": ["mem_91f4"],
  "warnings": []
}
```

#### `brain.recall`

Input:

```json
{
  "tenant_id": "t_123",
  "agent_id": "a_planner",
  "query": "What constraints did the user give for migration?",
  "scope": "team",
  "budget": {
    "max_items": 12,
    "max_tokens": 1400
  },
  "filters": {
    "trust_min": 0.5,
    "types": ["fact", "episode", "policy"]
  }
}
```

Output:

```json
{
  "items": [
    {
      "memory_id": "mem_91f4",
      "type": "fact",
      "text": "Migration must complete before April planning cycle.",
      "confidence": 0.78,
      "salience": 0.87,
      "source_ref": "trace_8742"
    }
  ],
  "composed_tokens_estimate": 162,
  "conflicts": [],
  "trace_id": "rec_2s9k"
}
```

#### `brain.reflect`

Creates episode summaries and candidate facts from recent events.

#### `brain.inspect`

Returns full provenance, revisions, and policy checks for a memory id.

#### `brain.forget`

Policy-compliant deletion/tombstone request by selector.

#### `brain.train`

Schedules async training jobs for reranker/salience model.

### 6.2 Optional REST Mirror (for non-MCP clients)

- `POST /v0/memory/remember`
- `POST /v0/memory/recall`
- `POST /v0/memory/reflect`
- `POST /v0/memory/train`
- `GET /v0/memory/{id}`
- `DELETE /v0/memory/{id}`

## 7. Data Model (PostgreSQL-first)

### 7.1 Tables

`tenants`

- `id` (pk)
- `name`
- `created_at`
- `policy_json`

`agents`

- `id` (pk)
- `tenant_id` (fk)
- `role` (`reader`, `writer`, `admin`)
- `created_at`

`memory_items`

- `id` (pk)
- `tenant_id` (fk)
- `agent_id` (fk)
- `type` (`event`, `fact`, `episode`, `policy`)
- `scope` (`private`, `team`, `global`)
- `text` (normalized content)
- `json_payload` (structured extras)
- `trust_level` (`trusted_tool`, `user_claim`, `untrusted_web`)
- `confidence` (float)
- `salience` (float)
- `source_ref` (text)
- `semantic_hash` (text)
- `created_at`
- `expires_at` (nullable)
- `is_tombstoned` (bool default false)

`memory_edges` (optional graph projection)

- `id` (pk)
- `tenant_id` (fk)
- `from_memory_id` (fk)
- `to_memory_id` (fk)
- `relation_type`
- `weight`

`memory_audit_log`

- `id` (pk)
- `tenant_id` (fk)
- `actor_agent_id`
- `action` (`create`, `update`, `delete`, `recall`)
- `memory_id`
- `request_id`
- `created_at`

`model_registry`

- `id` (pk)
- `tenant_id` (nullable for global model)
- `model_kind` (`reranker`, `salience`)
- `version`
- `artifact_uri`
- `status` (`candidate`, `canary`, `active`, `rolled_back`)
- `metrics_json`
- `created_at`

### 7.2 Indexes

- btree: `(tenant_id, created_at desc)`
- btree: `(tenant_id, type, scope)`
- btree: `(tenant_id, semantic_hash)`
- pgvector: embedding column `vector_cosine_ops`
- full-text/GiN index on `text`

## 8. Memory Write Rules

### 8.1 Salience scoring (v0 heuristic + optional model)

Base score combines:

- explicit user constraints or commitments,
- unresolved tasks/deadlines,
- recurrence frequency,
- entity centrality (project/user/core objective).

If salience `< threshold_low`, downgrade to archive tier and avoid default recall.

### 8.2 Confidence scoring

- trusted tool output starts higher than untrusted web claims,
- confidence decreases for stale or contradicted memories,
- facts without provenance cannot exceed configured cap.

### 8.3 Conflict handling

Contradictory facts are preserved with conflict links; retrieval prefers:

1. newer + higher-trust + higher-confidence memory,
2. but returns conflict notice when confidence gap is small.

## 9. Retrieval Strategy Details

### 9.1 Candidate generation defaults

- `K1` lexical = 40
- `K2` vector = 60
- merged target before rerank = 80
- final return = budget-constrained (default 8-12 items)

### 9.2 Rerank features

- query-memory semantic score,
- recency decay,
- salience,
- trust multiplier,
- type prior (policy/fact may outrank events for constraints queries).

### 9.3 Context packing policy

- include at least one high-trust policy/fact when available,
- include no more than `N` near-duplicate snippets,
- attach provenance ids for each snippet,
- include compact conflict block when needed.

## 10. Training and Eval Pipeline

### 10.1 Training jobs (async)

`train_reranker`:

- input: retrieval traces with accept/reject labels
- output: reranker model artifact + metrics

`train_salience`:

- input: event-to-usefulness labels (derived from downstream recalls/outcomes)
- output: salience predictor

### 10.2 Deployment policy

- candidate model validated offline,
- canary at 5% traffic per tenant,
- promote only if quality and latency pass thresholds,
- immediate rollback on regression or safety failure.

### 10.3 Eval suite

- recall relevance (nDCG, Recall@K),
- answer quality uplift vs no-memory baseline,
- token/latency efficiency,
- safety checks (cross-tenant leakage, prompt-injection memory attempts).

## 11. Security and Governance

### 11.1 Isolation model

- strict tenant partitioning at query layer and storage filters,
- scoped memory visibility (`private/team/global`),
- no cross-tenant retrieval in v0.

### 11.2 Trust partitions

- untrusted content stored in separate partition/tag,
- retrieval defaults exclude low-trust unless explicitly requested,
- high-impact actions require trusted corroboration.

### 11.3 Data lifecycle

- configurable retention by type/scope,
- tombstone + hard-delete workflow,
- audit log immutable retention policy.

## 12. Observability

Emit traces for:

- write pipeline stage timings,
- retrieval stage timings and candidate counts,
- policy-filter rejects,
- model version used in rerank,
- final packed token estimate.

Dashboards:

- p50/p95 latency by endpoint/tool,
- memory growth by tenant/type,
- recall hit quality trend,
- token savings trend.

## 13. SLOs and Capacity (v0 target)

- Availability: `99.5%` monthly for read endpoints.
- `p95` recall latency: `<=350ms`.
- `p95` remember latency: `<=250ms` (excluding async embedding queue delays).
- Error budget alerts for 5xx and authz failures.

Assumed initial load:

- 20 tenants,
- 300 agents total,
- up to 100 QPS combined recall/remember,
- 10M memory items.

## 14. Deployment Topology

Minimum production topology:

- API pods (2+),
- worker pods (2+),
- Postgres + pgvector,
- Redis queue,
- object storage for model artifacts,
- optional read replicas for recall scaling.

Environment tiers:

- `dev` (single node),
- `staging` (prod-like),
- `prod` (multi-AZ recommended).

## 15. Reference Implementation Plan

### Sprint 1

- Scaffold service (`FastAPI` or `Fastify`) with MCP and REST entrypoints.
- Implement auth, tenancy, and `remember` path.
- Create DB schema + migrations.

Exit criteria:

- valid writes with audit logs and indexes.

### Sprint 2

- Implement hybrid retrieval and context packer.
- Add `recall` and `inspect`.
- Add baseline metrics and tracing.

Exit criteria:

- end-to-end recall with provenance and budget enforcement.

### Sprint 3

- Add `reflect` jobs, conflict handling, and retention controls.
- Add eval harness and benchmark dataset.

Exit criteria:

- measurable uplift report and safety checks passing.

### Sprint 4

- Add async model training (`reranker`, `salience`) and canary routing.
- Add rollback controls and model registry dashboard.

Exit criteria:

- canary deployment workflow fully operational.

## 16. Open Questions

- Should `global` scope be org-wide only or include public templates?
- Which embedding model/provider should be default in v0?
- Do we need graph store in v0.0 or can we defer to v0.2?
- Should reflect jobs be scheduled, event-driven, or hybrid?

## 17. Immediate Next Build Tasks

1. Choose implementation language (`FastAPI` vs `Fastify`) and freeze stack.
2. Define JSON Schemas for all MCP tool inputs/outputs.
3. Generate SQL migrations for base tables/indexes.
4. Stub endpoints and add integration tests for auth + tenancy.
5. Build first benchmark harness for recall quality and token savings.
