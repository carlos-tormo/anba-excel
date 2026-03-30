#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${1:-$ROOT_DIR/data/league.db}"
BACKUP_DIR="${2:-$ROOT_DIR/backups}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "Database not found: $DB_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%F-%H%M%S)"
OUT_PATH="$BACKUP_DIR/league-$STAMP.db"

sqlite3 "$DB_PATH" ".backup '$OUT_PATH'"
echo "Backup created: $OUT_PATH"
