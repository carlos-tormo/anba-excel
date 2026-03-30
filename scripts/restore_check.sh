#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_PATH="${1:-}"
TMP_RESTORE_PATH="${2:-/tmp/anba-restore-check.db}"

if [[ -z "$BACKUP_PATH" ]]; then
  echo "Usage: $0 <backup-db-path> [tmp-restore-path]" >&2
  exit 1
fi

if [[ ! -f "$BACKUP_PATH" ]]; then
  echo "Backup file not found: $BACKUP_PATH" >&2
  exit 1
fi

cp "$BACKUP_PATH" "$TMP_RESTORE_PATH"

echo "Running integrity check..."
sqlite3 "$TMP_RESTORE_PATH" "PRAGMA integrity_check;" | grep -q '^ok$'

echo "Verifying required tables..."
required_count="$(
  sqlite3 "$TMP_RESTORE_PATH" "
  SELECT COUNT(*) FROM sqlite_master
  WHERE type='table'
    AND name IN ('teams','players','assets','dead_contracts','users','app_settings','sessions');
  "
)"
if [[ "$required_count" != "7" ]]; then
  echo "Missing required tables in restore copy (found $required_count of 7)." >&2
  exit 1
fi

echo "Sample counts:"
sqlite3 "$TMP_RESTORE_PATH" "
SELECT 'teams', COUNT(*) FROM teams;
SELECT 'players', COUNT(*) FROM players;
SELECT 'assets', COUNT(*) FROM assets;
SELECT 'dead_contracts', COUNT(*) FROM dead_contracts;
"

echo "Restore check passed for $BACKUP_PATH"
