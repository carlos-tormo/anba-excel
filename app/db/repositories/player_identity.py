"""Persistence boundary for player identity and profile synchronization."""

from __future__ import annotations

from contextlib import contextmanager
import json
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional

try:
    from ...domain_rules import (
        cap_hold_amount,
        cap_hold_bird_code_from_years,
        has_standard_cap_hold_marker,
        is_exhibit10_player,
        is_two_way_player,
        normalize_bird_years,
        parse_amount_like,
        parse_bool,
        parse_float,
        parse_int,
        row_salary_num,
        season_label,
    )
except ImportError:  # pragma: no cover
    from domain_rules import (
        cap_hold_amount,
        cap_hold_bird_code_from_years,
        has_standard_cap_hold_marker,
        is_exhibit10_player,
        is_two_way_player,
        normalize_bird_years,
        parse_amount_like,
        parse_bool,
        parse_float,
        parse_int,
        row_salary_num,
        season_label,
    )

from .base import LeagueRepository


class PlayerIdentityRepository(LeagueRepository):
    def __init__(
        self,
        db: Any,
        *,
        now: Optional[Callable[[], str]] = None,
        contract_seasons: Optional[Iterable[int]] = None,
        retained_rights_only: Optional[Callable[..., bool]] = None,
        current_year: Optional[Callable[..., int]] = None,
        record_transaction: Optional[Callable[..., Any]] = None,
        table_exists: Optional[Callable[..., bool]] = None,
        select_team_players: Optional[Callable[..., List[Dict[str, Any]]]] = None,
        attach_option_decisions: Optional[Callable[..., Any]] = None,
        cleanup_minimum_targets: Optional[Callable[..., Any]] = None,
        ensure_profile: Optional[Callable[..., Optional[int]]] = None,
        unavailable_profile_status: Optional[Callable[[Any], bool]] = None,
        free_agent_type_restricted: str = "Restringido",
        free_agent_type_unrestricted: str = "No restringido",
        free_agent_source_cap_hold: str = "cap_hold",
        free_agent_source_renounced_rights: str = "renounced_rights",
        free_agent_source_uncontracted: str = "uncontracted_profile",
        unavailable_profile_statuses: Optional[Iterable[str]] = None,
        profile_repository: Any = None,
    ) -> None:
        super().__init__(db)
        self._now = now
        self._contract_seasons = tuple(contract_seasons or ())
        self._retained_rights_only = retained_rights_only
        self._current_year = current_year
        self._record_transaction = record_transaction
        self._table_exists = table_exists
        self._select_team_players = select_team_players
        self._attach_option_decisions = attach_option_decisions
        self._cleanup_minimum_targets = cleanup_minimum_targets
        self._ensure_profile = ensure_profile
        self._unavailable_profile_status = unavailable_profile_status
        self._free_agent_type_restricted = free_agent_type_restricted
        self._free_agent_type_unrestricted = free_agent_type_unrestricted
        self._free_agent_source_cap_hold = free_agent_source_cap_hold
        self._free_agent_source_renounced_rights = free_agent_source_renounced_rights
        self._free_agent_source_uncontracted = free_agent_source_uncontracted
        self._unavailable_profile_statuses = tuple(unavailable_profile_statuses or ("outside_nba", "retired"))
        self._profile_repository = profile_repository

    @property
    def configured(self) -> bool:
        return all((self._now, self._contract_seasons, self._retained_rights_only,
                    self._current_year, self._record_transaction, self._table_exists))

    @staticmethod
    def settings(conn: Any) -> Dict[str, str]:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    def update_profile(self, profile_id: int, payload: Any) -> Any:
        if not self._profile_repository:
            raise RuntimeError("player_identity_repository_not_configured")
        return self._profile_repository.update_profile(profile_id, payload)

    def delete_profile(self, profile_id: int) -> Any:
        if not self._profile_repository:
            raise RuntimeError("player_identity_repository_not_configured")
        return self._profile_repository.delete_profile(profile_id)

    def merge_profiles(self, source_profile_id: int, target_profile_id: int) -> Any:
        if not self.configured:
            raise RuntimeError("player_identity_repository_not_configured")
        return self._merge_profiles(source_profile_id, target_profile_id)

    def integrity_report(self) -> Any:
        if not self.configured:
            raise RuntimeError("player_identity_repository_not_configured")
        checks = (
            ("players_missing_profile", "SELECT id FROM players WHERE profile_id IS NULL ORDER BY id"),
            ("players_orphan_profile", """SELECT p.id FROM players p LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                WHERE p.profile_id IS NOT NULL AND pp.id IS NULL ORDER BY p.id"""),
            ("free_agents_missing_profile", "SELECT id FROM free_agents WHERE profile_id IS NULL ORDER BY id"),
            ("free_agents_orphan_profile", """SELECT f.id FROM free_agents f LEFT JOIN player_profiles pp ON pp.id = f.profile_id
                WHERE f.profile_id IS NOT NULL AND pp.id IS NULL ORDER BY f.id"""),
            ("dead_contracts_missing_profile", "SELECT id FROM dead_contracts WHERE profile_id IS NULL ORDER BY id"),
            ("dead_contracts_orphan_profile", """SELECT d.id FROM dead_contracts d LEFT JOIN player_profiles pp ON pp.id = d.profile_id
                WHERE d.profile_id IS NOT NULL AND pp.id IS NULL ORDER BY d.id"""),
            ("active_and_free_agent_profiles", """SELECT DISTINCT p.profile_id FROM players p
                JOIN free_agents f ON f.profile_id = p.profile_id WHERE p.profile_id IS NOT NULL
                AND COALESCE(f.source, '') != 'cap_hold' ORDER BY p.profile_id"""),
            ("transaction_orphan_profiles", """SELECT tx.id FROM player_transactions tx
                LEFT JOIN player_profiles pp ON pp.id = tx.profile_id WHERE pp.id IS NULL ORDER BY tx.id"""),
            ("salary_history_orphan_profiles", """SELECT h.id FROM player_salary_history h
                LEFT JOIN player_profiles pp ON pp.id = h.profile_id
                WHERE h.profile_id IS NOT NULL AND pp.id IS NULL ORDER BY h.id"""),
            ("transaction_player_profile_mismatch", """SELECT tx.id FROM player_transactions tx
                JOIN players p ON p.id = tx.player_id WHERE tx.player_id IS NOT NULL
                AND p.profile_id IS NOT NULL AND tx.profile_id != p.profile_id ORDER BY tx.id"""),
            ("transaction_free_agent_profile_mismatch", """SELECT tx.id FROM player_transactions tx
                JOIN free_agents f ON f.id = tx.free_agent_id WHERE tx.free_agent_id IS NOT NULL
                AND f.profile_id IS NOT NULL AND tx.profile_id != f.profile_id ORDER BY tx.id"""),
            ("transaction_dead_contract_profile_mismatch", """SELECT tx.id FROM player_transactions tx
                JOIN dead_contracts d ON d.id = tx.dead_contract_id WHERE tx.dead_contract_id IS NOT NULL
                AND d.profile_id IS NOT NULL AND tx.profile_id != d.profile_id ORDER BY tx.id"""),
            ("draft_pick_holdings_orphan_asset", """SELECT h.id FROM draft_pick_holdings h
                LEFT JOIN assets a ON a.id = h.asset_id WHERE h.asset_id IS NOT NULL AND a.id IS NULL ORDER BY h.id"""),
            ("draft_pick_assets_missing_identity", """SELECT a.id FROM assets a
                LEFT JOIN draft_pick_holdings h ON h.asset_id = a.id WHERE a.asset_type = 'draft_pick'
                AND a.year IS NOT NULL AND COALESCE(a.draft_round, '') != '' AND h.id IS NULL ORDER BY a.id"""),
        )
        errors: List[Dict[str, Any]] = []
        with self.db.connect() as conn:
            foreign_keys = conn.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_keys:
                errors.append({"check": "foreign_key_check", "ids": [
                    {"table": row["table"], "rowid": row["rowid"], "parent": row["parent"], "fkid": row["fkid"]}
                    for row in foreign_keys
                ]})
            for check_name, query in checks:
                rows = conn.execute(query).fetchall()
                if rows:
                    first_key = rows[0].keys()[0]
                    errors.append({"check": check_name, "ids": [row[first_key] for row in rows]})
            current_year = int(self._current_year(conn))
            active_by_profile: Dict[int, List[int]] = {}
            for row in conn.execute(
                """SELECT p.*, t.code AS team_code FROM players p JOIN teams t ON t.id = p.team_id
                   WHERE p.profile_id IS NOT NULL ORDER BY p.profile_id, p.id"""
            ).fetchall():
                profile_id = parse_int(row["profile_id"])
                if profile_id is not None and not self._retained_rights_only(row, current_year, conn):
                    active_by_profile.setdefault(profile_id, []).append(int(row["id"]))
            duplicates = [
                {"profile_id": profile_id, "player_ids": player_ids}
                for profile_id, player_ids in active_by_profile.items() if len(player_ids) > 1
            ]
            if duplicates:
                errors.append({"check": "duplicate_active_contract_profiles", "ids": duplicates})
        return {"ok": not errors, "errors": errors}

    def assert_integrity(self) -> None:
        report = self.integrity_report()
        if not report["ok"]:
            raise AssertionError(json.dumps(report["errors"], ensure_ascii=True, sort_keys=True))

    def _merge_profiles(self, source_profile_id: int, target_profile_id: int) -> Dict[str, Any]:
        source_id = parse_int(source_profile_id)
        target_id = parse_int(target_profile_id)
        if source_id is None or target_id is None or source_id == target_id:
            return {"ok": False, "error": "invalid_profile_id"}

        timestamp = self._now()
        with self.db.connect() as conn:
            source = conn.execute("SELECT id, name FROM player_profiles WHERE id = ?", (source_id,)).fetchone()
            target = conn.execute("SELECT id, name FROM player_profiles WHERE id = ?", (target_id,)).fetchone()
            if not source or not target:
                return {"ok": False, "error": "not_found"}
            settings = {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM app_settings")}
            current_year = parse_int(settings.get("current_year")) or self._contract_seasons[0]

            def player_rows(profile_id: int) -> List[Any]:
                return conn.execute(
                    """SELECT p.*, t.code AS team_code FROM players p JOIN teams t ON t.id = p.team_id
                       WHERE p.profile_id = ? ORDER BY p.id""",
                    (profile_id,),
                ).fetchall()

            source_players = player_rows(source_id)
            target_players = player_rows(target_id)
            source_active = [row for row in source_players if not self._retained_rights_only(row, current_year, conn)]
            target_active = [row for row in target_players if not self._retained_rights_only(row, current_year, conn)]
            if source_active and target_active:
                return {"ok": False, "error": "active_contract_conflict"}

            deleted_player_rows = 0
            moved_player_rows = 0
            if source_players:
                if target_players:
                    if source_active and not target_active:
                        for row in target_players:
                            conn.execute("DELETE FROM players WHERE id = ?", (int(row["id"]),))
                            deleted_player_rows += 1
                        moved_player_rows += int(conn.execute(
                            "UPDATE players SET profile_id = ?, updated_at = ? WHERE profile_id = ?",
                            (target_id, timestamp, source_id),
                        ).rowcount or 0)
                    else:
                        for row in source_players:
                            conn.execute("DELETE FROM players WHERE id = ?", (int(row["id"]),))
                            deleted_player_rows += 1
                else:
                    moved_player_rows += int(conn.execute(
                        "UPDATE players SET profile_id = ?, updated_at = ? WHERE profile_id = ?",
                        (target_id, timestamp, source_id),
                    ).rowcount or 0)

            final_has_active_contract = any(
                not self._retained_rights_only(row, current_year, conn) for row in player_rows(target_id)
            )
            deleted_free_agents = 0
            if final_has_active_contract:
                free_agent_ids = [int(row["id"]) for row in conn.execute(
                    "SELECT id FROM free_agents WHERE profile_id IN (?, ?)", (source_id, target_id)
                ).fetchall()]
                if free_agent_ids:
                    placeholders = ",".join("?" for _ in free_agent_ids)
                    conn.execute(
                        f"DELETE FROM gm_free_agent_offer_requests WHERE free_agent_id IN ({placeholders})",
                        free_agent_ids,
                    )
                    deleted_free_agents = int(conn.execute(
                        f"DELETE FROM free_agents WHERE id IN ({placeholders})", free_agent_ids
                    ).rowcount or 0)
            else:
                moved_player_rows += int(conn.execute(
                    "UPDATE free_agents SET profile_id = ?, updated_at = ? WHERE profile_id = ?",
                    (target_id, timestamp, source_id),
                ).rowcount or 0)

            moved_dead_contracts = int(conn.execute(
                "UPDATE dead_contracts SET profile_id = ?, updated_at = ? WHERE profile_id = ?",
                (target_id, timestamp, source_id),
            ).rowcount or 0)
            conn.execute(
                "UPDATE waiver_players SET profile_id = ?, updated_at = ? WHERE profile_id = ?",
                (target_id, timestamp, source_id),
            )
            moved_salary_history, deleted_salary_history = self._merge_salary_history_rows(
                conn, source_id, target_id, timestamp
            )
            moved_transactions = int(conn.execute(
                "UPDATE player_transactions SET profile_id = ? WHERE profile_id = ?",
                (target_id, source_id),
            ).rowcount or 0)
            conn.execute("UPDATE admin_logs SET profile_id = ? WHERE profile_id = ?", (str(target_id), str(source_id)))
            conn.execute("UPDATE admin_logs SET profile_id = ? WHERE profile_id = ?", (str(target_id), source_id))

            if conn.execute(
                "SELECT id FROM discord_free_agent_offer_threads WHERE profile_id = ? LIMIT 1", (target_id,)
            ).fetchone():
                conn.execute("DELETE FROM discord_free_agent_offer_threads WHERE profile_id = ?", (source_id,))
            else:
                conn.execute(
                    "UPDATE discord_free_agent_offer_threads SET profile_id = ?, updated_at = ? WHERE profile_id = ?",
                    (target_id, timestamp, source_id),
                )
            if self._table_exists(conn, "free_agent_offer_promises"):
                conn.execute(
                    "UPDATE free_agent_offer_promises SET profile_id = ?, updated_at = ? WHERE profile_id = ?",
                    (target_id, timestamp, source_id),
                )

            details = {
                "source_profile_id": source_id,
                "target_profile_id": target_id,
                "source_name": source["name"],
                "target_name": target["name"],
                "deleted_player_rows": deleted_player_rows,
                "moved_player_rows": moved_player_rows,
                "moved_dead_contracts": moved_dead_contracts,
                "moved_salary_history": moved_salary_history,
                "deleted_salary_history": deleted_salary_history,
                "deleted_free_agents": deleted_free_agents,
            }
            conn.execute(
                """INSERT INTO player_profile_aliases (
                       old_profile_id, target_profile_id, reason, actor, details_json, created_at
                   ) VALUES (?, ?, 'merge', NULL, ?, ?)
                   ON CONFLICT(old_profile_id) DO UPDATE SET
                       target_profile_id = excluded.target_profile_id, reason = excluded.reason,
                       actor = excluded.actor, details_json = excluded.details_json,
                       created_at = excluded.created_at""",
                (source_id, target_id, json.dumps(details, ensure_ascii=True, sort_keys=True), timestamp),
            )
            self._record_transaction(
                conn, target_id, "merge_profile", f"Perfil fusionado: {source['name']} -> {target['name']}",
                details=details,
            )
            conn.execute("DELETE FROM player_profiles WHERE id = ?", (source_id,))
            conn.commit()
            return {
                "ok": True,
                "source_profile_id": source_id,
                "target_profile_id": target_id,
                "moved": {
                    "player_rows": moved_player_rows,
                    "dead_contracts": moved_dead_contracts,
                    "salary_history": moved_salary_history,
                    "transactions": moved_transactions,
                },
                "deleted": {
                    "player_rows": deleted_player_rows,
                    "salary_history": deleted_salary_history,
                    "free_agents": deleted_free_agents,
                },
            }

    def _merge_salary_history_rows(
        self,
        conn: Any,
        source_profile_id: int,
        target_profile_id: int,
        timestamp: str,
    ) -> tuple[int, int]:
        if not self._table_exists(conn, "player_salary_history"):
            return 0, 0
        source_rows = conn.execute(
            """SELECT id, profile_id, player_id, team_code, season_year, salary_text,
                      salary_num, salary_type, source, created_at, updated_at
               FROM player_salary_history WHERE profile_id = ? ORDER BY season_year, id""",
            (source_profile_id,),
        ).fetchall()
        moved = 0
        deleted = 0
        for row in source_rows:
            row_id = int(row["id"])
            season_year = parse_int(row["season_year"])
            if season_year is None:
                conn.execute(
                    "UPDATE player_salary_history SET profile_id = ?, updated_at = ? WHERE id = ?",
                    (target_profile_id, timestamp, row_id),
                )
                moved += 1
                continue
            existing = conn.execute(
                """SELECT id, player_id, team_code, salary_text, salary_num, salary_type, source
                   FROM player_salary_history WHERE profile_id = ? AND season_year = ? LIMIT 1""",
                (target_profile_id, season_year),
            ).fetchone()
            if not existing:
                conn.execute(
                    "UPDATE player_salary_history SET profile_id = ?, updated_at = ? WHERE id = ?",
                    (target_profile_id, timestamp, row_id),
                )
                moved += 1
                continue
            updates: List[str] = []
            values: List[Any] = []
            for field in ("player_id", "team_code", "salary_text", "salary_num", "salary_type", "source"):
                existing_value = existing[field]
                source_value = row[field]
                existing_blank = existing_value is None or str(existing_value).strip() == ""
                source_blank = source_value is None or str(source_value).strip() == ""
                if existing_blank and not source_blank:
                    updates.append(f"{field} = ?")
                    values.append(source_value)
            if updates:
                conn.execute(
                    f"UPDATE player_salary_history SET {', '.join(updates)}, updated_at = ? WHERE id = ?",
                    [*values, timestamp, int(existing["id"])],
                )
            conn.execute("DELETE FROM player_salary_history WHERE id = ?", (row_id,))
            deleted += 1
        return moved, deleted

    def _has_future_contract_salary(self, player: Dict[str, Any], season: int) -> bool:
        rights_markers = {"NB", "EB", "FB", "QO", "GAP"}
        for future_season in self._contract_seasons:
            if int(future_season) <= int(season):
                continue
            salary_text = str(player.get(f"salary_{future_season}_text") or "").strip()
            salary_code = salary_text.upper()
            option_code = str(player.get(f"option_{future_season}") or "").strip().upper()
            salary_num = parse_float(player.get(f"salary_{future_season}_num"))
            if salary_num is not None and abs(float(salary_num)) > 0:
                return True
            salary_text_amount = parse_amount_like(salary_text)
            if salary_text_amount is not None and abs(float(salary_text_amount)) > 0:
                return True
            if salary_text and salary_text != "-" and salary_code not in rights_markers:
                return True
            if option_code and option_code not in rights_markers:
                return True
        return False

    def _free_agent_type(self, player: Dict[str, Any], season: int) -> str:
        decision = (player.get("option_decisions") or {}).get(f"option_{int(season)}") or {}
        option_value = str(decision.get("option_value") or "").strip().upper()
        option_action = str(decision.get("action") or "").strip().lower()
        option_status = str(decision.get("status") or "").strip().lower()
        salary_text_code = str(player.get(f"salary_{int(season)}_text") or "").strip().upper()
        option_code = str(player.get(f"option_{int(season)}") or "").strip().upper()
        if salary_text_code == "QO" or option_code == "QO":
            return self._free_agent_type_restricted
        if (
            option_value in {"QO", "GAP"}
            and option_action == "accepted"
            and option_status == "approved"
            and (option_code in {"QO", "GAP"} or not self._has_future_contract_salary(player, season))
        ):
            return self._free_agent_type_restricted
        return self._free_agent_type_unrestricted

    @staticmethod
    def _empty_contract_cell(value: Any) -> bool:
        return str(value or "").strip() in {"", "-", "—", "0"}

    def _is_expiring_contract(self, player: Dict[str, Any], current_year: int, next_year: int) -> bool:
        if is_two_way_player(player) or is_exhibit10_player(player):
            return False
        if row_salary_num(player, current_year) <= 0 or row_salary_num(player, next_year) > 0:
            return False
        return self._empty_contract_cell(player.get(f"salary_{next_year}_text")) and self._empty_contract_cell(
            player.get(f"option_{next_year}")
        )

    @staticmethod
    def _bird_rights_code(player: Dict[str, Any], season: int) -> Optional[str]:
        for key in (f"salary_{season}_text", f"option_{season}"):
            code = str(player.get(key) or "").strip().upper()
            if code in {"NB", "EB", "FB"}:
                return code
        return cap_hold_bird_code_from_years(player.get("years_left")) or None

    def _cleanup_active_contract_free_agents(self, conn: Any, current_year: int) -> int:
        active_profile_ids: List[int] = []
        for team in conn.execute("SELECT id FROM teams ORDER BY id").fetchall():
            team_id = parse_int(team["id"])
            if team_id is None:
                continue
            players = self._select_team_players(conn, team_id)
            self._attach_option_decisions(conn, players, team_id)
            for player in players:
                profile_id = parse_int(player.get("profile_id"))
                if profile_id is None:
                    continue
                for season in self._contract_seasons:
                    if int(season) < current_year:
                        continue
                    option_code = str(player.get(f"option_{season}") or "").strip().upper()
                    decision = (player.get("option_decisions") or {}).get(f"option_{season}") or {}
                    decision_option = str(decision.get("option_value") or "").strip().upper()
                    if (
                        decision_option in {"QO", "GAP"}
                        and str(decision.get("action") or "").strip().lower() == "accepted"
                        and str(decision.get("status") or "").strip().lower() == "approved"
                        and (option_code in {"QO", "GAP"} or not self._has_future_contract_salary(player, season))
                    ):
                        continue
                    salary_num = parse_float(player.get(f"salary_{season}_num"))
                    salary_text_amount = parse_amount_like(player.get(f"salary_{season}_text"))
                    if (salary_num is not None and abs(float(salary_num)) > 0) or (
                        salary_text_amount is not None and abs(float(salary_text_amount)) > 0
                    ):
                        active_profile_ids.append(profile_id)
                        break
        if not active_profile_ids:
            return 0
        unique_ids = sorted(set(active_profile_ids))
        placeholders = ",".join("?" for _ in unique_ids)
        rows = conn.execute(
            f"SELECT id FROM free_agents WHERE profile_id IN ({placeholders}) AND COALESCE(source, '') != ?",
            (*unique_ids, self._free_agent_source_cap_hold),
        ).fetchall()
        self._cleanup_minimum_targets(conn, [row["id"] for row in rows])
        cur = conn.execute(
            f"DELETE FROM free_agents WHERE profile_id IN ({placeholders}) AND COALESCE(source, '') != ?",
            (*unique_ids, self._free_agent_source_cap_hold),
        )
        return int(cur.rowcount or 0)

    def sync_cap_hold_free_agents(self, conn: Any, settings: Dict[str, str]) -> int:
        timestamp = self._now()
        if not parse_bool(settings.get("free_agency_mode")):
            rows = conn.execute(
                "SELECT id FROM free_agents WHERE source = ?", (self._free_agent_source_cap_hold,)
            ).fetchall()
            self._cleanup_minimum_targets(conn, [row["id"] for row in rows])
            cur = conn.execute("DELETE FROM free_agents WHERE source = ?", (self._free_agent_source_cap_hold,))
            return int(cur.rowcount or 0)

        current_year = parse_int(settings.get("current_year")) or 2025
        season = int(current_year)
        salary_cap = parse_float(settings.get(f"salary_cap_{season}")) or parse_float(
            settings.get("salary_cap_2025")
        ) or 0.0
        valid_profile_ids: List[int] = []
        changed = 0
        for team in conn.execute("SELECT id, code FROM teams ORDER BY code").fetchall():
            team_id = int(team["id"])
            team_code = str(team["code"] or "").strip().upper()
            players = self._select_team_players(conn, team_id)
            self._attach_option_decisions(conn, players, team_id)
            for player in players:
                profile_id = parse_int(player.get("profile_id"))
                if profile_id is not None:
                    status_row = conn.execute(
                        "SELECT profile_status FROM player_profiles WHERE id = ?", (profile_id,)
                    ).fetchone()
                    if status_row and self._unavailable_profile_status(status_row["profile_status"]):
                        continue
                free_agent_type = self._free_agent_type(player, season)
                restricted = free_agent_type == self._free_agent_type_restricted
                hold_amount = cap_hold_amount(player, season, settings, salary_cap)
                hold_marker = has_standard_cap_hold_marker(player, season)
                expiring = self._is_expiring_contract(player, current_year - 1, season)
                if not restricted and hold_amount <= 0 and not hold_marker and not expiring:
                    continue
                retained_rights = restricted or hold_amount > 0 or hold_marker
                player_id = parse_int(player.get("id"))
                if player_id is None:
                    continue
                if profile_id is None:
                    profile_id = self._ensure_profile(conn, player_id, timestamp)
                if profile_id is None:
                    continue
                name = str(player.get("name") or player.get("profile_name") or "Agente libre").strip() or "Agente libre"
                default_notes = (
                    f"Cap hold retenido por {team_code} para {season_label(season)}"
                    if retained_rights
                    else f"Contrato expirado tras {season_label(current_year - 1)}"
                )
                bird_rights = self._bird_rights_code(player, season) if retained_rights else None
                rights_team_code = team_code if retained_rights else None
                existing = conn.execute(
                    "SELECT id, notes, source FROM free_agents WHERE profile_id = ? LIMIT 1", (profile_id,)
                ).fetchone()
                if existing and str(existing["source"] or "").strip() == self._free_agent_source_renounced_rights:
                    continue
                valid_profile_ids.append(profile_id)
                values = (
                    name,
                    str(player.get("position") or "").strip() or None,
                    bird_rights,
                    str(player.get("rating") or "").strip() or None,
                    normalize_bird_years(player.get("years_left")),
                    free_agent_type,
                    self._free_agent_source_cap_hold,
                    rights_team_code,
                    default_notes,
                    timestamp,
                )
                if existing:
                    cur = conn.execute(
                        """UPDATE free_agents SET name = ?, position = ?, bird_rights = ?, rating = ?,
                               years_left = ?, free_agent_type = ?, source = ?, rights_team_code = ?,
                               notes = CASE WHEN notes IS NULL OR TRIM(notes) = ''
                                   OR notes LIKE 'Cap hold retenido por %' OR notes LIKE 'Contrato expirado tras %'
                                   THEN ? ELSE notes END, updated_at = ? WHERE id = ?""",
                        (*values, int(existing["id"])),
                    )
                else:
                    cur = conn.execute(
                        """INSERT INTO free_agents (profile_id, name, position, bird_rights, rating, years_left,
                               free_agent_type, source, rights_team_code, notes, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (profile_id, *values[:-1], timestamp, timestamp),
                    )
                changed += int(cur.rowcount or 0)

        if valid_profile_ids:
            placeholders = ",".join("?" for _ in valid_profile_ids)
            condition = f"source = ? AND (profile_id IS NULL OR profile_id NOT IN ({placeholders}))"
            params: tuple[Any, ...] = (self._free_agent_source_cap_hold, *valid_profile_ids)
        else:
            condition = "source = ?"
            params = (self._free_agent_source_cap_hold,)
        rows = conn.execute(f"SELECT id FROM free_agents WHERE {condition}", params).fetchall()
        self._cleanup_minimum_targets(conn, [row["id"] for row in rows])
        cur = conn.execute(f"DELETE FROM free_agents WHERE {condition}", params)
        changed += int(cur.rowcount or 0)
        changed += self._cleanup_active_contract_free_agents(conn, current_year)
        return changed

    def sync_uncontracted_profile_free_agents(self, conn: Any) -> int:
        timestamp = self._now()
        rows = conn.execute(
            """SELECT id FROM free_agents WHERE source = ? AND profile_id IN
                   (SELECT DISTINCT profile_id FROM players WHERE profile_id IS NOT NULL)""",
            (self._free_agent_source_uncontracted,),
        ).fetchall()
        self._cleanup_minimum_targets(conn, [row["id"] for row in rows])
        changed = int(conn.execute(
            """DELETE FROM free_agents WHERE source = ? AND profile_id IN
                   (SELECT DISTINCT profile_id FROM players WHERE profile_id IS NOT NULL)""",
            (self._free_agent_source_uncontracted,),
        ).rowcount or 0)
        cur = conn.execute(
            """INSERT INTO free_agents (
                   profile_id, name, position, bird_rights, rating, years_left, free_agent_type,
                   source, rights_team_code, agent, notes, created_at, updated_at)
               SELECT pp.id, pp.name, NULL, NULL, NULL, NULL, ?, ?, NULL, NULL,
                   'Agente libre sin derechos Bird retenidos.', ?, ?
               FROM player_profiles pp
               LEFT JOIN players p ON p.profile_id = pp.id
               LEFT JOIN free_agents f ON f.profile_id = pp.id
               WHERE p.id IS NULL AND f.id IS NULL
                   AND COALESCE(pp.profile_status, 'active') NOT IN (?, ?)
                   AND TRIM(COALESCE(pp.name, '')) != ''""",
            (
                self._free_agent_type_unrestricted,
                self._free_agent_source_uncontracted,
                timestamp,
                timestamp,
                *self._unavailable_profile_statuses,
            ),
        )
        return changed + int(cur.rowcount or 0)

    @contextmanager
    def synchronized_transaction(self) -> Iterator[Any]:
        with self.db._free_agents_sync_lock:
            with self.db.transaction("IMMEDIATE") as conn:
                yield conn
