#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/restore_sqlite.sh \
    --backup-dir <backup_dir> \
    --memory-db <target_memory_db> \
    --registry-db <target_registry_db>
EOF
}

backup_dir=""
memory_db=""
registry_db=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-dir)
      backup_dir="$2"
      shift 2
      ;;
    --memory-db)
      memory_db="$2"
      shift 2
      ;;
    --registry-db)
      registry_db="$2"
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

if [[ -z "$backup_dir" || -z "$memory_db" || -z "$registry_db" ]]; then
  usage
  exit 2
fi

if [[ ! -f "$backup_dir/memory.db" || ! -f "$backup_dir/model_registry.db" ]]; then
  echo "Backup files not found in: $backup_dir" >&2
  exit 1
fi

if [[ -f "$backup_dir/checksums.txt" ]]; then
  (
    cd "$backup_dir"
    sha256sum -c checksums.txt
  )
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$(dirname "$memory_db")" "$(dirname "$registry_db")"

if [[ -f "$memory_db" ]]; then
  cp "$memory_db" "${memory_db}.pre_restore.${timestamp}"
fi
if [[ -f "$registry_db" ]]; then
  cp "$registry_db" "${registry_db}.pre_restore.${timestamp}"
fi

cp "$backup_dir/memory.db" "$memory_db"
cp "$backup_dir/model_registry.db" "$registry_db"

echo "SQLite restore complete."
echo "memory db: $memory_db"
echo "registry db: $registry_db"
