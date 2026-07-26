"""Shared SQL helpers for user-to-team assignment read models."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

try:
    from ...auth.policies import normalize_team_codes
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_codes


def user_display_name(row: Any) -> str:
    username = str(row["username"] or "").strip() if "username" in row.keys() else ""
    display_name = str(row["display_name"] or "").strip() if "display_name" in row.keys() else ""
    email = str(row["email"] or "").strip() if "email" in row.keys() else ""
    return username or display_name or email


def assigned_gm_names_by_team(
    conn: Any,
    team_codes: Optional[Iterable[Any]] = None,
) -> Dict[str, str]:
    codes = normalize_team_codes(list(team_codes or []))
    params: List[Any] = []
    where = ""
    if codes:
        where = f"WHERE t.code IN ({','.join('?' for _ in codes)})"
        params.extend(codes)
    rows = conn.execute(
        f"""
        SELECT t.code AS team_code, u.username, u.display_name, u.email
        FROM user_team_assignments a
        JOIN users u ON u.id = a.user_id
        JOIN teams t ON t.id = a.team_id
        {where}
        ORDER BY t.code,
                 lower(COALESCE(NULLIF(TRIM(u.username), ''), NULLIF(TRIM(u.display_name), ''), u.email)),
                 u.id
        """,
        params,
    ).fetchall()
    names_by_team: Dict[str, List[str]] = {}
    for row in rows:
        code = str(row["team_code"] or "").strip().upper()
        name = user_display_name(row)
        if code and name and name not in names_by_team.setdefault(code, []):
            names_by_team[code].append(name)
    return {code: ", ".join(names) for code, names in names_by_team.items()}
