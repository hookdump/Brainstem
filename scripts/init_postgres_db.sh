#!/usr/bin/env bash
set -euo pipefail

DSN="${1:-${BRAINSTEM_POSTGRES_DSN:-}}"
MIGRATION="${2:-migrations/0002_postgres_pgvector.sql}"

if [[ -z "${DSN}" ]]; then
  echo "Usage: $0 <postgres-dsn> [migration-file]" >&2
  echo "Or set BRAINSTEM_POSTGRES_DSN." >&2
  exit 1
fi

psql "${DSN}" -f "${MIGRATION}"
echo "Applied ${MIGRATION} to ${DSN}"
