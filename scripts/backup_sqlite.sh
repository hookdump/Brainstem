#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/backup_sqlite.sh \
    --memory-db <path> \
    --registry-db <path> \
    --out-dir <backup_dir>
EOF
}

memory_db=""
registry_db=""
out_dir=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --memory-db)
      memory_db="$2"
      shift 2
      ;;
    --registry-db)
      registry_db="$2"
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

if [[ -z "$memory_db" || -z "$registry_db" || -z "$out_dir" ]]; then
  usage
  exit 2
fi

if [[ ! -f "$memory_db" ]]; then
  echo "memory db not found: $memory_db" >&2
  exit 1
fi
if [[ ! -f "$registry_db" ]]; then
  echo "registry db not found: $registry_db" >&2
  exit 1
fi

mkdir -p "$out_dir"

created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cp "$memory_db" "$out_dir/memory.db"
cp "$registry_db" "$out_dir/model_registry.db"

(
  cd "$out_dir"
  sha256sum memory.db model_registry.db > checksums.txt
)

cat > "$out_dir/manifest.json" <<EOF
{
  "created_at": "$created_at",
  "memory_db": "memory.db",
  "model_registry_db": "model_registry.db",
  "checksums": "checksums.txt"
}
EOF

echo "SQLite backup complete: $out_dir"
