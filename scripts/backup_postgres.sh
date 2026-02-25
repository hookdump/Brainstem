#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/backup_postgres.sh \
    --dsn <postgres_dsn> \
    --out-dir <backup_dir>
EOF
}

dsn=""
out_dir=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dsn)
      dsn="$2"
      shift 2
      ;;
    --out-dir)
      out_dir="$2"
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

if [[ -z "$dsn" || -z "$out_dir" ]]; then
  usage
  exit 2
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "pg_dump is required but not found in PATH." >&2
  exit 1
fi

mkdir -p "$out_dir"
created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

pg_dump --format=custom --no-owner --no-privileges --file "$out_dir/brainstem.pgdump" "$dsn"
pg_dump --schema-only --no-owner --no-privileges --file "$out_dir/schema.sql" "$dsn"

(
  cd "$out_dir"
  sha256sum brainstem.pgdump schema.sql > checksums.txt
)

cat > "$out_dir/manifest.json" <<EOF
{
  "created_at": "$created_at",
  "backup_file": "brainstem.pgdump",
  "schema_file": "schema.sql",
  "checksums": "checksums.txt"
}
EOF

echo "Postgres backup complete: $out_dir"
