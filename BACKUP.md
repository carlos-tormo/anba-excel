# Backup and Restore Runbook

## Scope
- Database file: `data/league.db`
- Backup artifact format: SQLite `.db` file copied using SQLite native `.backup` command

## Recommended policy
- Frequency: hourly backups
- Retention: keep 7 days
- Restore drill cadence: monthly

## Scripts in this repo
- Backup: `scripts/backup_db.sh`
- Prune old backups: `scripts/prune_backups.sh`
- Restore check: `scripts/restore_check.sh`

## One-time setup
1. Ensure `sqlite3` is installed on the host.
2. Make scripts executable:
   ```bash
   chmod +x scripts/backup_db.sh scripts/prune_backups.sh scripts/restore_check.sh
   ```
3. Choose backup destination directory (example: `/var/backups/anba`).

## Manual backup
```bash
scripts/backup_db.sh /absolute/path/to/data/league.db /var/backups/anba
```

## Manual prune
```bash
scripts/prune_backups.sh /var/backups/anba 7
```

## Monthly restore drill
1. Pick a recent backup file from `/var/backups/anba`.
2. Run:
   ```bash
   scripts/restore_check.sh /var/backups/anba/league-YYYY-MM-DD-HHMMSS.db /tmp/anba-restore-check.db
   ```
3. Confirm:
   - `PRAGMA integrity_check` returns `ok`
   - table checks and sample counts are returned
4. Optional app-level check:
   - start server against restored DB:
     ```bash
     python3 app/server.py --db /tmp/anba-restore-check.db --host 127.0.0.1 --port 8090
     ```
   - verify `/api/teams` and one `/api/teams/<CODE>` endpoint.

## Automation examples

### Cron (hourly backup + daily prune)
```cron
0 * * * * /absolute/path/to/repo/scripts/backup_db.sh /absolute/path/to/repo/data/league.db /var/backups/anba >> /var/log/anba-backup.log 2>&1
30 2 * * * /absolute/path/to/repo/scripts/prune_backups.sh /var/backups/anba 7 >> /var/log/anba-backup.log 2>&1
```

### systemd timer (alternative)
- Create `anba-backup.service` to call `backup_db.sh`.
- Create `anba-backup.timer` with `OnCalendar=hourly`.
- Create `anba-backup-prune.service` and timer with `OnCalendar=daily`.

## RTO / RPO template
- RPO target: `<= 1 hour`
- RTO target: `<= 30 minutes`
- Owner: `<name/team>`
- Last restore drill: `<YYYY-MM-DD>`
- Next scheduled drill: `<YYYY-MM-DD>`
