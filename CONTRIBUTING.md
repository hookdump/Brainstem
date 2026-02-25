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

## Review bar

A PR is ready when:

- CI is green.
- Core behavior is covered by tests.
- No obvious tenant isolation or trust-level regressions.
