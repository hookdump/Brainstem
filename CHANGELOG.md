# Changelog

## 0.3.0 - 2026-02-25

### Changes
- Merge pull request #55 from hookdump/chore/release-0.3.0-prep
- chore: prepare release artifacts for v0.3.0
- Merge pull request #54 from hookdump/feat/53-context-compaction
- feat: add context compaction API and MCP workflow
- Merge pull request #52 from hookdump/feat/51-mypy-hardening
- fix: ignore optional MCP imports in strict mypy
- feat: enforce strict mypy gate across repo

## 0.3.0 - 2026-02-25

### Changes
- Merge pull request #54 from hookdump/feat/53-context-compaction
- feat: add context compaction API and MCP workflow
- Merge pull request #52 from hookdump/feat/51-mypy-hardening
- fix: ignore optional MCP imports in strict mypy
- feat: enforce strict mypy gate across repo

## 0.2.0 - 2026-02-25

### Changes
- Merge pull request #50 from hookdump/chore/release-0.2.0-prep
- Prepare release artifacts for v0.2.0
- Merge pull request #49 from hookdump/feat/44-release-automation
- Add release automation workflow and changelog tooling
- Merge pull request #48 from hookdump/feat/43-backup-restore-playbook
- Add backup and restore playbooks with verification scripts
- Merge pull request #47 from hookdump/feat/42-performance-regression-suite
- Add sustained performance regression suite and workflow
- Merge pull request #46 from hookdump/feat/41-license-governance
- Adopt MIT license and maintainer governance policy
- Merge pull request #45 from hookdump/feat/demo-and-planning-reorg
- Add runnable demo and move planning docs into Planning folder
- Merge pull request #40 from hookdump/feat/37-mcp-e2e-harness
- Add MCP end-to-end integration test harness
- Merge pull request #39 from hookdump/feat/36-graph-relation-scoring
- Improve graph relation scoring and leaderboard dashboards
- Update README.md with project description
- Persist model registry state and add audit history (#38)
- Add optional graph projection and recall expansion (#34)
- Add canary model registry with rollout and signals (#33)
- Add reproducible benchmark suite and leaderboard artifacts (#32)
- Add SQLite-backed distributed job queue and worker (#31)
- Harden MCP auth and session context enforcement (#26)
- Add first-party CLI for Brainstem admin and ops (#25)
- Add Postgres integration test job to CI (#24)
- Add job retries and dead-letter inspection endpoint (#23)
- Add Docker compose stack and local smoke tooling (#22)
- Add pgvector recall path and Postgres integration tests (#16)
- Add MCP tool-service baseline and server entrypoint (#15)
- Add async retention cleanup worker and purge APIs (#14)
- Add recall stage timing metrics and structured traces (#13)
- Add async reflect/train jobs with status polling (#12)
- Expand benchmark dataset and publish report artifact (#11)
- Add Postgres backend scaffold with pgvector migration (#10)
- Add observability metrics endpoint and request telemetry (#9)
- Bootstrap v0 service scaffold and OSS workflow (#6)
- Add Brainstem architecture and v0 technical spec

## 0.1.0 - 2026-02-25

### Changes

- Initial public baseline with REST API, MCP transport, storage backends,
  async jobs, model registry, benchmarks, and operational tooling.
