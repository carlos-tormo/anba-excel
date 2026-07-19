"""Persistence boundary for player identity and profile synchronization."""

from __future__ import annotations

from contextlib import contextmanager
import json
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional

try:
    from ...domain_rules import parse_int
except ImportError:  # pragma: no cover
    from domain_rules import parse_int

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
    ) -> None:
        super().__init__(db)
        self._now = now
        self._contract_seasons = tuple(contract_seasons or ())
        self._retained_rights_only = retained_rights_only
        self._current_year = current_year
        self._record_transaction = record_transaction
        self._table_exists = table_exists

    @property
    def configured(self) -> bool:
        return all((self._now, self._contract_seasons, self._retained_rights_only,
                    self._current_year, self._record_transaction, self._table_exists))

    def update_profile(self, profile_id: int, payload: Any) -> Any:
        return self.db.update_player_profile(profile_id, payload)

    def delete_profile(self, profile_id: int) -> Any:
        return self.db.delete_player_profile(profile_id)

    def merge_profiles(self, source_profile_id: int, target_profile_id: int) -> Any:
        if not self.configured:
            return self.db.merge_player_profiles(source_profile_id, target_profile_id)
        return self._merge_profiles(source_profile_id, target_profile_id)

    def integrity_report(self) -> Any:
        if not self.configured:
            return self.db.player_identity_integrity_report()
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

    def sync_cap_hold_free_agents(self, *args: Any, **kwargs: Any) -> Any:
        return self.db._sync_cap_hold_free_agents(*args, **kwargs)

    def sync_uncontracted_profile_free_agents(self, *args: Any, **kwargs: Any) -> Any:
        return self.db._sync_uncontracted_profile_free_agents(*args, **kwargs)

    @contextmanager
    def synchronized_transaction(self) -> Iterator[Any]:
        with self.db._free_agents_sync_lock:
            with self.db.transaction("IMMEDIATE") as conn:
                yield conn
