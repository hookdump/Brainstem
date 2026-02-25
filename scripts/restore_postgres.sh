#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/restore_postgres.sh \
    --dsn <postgres_dsn> \
    --backup-file <path_to_brainstem.pgdump>
EOF
}

dsn=""
backup_file=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dsn)
      dsn="$2"
      shift 2
      ;;
    --backup-file)
      backup_file="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$dsn" || -z "$backup_file" ]]; then
  usage
  exit 2
fi

if [[ ! -f "$backup_file" ]]; then
  echo "Backup file not found: $backup_file" >&2
  exit 1
fi

if ! command -v pg_restore >/dev/null 2>&1; then
  echo "pg_restore is required but not found in PATH." >&2
  exit 1
fi

pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  --dbname "$dsn" \
  "$backup_file"

echo "Postgres restore complete from: $backup_file"
