# Contributing to Brainstem

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run checks before opening PR:

```bash
ruff check .
pytest
```

Run MCP end-to-end integration tests (for MCP-related changes):

```bash
pip install -e ".[dev,mcp]"
pytest tests/test_mcp_integration_e2e.py -q
```

## Branch naming

- `feat/<issue-number>-short-name`
- `fix/<issue-number>-short-name`
- `chore/<issue-number>-short-name`

## Commit style

Use clear imperative commit messages:

- `Add PostgreSQL repository implementation`
- `Fix tenant scope enforcement for private memory`
- `Improve recall packing token estimator`

## Pull requests

- Link the issue in PR description.
- Include tests for behavior changes.
- Keep PRs focused and reviewable.
- Update docs when APIs or behavior change.
- Require maintainer approval before merge.

## Review bar

A PR is ready when:

- CI is green.
- Core behavior is covered by tests.
- No obvious tenant isolation or trust-level regressions.

## Governance

- Maintainer roster and ownership: `MAINTAINERS.md`.
- Repository ownership defaults are enforced via `.github/CODEOWNERS`.
- Security-sensitive changes (auth/session, tenancy boundaries, persistence)
  require explicit maintainer signoff.
