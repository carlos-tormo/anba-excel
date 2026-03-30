# anba-excel

Local roster management app that replicates the team-tab workflow from `ROSTERS.xlsx` with editable contracts, player movement, and salary calculations.

## Features
- Imports 30 NBA team tabs from an `.xlsx` file (no external Python dependencies).
- Team-by-team roster view with editable player fields and contract years.
- Move players between teams instantly.
- Manage team assets (draft picks, exceptions, dead-cap entries).
- Salary summary cards (cap figure, payroll, cap room, luxury/apron headroom).
- SQLite-backed data for fast edits.

## Quick start
1. Import workbook data into SQLite:
   ```bash
   python3 app/xlsx_import.py --xlsx /Users/carlos.tormo/Downloads/ROSTERS.xlsx --db data/league.db
   ```
2. Configure environment:
   ```bash
   cp .env.example .env
   # edit .env with your real values
   ```
3. Run the server:
   ```bash
   python3 app/server.py --db data/league.db --host 127.0.0.1 --port 8000
   ```
4. Open:
   ```
   Guest view: http://127.0.0.1:8000
   Admin login: http://127.0.0.1:8000/login
   Admin panel: http://127.0.0.1:8000/admin
   ```

## Notes
- Contract values accept either numbers (e.g. `15000000`) or labels (e.g. `NB`, `FB`, `PO`).
- Calculations use numeric contract values and ignore non-numeric labels, matching spreadsheet-style behavior.
- Cap constants are imported from each team tab (Salary Cap, Luxury, 1st Apron, 2nd Apron), and default to common values if missing.
- Team icons are loaded from `web/team-icons/<CODE>.svg` or `web/team-icons/<CODE>.png` (for all 30 team codes). If missing, the app shows a code fallback.
- Write operations (`POST/PATCH/DELETE`) require admin authentication via session cookie.
- If `ADMIN_USER` and `ADMIN_PASSWORD` are not set, defaults are `admin` / `admin123` (change these in real usage).
- Google OAuth sign-in is optional. If configured, users can sign in with Google:
  - Emails in `ADMIN_EMAILS` get `admin` role.
  - Other Google users get `viewer` role (read-only).
- Admin panel includes a global `Salary Cap 25/26` setting used across views for salary `% of cap` and cap-room calculations.
- The server auto-loads `.env` from project root. You can override file path with `ENV_FILE=/path/to/.env`.

## Google OAuth setup
1. In Google Cloud Console, create OAuth 2.0 Client ID for **Web application**.
2. Add this Authorized redirect URI:
   - `http://127.0.0.1:8000/api/auth/google/callback`
3. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` env vars before starting the server.

## Deploying Publicly
1. Put the app behind HTTPS (reverse proxy like Nginx/Caddy).
2. Set production env vars in your process manager (systemd, Docker, Render, Railway, etc.) instead of relying on a local `.env` file.
3. Update `GOOGLE_REDIRECT_URI` to your public domain callback URL.
4. Keep secrets out of git and rotate credentials if exposed.
