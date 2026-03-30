#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${1:-$ROOT_DIR/backups}"
RETENTION_DAYS="${2:-7}"

if [[ ! -d "$BACKUP_DIR" ]]; then
  echo "Backup directory not found: $BACKUP_DIR"
  exit 0
fi

if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
  echo "RETENTION_DAYS must be a non-negative integer" >&2
  exit 1
fi

find "$BACKUP_DIR" -type f -name 'league-*.db' -mtime "+$RETENTION_DAYS" -delete
echo "Pruned backups older than $RETENTION_DAYS days in $BACKUP_DIR"
