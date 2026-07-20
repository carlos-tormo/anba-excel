"""Core SQLite persistence operations for active players."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable, Dict, Optional

try:
    from ...auth.policies import normalize_team_code
    from ...domain.contracts import normalize_bird_years
    from ...domain_rules import parse_amount_like, parse_bool, parse_float, parse_int
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_code
    from domain.contracts import normalize_bird_years
    from domain_rules import parse_amount_like, parse_bool, parse_float, parse_int

from .base import LeagueRepository


class PlayerRepository(LeagueRepository):
    def __init__(
        self,
        db: Any,
        *,
        now: Callable[[], str],
        select_columns: Callable[[], str],
        merge_profile: Callable[[Dict[str, Any]], Dict[str, Any]],
        record_transaction: Callable[..., Any],
        upsert_salary_history: Callable[..., bool],
        attach_salary_history: Callable[..., list[Dict[str, Any]]],
        player_text_fields: Any,
        player_bool_fields: Any,
        contract_seasons: Any,
        normalize_experience: Callable[[Any], Optional[int]],
        ensure_profile: Callable[..., Optional[int]],
        sync_row_state: Callable[..., Any],
        sync_generated_free_agents: Callable[..., Any],
        normalize_happiness: Callable[[Any], Any],
        normalize_profile_status: Callable[[Any], str],
        is_unavailable_profile_status: Callable[[Any], bool],
        make_profile_unavailable: Callable[..., Dict[str, int]],
        retained_rights_only: Callable[..., bool],
        resolve_profile: Callable[..., int],
        parse_salary_amount: Callable[[Any], Optional[float]],
        free_agent_type_unrestricted: str,
        free_agent_source_uncontracted: str,
    ) -> None:
        super().__init__(db)
        self._now = now
        self._select_columns = select_columns
        self._merge_profile = merge_profile
        self._record_transaction = record_transaction
        self._upsert_salary_history = upsert_salary_history
        self._attach_salary_history = attach_salary_history
        self._player_text_fields = tuple(player_text_fields)
        self._player_bool_fields = tuple(player_bool_fields)
        self._contract_seasons = tuple(contract_seasons)
        self._normalize_experience = normalize_experience
        self._ensure_profile = ensure_profile
        self._sync_row_state = sync_row_state
        self._sync_generated_free_agents = sync_generated_free_agents
        self._normalize_happiness = normalize_happiness
        self._normalize_profile_status = normalize_profile_status
        self._is_unavailable_profile_status = is_unavailable_profile_status
        self._make_profile_unavailable = make_profile_unavailable
        self._retained_rights_only = retained_rights_only
        self._resolve_profile = resolve_profile
        self._parse_salary_amount = parse_salary_amount
        self._free_agent_type_unrestricted = free_agent_type_unrestricted
        self._free_agent_source_uncontracted = free_agent_source_uncontracted

    def record(self, player_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                f"""SELECT {self._select_columns()}, t.code AS team_code, t.name AS team_name
                    FROM players p LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                    JOIN teams t ON t.id = p.team_id WHERE p.id = ?""",
                (player_id,),
            ).fetchone()
            if not row:
                return None
            player = dict(row)
            player["years_left"] = normalize_bird_years(player.get("years_left"))
            return self._merge_profile(player)

    def rows_from_cursor(self, cursor: Any, rows: Any) -> list[Dict[str, Any]]:
        return [self._merge_profile(dict(row)) for row in rows]

    def select_columns(self) -> str:
        return self._select_columns()

    def select_team(self, conn: Any, team_id: int) -> list[Dict[str, Any]]:
        cursor = conn.execute(
            f"""SELECT {self.select_columns()} FROM players p
                LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                WHERE p.team_id = ? ORDER BY p.row_order, p.id""",
            (team_id,),
        )
        players = self.rows_from_cursor(cursor, cursor.fetchall())
        return self._attach_salary_history(conn, players)

    def attach_salary_history(
        self,
        conn: Any,
        players: list[Dict[str, Any]],
    ) -> list[Dict[str, Any]]:
        """Attach persisted salary history to an existing player-like read model."""
        return self._attach_salary_history(conn, players)

    @staticmethod
    def attach_option_decisions(conn: Any, players: list[Dict[str, Any]], team_id: int) -> None:
        if not players:
            return
        player_ids = {int(player["id"]) for player in players if parse_int(player.get("id")) is not None}
        if not player_ids:
            return
        latest_by_key: Dict[tuple[int, str], Dict[str, Any]] = {}
        rows = conn.execute(
            """SELECT id, player_id, option_field, option_value, action, status,
                      created_at, updated_at, decided_at
               FROM gm_option_requests WHERE team_id = ? AND status = 'approved'
               ORDER BY COALESCE(decided_at, updated_at, created_at) DESC, id DESC""",
            (int(team_id),),
        ).fetchall()
        for row in rows:
            player_id = int(row["player_id"])
            if player_id not in player_ids:
                continue
            key = (player_id, str(row["option_field"] or "").strip())
            if key not in latest_by_key:
                latest_by_key[key] = {
                    "request_id": int(row["id"]),
                    "option_value": str(row["option_value"] or "").strip().upper(),
                    "action": str(row["action"] or "").strip().lower(),
                    "status": str(row["status"] or "").strip().lower(),
                }
        for player in players:
            player_id = parse_int(player.get("id"))
            player["option_decisions"] = {}
            if player_id is not None:
                player["option_decisions"] = {
                    option_field: decision
                    for (decision_player_id, option_field), decision in latest_by_key.items()
                    if decision_player_id == player_id
                }

    def create(
        self,
        team_code: str,
        payload: Dict[str, Any],
        conn: Optional[sqlite3.Connection] = None,
    ) -> Optional[int]:
        if conn is not None:
            return self.create_conn(conn, team_code, payload)
        with self.db.connect() as owned_conn:
            player_id = self.create_conn(owned_conn, team_code, payload)
            owned_conn.commit()
            return player_id

    def create_conn(
        self,
        conn: sqlite3.Connection,
        team_code: str,
        payload: Dict[str, Any],
    ) -> Optional[int]:
        normalized_team_code = team_code.upper()
        team = conn.execute("SELECT id FROM teams WHERE code = ?", (normalized_team_code,)).fetchone()
        if not team:
            return None
        max_order = conn.execute(
            "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?",
            (team["id"],),
        ).fetchone()["mx"]
        timestamp = self._now()
        values: Dict[str, Any] = {
            "name": payload.get("name", "New Player"),
            "bird_rights": payload.get("bird_rights"),
            "rating": payload.get("rating"),
            "position": payload.get("position"),
            "years_left": normalize_bird_years(payload.get("years_left")),
            "notes": payload.get("notes"),
            "reference_image_url": payload.get("reference_image_url"),
            "profile_notes": payload.get("profile_notes"),
            "experience_years": self._normalize_experience(payload.get("experience_years")),
        }
        for field in ("provisional_amounts", "partially_guaranteed", "signed_as_free_agent"):
            values[field] = 1 if parse_bool(payload.get(field)) else 0
        for season in self._contract_seasons:
            salary_field = f"salary_{season}_text"
            values[salary_field] = payload.get(salary_field)
            values[f"salary_{season}_num"] = self._parse_salary_amount(values[salary_field])
            values[f"salary_{season}_guaranteed_text"] = payload.get(f"salary_{season}_guaranteed_text")
            values[f"option_{season}"] = payload.get(f"option_{season}")
            values[f"salary_{season}_provisional"] = 1 if parse_bool(payload.get(f"salary_{season}_provisional")) else 0
            values[f"salary_{season}_partially_guaranteed"] = 1 if parse_bool(payload.get(f"salary_{season}_partially_guaranteed")) else 0

        profile_payload = dict(payload)
        for field in ("experience_years", "reference_image_url", "profile_notes"):
            profile_payload[field] = values[field]
        profile_id = self._resolve_profile(
            conn,
            profile_payload,
            name=values["name"],
            timestamp=timestamp,
            forbid_active_contract=True,
            require_available=True,
        )
        if parse_int(payload.get("profile_id")) is not None:
            conn.execute(
                """UPDATE player_profiles SET name = ?, experience_years = COALESCE(?, experience_years),
                          reference_image_url = COALESCE(NULLIF(?, ''), reference_image_url),
                          profile_notes = COALESCE(?, profile_notes), updated_at = ? WHERE id = ?""",
                (str(values["name"] or "").strip() or "New Player", values["experience_years"],
                 values["reference_image_url"], values["profile_notes"], timestamp, profile_id),
            )

        insert_values: Dict[str, Any] = {
            "team_id": team["id"],
            "profile_id": profile_id,
            "row_order": int(max_order) + 1,
            **values,
            "is_two_way": 1 if str(values["bird_rights"] or "").upper() == "TW" else 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        columns = list(insert_values)
        cur = conn.execute(
            f"INSERT INTO players ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            [insert_values[column] for column in columns],
        )
        player_id = int(cur.lastrowid)
        self._record_transaction(
            conn, profile_id, "create", f"Alta en {normalized_team_code}", player_id=player_id,
            team_code=team_code, details={"player_name": values["name"]}, created_at=timestamp,
        )
        return player_id

    def move(self, player_id: int, to_team_code: str) -> bool:
        with self.db.connect() as conn:
            player = conn.execute(
                """SELECT p.id, p.profile_id, COALESCE(pp.name, p.name) AS name, t.code AS from_team_code
                   FROM players p LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                   JOIN teams t ON t.id = p.team_id WHERE p.id = ?""",
                (player_id,),
            ).fetchone()
            target = conn.execute("SELECT id, code FROM teams WHERE code = ?", (to_team_code.upper(),)).fetchone()
            if not player or not target:
                return False
            max_row = conn.execute(
                "SELECT COALESCE(MAX(row_order), 3) AS mx FROM players WHERE team_id = ?", (target["id"],)
            ).fetchone()["mx"]
            timestamp = self._now()
            cur = conn.execute("UPDATE players SET team_id = ?, row_order = ?, updated_at = ? WHERE id = ?",
                               (target["id"], int(max_row) + 1, timestamp, player_id))
            if cur.rowcount:
                self._record_transaction(
                    conn, player["profile_id"], "move",
                    f"Movimiento de {player['from_team_code']} a {target['code']}",
                    player_id=player_id, team_code=target["code"], from_team_code=player["from_team_code"],
                    to_team_code=target["code"], details={"player_name": player["name"]}, created_at=timestamp,
                )
            conn.commit()
            return cur.rowcount > 0

    def delete(self, player_id: int) -> bool:
        with self.db.connect() as conn:
            player = conn.execute(
                """SELECT p.profile_id, COALESCE(pp.name, p.name) AS name, t.code AS team_code
                   FROM players p LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                   JOIN teams t ON t.id = p.team_id WHERE p.id = ?""",
                (player_id,),
            ).fetchone()
            cur = conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
            if cur.rowcount and player:
                self._record_transaction(
                    conn, player["profile_id"], "delete", f"Contrato eliminado de {player['team_code']}",
                    player_id=player_id, team_code=player["team_code"], details={"player_name": player["name"]},
                )
            conn.commit()
            return cur.rowcount > 0

    def update(self, player_id: int, payload: Dict[str, Any]) -> bool:
        assignments = []
        values = []
        for field in sorted(self._player_text_fields):
            if field in payload:
                assignments.append(f"{field} = ?")
                values.append(normalize_bird_years(payload[field]) if field == "years_left" else payload[field])
        for field in sorted(self._player_bool_fields):
            if field in payload:
                assignments.append(f"{field} = ?")
                values.append(1 if parse_bool(payload[field]) else 0)
        for season in self._contract_seasons:
            field = f"salary_{season}_text"
            if field in payload:
                assignments.append(f"salary_{season}_num = ?")
                values.append(parse_float(payload[field]))
        if "bird_rights" in payload:
            assignments.append("is_two_way = ?")
            values.append(1 if str(payload["bird_rights"]).upper() == "TW" else 0)
        if "experience_years" in payload:
            assignments.append("experience_years = ?")
            values.append(self._normalize_experience(payload.get("experience_years")))
        profile_fields = {
            "name", "experience_years", "reference_image_url", "profile_notes",
            "date_of_birth", "nationality", "yos_source", "transaction_notes",
        }
        if not assignments and not any(field in payload for field in profile_fields):
            return False
        timestamp = self._now()
        with self.db.connect() as conn:
            if assignments:
                assignments.append("updated_at = ?")
                cur = conn.execute(
                    f"UPDATE players SET {', '.join(assignments)} WHERE id = ?",
                    [*values, timestamp, player_id],
                )
                player_exists = cur.rowcount > 0
            else:
                player_exists = conn.execute("SELECT 1 FROM players WHERE id = ?", (player_id,)).fetchone() is not None
            if not player_exists:
                conn.commit()
                return False
            profile_updates: Dict[str, Any] = {}
            if "name" in payload:
                profile_updates["name"] = str(payload.get("name") or "").strip() or "New Player"
            if "experience_years" in payload:
                profile_updates["experience_years"] = self._normalize_experience(payload.get("experience_years"))
            for field in ("reference_image_url", "profile_notes", "date_of_birth", "nationality", "yos_source", "transaction_notes"):
                if field in payload:
                    profile_updates[field] = str(payload.get(field) or "").strip() or None
            if profile_updates:
                profile_id = self._ensure_profile(conn, player_id, timestamp)
                if profile_id is not None:
                    conn.execute(
                        f"UPDATE player_profiles SET {', '.join(f'{field} = ?' for field in profile_updates)}, updated_at = ? WHERE id = ?",
                        [*profile_updates.values(), timestamp, profile_id],
                    )
            self._sync_row_state(conn, player_id, timestamp)
            self._sync_generated_free_agents(conn, payload)
            conn.commit()
            return True

    def remove_from_roster(self, player_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                f"""SELECT {self._select_columns()}, t.code AS team_code, t.name AS team_name
                    FROM players p LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                    JOIN teams t ON t.id = p.team_id WHERE p.id = ?""",
                (player_id,),
            ).fetchone()
            if not row:
                return None
            player = dict(row)
            player["years_left"] = normalize_bird_years(player.get("years_left"))
            player = self._merge_profile(player)
            timestamp = self._now()
            profile_id = self._ensure_profile(conn, player_id, timestamp)
            if profile_id is None:
                return None
            team_code = normalize_team_code(player.get("team_code")) or str(player.get("team_code") or "").upper()
            player_name = str(player.get("name") or "Agente libre").strip() or "Agente libre"
            existing = conn.execute("SELECT id FROM free_agents WHERE profile_id = ? LIMIT 1", (int(profile_id),)).fetchone()
            if existing:
                free_agent_id = int(existing["id"])
                conn.execute(
                    """UPDATE free_agents SET name = ?, position = ?, bird_rights = NULL, rating = ?,
                              years_left = NULL, free_agent_type = ?, source = ?, rights_team_code = NULL,
                              notes = NULL, updated_at = ? WHERE id = ?""",
                    (player_name, str(player.get("position") or "").strip() or None,
                     str(player.get("rating") or "").strip() or None, self._free_agent_type_unrestricted,
                     self._free_agent_source_uncontracted, timestamp, free_agent_id),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO free_agents (
                           profile_id, name, position, bird_rights, rating, years_left,
                           free_agent_type, source, rights_team_code, notes, created_at, updated_at
                       ) VALUES (?, ?, ?, NULL, ?, NULL, ?, ?, NULL, NULL, ?, ?)""",
                    (int(profile_id), player_name, str(player.get("position") or "").strip() or None,
                     str(player.get("rating") or "").strip() or None, self._free_agent_type_unrestricted,
                     self._free_agent_source_uncontracted, timestamp, timestamp),
                )
                free_agent_id = int(cur.lastrowid)
            conn.execute("DELETE FROM players WHERE id = ?", (player_id,))
            self._record_transaction(
                conn, profile_id, "remove", f"Eliminado del roster de {team_code}",
                player_id=player_id, free_agent_id=free_agent_id, team_code=team_code, from_team_code=team_code,
                details={"player_name": player_name}, created_at=timestamp,
            )
            conn.commit()
            return {"team_code": team_code, "team_name": player.get("team_name"), "player_name": player_name,
                    "profile_id": int(profile_id), "free_agent_id": free_agent_id}

    def update_profile(self, profile_id: int, payload: Dict[str, Any]) -> bool:
        fields: Dict[str, Any] = {}
        update_rights_team = "rights_team_code" in payload
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                return False
            fields["name"] = name
        for field in (
            "date_of_birth", "nationality", "yos_source", "reference_image_url",
            "profile_notes", "transaction_notes",
        ):
            if field in payload:
                fields[field] = str(payload.get(field) or "").strip() or None
        if "experience_years" in payload:
            fields["experience_years"] = self._normalize_experience(payload.get("experience_years"))
        if "happiness" in payload:
            fields["happiness"] = self._normalize_happiness(payload.get("happiness"))
        if "profile_status" in payload:
            fields["profile_status"] = self._normalize_profile_status(payload.get("profile_status"))
        if not fields and not update_rights_team:
            return False

        timestamp = self._now()
        with self.db.connect() as conn:
            changed = False
            if fields:
                cur = conn.execute(
                    f"UPDATE player_profiles SET {', '.join(f'{field} = ?' for field in fields)}, "
                    "updated_at = ? WHERE id = ?",
                    [*fields.values(), timestamp, profile_id],
                )
                changed = bool(cur.rowcount)
                if cur.rowcount:
                    if "name" in fields:
                        conn.execute("UPDATE players SET name = ?, updated_at = ? WHERE profile_id = ?", (fields["name"], timestamp, profile_id))
                        conn.execute("UPDATE free_agents SET name = ?, updated_at = ? WHERE profile_id = ?", (fields["name"], timestamp, profile_id))
                        conn.execute("UPDATE dead_contracts SET label = ?, updated_at = ? WHERE profile_id = ?", (fields["name"], timestamp, profile_id))
                    if "experience_years" in fields:
                        conn.execute("UPDATE players SET experience_years = ?, updated_at = ? WHERE profile_id = ?", (fields["experience_years"], timestamp, profile_id))
                    if "reference_image_url" in fields:
                        conn.execute("UPDATE players SET reference_image_url = ?, updated_at = ? WHERE profile_id = ?", (fields["reference_image_url"], timestamp, profile_id))
                    if "profile_notes" in fields:
                        conn.execute("UPDATE players SET profile_notes = ?, updated_at = ? WHERE profile_id = ?", (fields["profile_notes"], timestamp, profile_id))
                    if "profile_status" in fields and self._is_unavailable_profile_status(fields["profile_status"]):
                        self._make_profile_unavailable(conn, int(profile_id), fields["profile_status"], timestamp)
            elif not conn.execute("SELECT id FROM player_profiles WHERE id = ?", (profile_id,)).fetchone():
                return False

            if update_rights_team:
                status_row = conn.execute("SELECT profile_status FROM player_profiles WHERE id = ?", (profile_id,)).fetchone()
                if status_row and self._is_unavailable_profile_status(status_row["profile_status"]):
                    raise ValueError("profile_unavailable")
                settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings").fetchall()}
                current_year = parse_int(settings.get("current_year")) or self._contract_seasons[0]
                roster_rows = conn.execute("SELECT * FROM players WHERE profile_id = ? ORDER BY id", (profile_id,)).fetchall()
                if any(not self._retained_rights_only(row, int(current_year), conn) for row in roster_rows):
                    raise ValueError("profile_has_active_contract")
                team_code = normalize_team_code(payload.get("rights_team_code"))
                if team_code and not conn.execute("SELECT code FROM teams WHERE code = ?", (team_code,)).fetchone():
                    raise ValueError("invalid_team_code")
                profile_row = conn.execute("SELECT name FROM player_profiles WHERE id = ?", (profile_id,)).fetchone()
                if not profile_row:
                    return False
                free_agent_row = conn.execute("SELECT id FROM free_agents WHERE profile_id = ? ORDER BY id LIMIT 1", (profile_id,)).fetchone()
                if free_agent_row:
                    cur = conn.execute(
                        "UPDATE free_agents SET rights_team_code = ?, updated_at = ? WHERE id = ?",
                        (team_code, timestamp, int(free_agent_row["id"])),
                    )
                    changed = changed or bool(cur.rowcount)
                else:
                    conn.execute(
                        """INSERT INTO free_agents (
                               profile_id, name, position, bird_rights, rating, years_left,
                               free_agent_type, source, rights_team_code, agent, notes, created_at, updated_at
                           ) VALUES (?, ?, NULL, NULL, NULL, NULL, ?, ?, ?, NULL, ?, ?, ?)""",
                        (profile_id, str(profile_row["name"] or "").strip() or "New Player",
                         self._free_agent_type_unrestricted, self._free_agent_source_uncontracted,
                         team_code, "Agente libre sin contrato activo.", timestamp, timestamp),
                    )
                    changed = True
            conn.commit()
            return changed

    def create_transaction(self, profile_id: int, payload: Dict[str, Any]) -> Optional[int]:
        summary = str(payload.get("summary") or "").strip()
        if not summary:
            return None
        created_at = str(payload.get("created_at") or "").strip() or self._now()
        with self.db.connect() as conn:
            if not conn.execute("SELECT id FROM player_profiles WHERE id = ?", (profile_id,)).fetchone():
                return None
            cur = conn.execute(
                """INSERT INTO player_transactions (
                       profile_id, player_id, free_agent_id, dead_contract_id, action,
                       team_code, from_team_code, to_team_code, summary, details_json, source_log_id, created_at
                   ) VALUES (?, NULL, NULL, NULL, ?, ?, ?, ?, ?, ?, NULL, ?)""",
                (profile_id, str(payload.get("action") or "manual").strip().lower() or "manual",
                 normalize_team_code(payload.get("team_code")), normalize_team_code(payload.get("from_team_code")),
                 normalize_team_code(payload.get("to_team_code")), summary,
                 json.dumps({"manual": True}, ensure_ascii=True), created_at),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_transaction(self, transaction_id: int, payload: Dict[str, Any]) -> bool:
        fields: Dict[str, Any] = {}
        if "summary" in payload:
            summary = str(payload.get("summary") or "").strip()
            if not summary:
                return False
            fields["summary"] = summary
        if "action" in payload:
            fields["action"] = str(payload.get("action") or "").strip().lower() or "manual"
        for key in ("team_code", "from_team_code", "to_team_code"):
            if key in payload:
                fields[key] = normalize_team_code(payload.get(key))
        if "created_at" in payload:
            fields["created_at"] = str(payload.get("created_at") or "").strip() or self._now()
        return self._update_fields("player_transactions", transaction_id, fields)

    def delete_transaction(self, transaction_id: int) -> bool:
        return self._delete_by_id("player_transactions", transaction_id)

    def create_salary_history(self, profile_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        season_year = parse_int(payload.get("season_year"))
        if season_year is None or season_year < 1900 or season_year > 2200:
            raise ValueError("invalid_season_year")
        salary_text = str(payload.get("salary_text") or payload.get("salary") or "").strip()
        salary_num = parse_float(payload.get("salary_num"))
        if salary_num is None and salary_text:
            salary_num = parse_amount_like(salary_text)
        if not salary_text and salary_num is None:
            raise ValueError("salary_required")
        timestamp = self._now()
        with self.db.connect() as conn:
            if not conn.execute("SELECT id FROM player_profiles WHERE id = ?", (profile_id,)).fetchone():
                return None
            self._upsert_salary_history(
                conn, profile_id=profile_id, player_id=payload.get("player_id"),
                team_code=normalize_team_code(payload.get("team_code") or payload.get("last_team")),
                season_year=season_year, salary_text=salary_text, salary_num=salary_num, source="manual",
                salary_type=str(payload.get("salary_type") or payload.get("type") or "").strip() or None,
                timestamp=timestamp,
            )
            row = conn.execute(
                """SELECT id, profile_id, player_id, team_code, season_year, salary_text,
                          salary_num, salary_type, source, created_at, updated_at
                   FROM player_salary_history WHERE profile_id = ? AND season_year = ?""",
                (profile_id, season_year),
            ).fetchone()
            conn.commit()
            return dict(row) if row else None

    def list_salary_history(self, profile_id: int) -> list[Dict[str, Any]]:
        parsed_profile_id = parse_int(profile_id)
        if parsed_profile_id is None:
            return []
        with self.db.connect() as conn:
            if not self._table_exists(conn, "player_salary_history"):
                return []
            rows = conn.execute(
                """SELECT id, profile_id, player_id, team_code, season_year, salary_text,
                          salary_num, salary_type, source, created_at, updated_at
                   FROM player_salary_history WHERE profile_id = ?
                   ORDER BY season_year DESC, id DESC""",
                (parsed_profile_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_salary_history(self, salary_history_id: int, payload: Dict[str, Any]) -> bool:
        fields: Dict[str, Any] = {}
        if "season_year" in payload:
            season_year = parse_int(payload.get("season_year"))
            if season_year is None or season_year < 1900 or season_year > 2200:
                raise ValueError("invalid_season_year")
            fields["season_year"] = season_year
        if "salary_text" in payload or "salary" in payload:
            raw = payload.get("salary_text") if "salary_text" in payload else payload.get("salary")
            text = str(raw or "").strip() or None
            fields.update({"salary_text": text, "salary_num": parse_amount_like(text) if text else None})
        if "salary_num" in payload and "salary_text" not in payload and "salary" not in payload:
            fields["salary_num"] = parse_float(payload.get("salary_num"))
        if "salary_type" in payload or "type" in payload:
            raw_type = payload.get("salary_type") if "salary_type" in payload else payload.get("type")
            fields["salary_type"] = str(raw_type or "").strip() or None
        if "team_code" in payload or "last_team" in payload:
            fields["team_code"] = normalize_team_code(
                payload.get("team_code") if "team_code" in payload else payload.get("last_team")
            )
        if not fields:
            return False
        fields.update({"source": "manual", "updated_at": self._now()})
        try:
            return self._update_fields("player_salary_history", salary_history_id, fields)
        except sqlite3.IntegrityError as err:
            raise ValueError("duplicate_salary_history") from err

    def delete_salary_history(self, salary_history_id: int) -> bool:
        return self._delete_by_id("player_salary_history", salary_history_id)

    def delete_profile(self, profile_id: int) -> Dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT id, name, date_of_birth, nationality, experience_years, yos_source,
                          reference_image_url, profile_notes, transaction_notes, created_at, updated_at
                   FROM player_profiles WHERE id = ?""",
                (profile_id,),
            ).fetchone()
            if not row:
                return {"ok": False, "error": "not_found"}
            profile = dict(row)
            free_agent_ids = [int(item["id"]) for item in conn.execute(
                "SELECT id FROM free_agents WHERE profile_id = ?", (profile_id,)
            ).fetchall()]
            request_count = 0
            if free_agent_ids:
                placeholders = ",".join("?" for _ in free_agent_ids)
                request_count = int(conn.execute(
                    f"SELECT COUNT(*) FROM gm_free_agent_offer_requests WHERE free_agent_id IN ({placeholders})",
                    free_agent_ids,
                ).fetchone()[0])
            counts = {
                "active_contracts": self._count(conn, "players", profile_id),
                "free_agents": self._count(conn, "free_agents", profile_id),
                "dead_contracts": self._count(conn, "dead_contracts", profile_id),
                "transactions": self._count(conn, "player_transactions", profile_id),
                "discord_offer_threads": self._count(conn, "discord_free_agent_offer_threads", profile_id),
                "free_agent_offer_requests": request_count,
                "salary_history": self._count(conn, "player_salary_history", profile_id) if self._table_exists(conn, "player_salary_history") else 0,
            }
            for table in ("player_transactions", "discord_free_agent_offer_threads"):
                conn.execute(f"DELETE FROM {table} WHERE profile_id = ?", (profile_id,))
            if self._table_exists(conn, "player_salary_history"):
                conn.execute("DELETE FROM player_salary_history WHERE profile_id = ?", (profile_id,))
            if free_agent_ids:
                placeholders = ",".join("?" for _ in free_agent_ids)
                conn.execute(f"DELETE FROM gm_free_agent_offer_requests WHERE free_agent_id IN ({placeholders})", free_agent_ids)
            for table in ("players", "free_agents", "dead_contracts"):
                conn.execute(f"DELETE FROM {table} WHERE profile_id = ?", (profile_id,))
            cur = conn.execute("DELETE FROM player_profiles WHERE id = ?", (profile_id,))
            conn.commit()
            return {"ok": True, "profile": profile, "deleted": counts} if cur.rowcount > 0 else {"ok": False, "error": "not_found"}

    def _update_fields(self, table: str, entity_id: int, fields: Dict[str, Any]) -> bool:
        if not fields:
            return False
        with self.db.connect() as conn:
            cur = conn.execute(
                f"UPDATE {table} SET {', '.join(f'{key} = ?' for key in fields)} WHERE id = ?",
                [*fields.values(), entity_id],
            )
            conn.commit()
            return cur.rowcount > 0

    def _delete_by_id(self, table: str, entity_id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (entity_id,))
            conn.commit()
            return cur.rowcount > 0

    @staticmethod
    def _table_exists(conn: Any, table: str) -> bool:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1", (table,)).fetchone() is not None

    @staticmethod
    def _count(conn: Any, table: str, profile_id: int) -> int:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE profile_id = ?", (profile_id,)).fetchone()[0])
