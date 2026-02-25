#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-hookdump/Brainstem}"

gh issue create --repo "$REPO" \
  --title "Implement PostgreSQL + pgvector memory repository (v0.2)" \
  --body "## Goal
Replace the in-memory repository with PostgreSQL + pgvector while preserving current API contracts.

## Scope
- Add DB schema + migrations
- Implement repository methods for remember/recall/inspect/forget
- Keep tenant and scope checks strict
- Add integration tests for persistence behavior

## Done criteria
- API behavior equivalent to in-memory baseline
- Persistence verified by tests
- Migration instructions documented"

gh issue create --repo "$REPO" \
  --title "Add authn/authz middleware for tenant and scope enforcement" \
  --body "## Goal
Implement robust access control for all memory endpoints.

## Scope
- API key or JWT validation layer
- Tenant scoping checks
- Scope escalation prevention (private/team/global)
- Audit logging for access-denied attempts

## Done criteria
- Unauthorized reads/writes blocked
- Tests cover positive and negative access cases"

gh issue create --repo "$REPO" \
  --title "Build retrieval eval harness (Recall@K, nDCG, token efficiency)" \
  --body "## Goal
Add measurable quality and efficiency benchmarks for memory retrieval.

## Scope
- Curated evaluation dataset
- Baseline comparisons
- Metrics reporting

## Done criteria
- Reproducible benchmark command
- Results document committed in repo"

gh issue create --repo "$REPO" \
  --title "Implement async reflection and training job workers" \
  --body "## Goal
Move reflect/train endpoints from stubs to queued worker jobs.

## Scope
- Queue backend selection
- Worker process implementation
- Job status tracking endpoint

## Done criteria
- End-to-end queued job flow functional
- Errors and retries observable"

gh issue create --repo "$REPO" \
  --title "Add observability stack for recall and write pipelines" \
  --body "## Goal
Capture operational and quality metrics for production readiness.

## Scope
- Structured logs
- Stage timing metrics
- Tracing for recall pipeline

## Done criteria
- Dashboard-ready metrics exported
- p95 latency and error-rate visible per endpoint"

echo "Bootstrap issues created in $REPO"
