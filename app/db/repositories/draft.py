"""Repository-owned draft read models, commands, requests, and result processing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import sqlite3
from typing import Any, Callable, Dict, List, Optional

try:
    from ...domain._values import parse_bool, parse_int
    from ...workflow_states import WorkflowTransitionError
except ImportError:  # pragma: no cover - supports direct app imports.
    from domain._values import parse_bool, parse_int
    from workflow_states import WorkflowTransitionError

from .base import LeagueRepository


@dataclass(frozen=True)
class DraftReadOperations:
    normalize_pick_round: Callable[[Any], str]
    normalize_pick_type: Callable[[Any], str]
    normalize_team_code: Callable[[Any], Optional[str]]
    normalize_team_codes: Callable[[Any], List[str]]
    now: Callable[[], str]
    contract_min_year: int
    contract_max_start_year: int
    max_pending_requests: int
    resolve_profile_for_new_row: Optional[Callable[..., Any]] = None
    record_player_transaction_conn: Optional[Callable[..., Any]] = None
    parse_salary_amount: Optional[Callable[[Any], Optional[float]]] = None
    parse_amount_like: Optional[Callable[[Any], Optional[float]]] = None
    contract_seasons: tuple[int, ...] = ()
    contract_max_year: int = 0


class DraftRepository(LeagueRepository):
    def __init__(self, db: Any, read_operations: Optional[DraftReadOperations] = None, *, workflows: Any = None) -> None:
        super().__init__(db)
        self.read_operations = read_operations
        self.workflows = workflows or getattr(db, "_workflow_repository", None)

    def _read_operations(self) -> DraftReadOperations:
        if not self.read_operations:
            raise RuntimeError("draft_read_repository_not_configured")
        return self.read_operations

    def current_year(self) -> int:
        operations = self._read_operations()
        with self.db.connect() as conn:
            row = conn.execute("SELECT value FROM app_settings WHERE key = 'current_year'").fetchone()
        current_year = parse_int(row["value"] if row else None) or 2025
        if current_year < operations.contract_min_year or current_year > operations.contract_max_start_year:
            current_year = 2025
        return current_year + 1

    def list_order(self, draft_year: Any = None) -> Dict[str, Any]:
        year = draft_year if draft_year is not None else self.current_year()
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT d.id, d.draft_year, d.draft_round, d.pick_number,
                       d.owner_team_code,
                       COALESCE(owner.name, d.owner_team_code) AS owner_team_name,
                       d.original_team_code,
                       COALESCE(original.name, d.original_team_code) AS original_team_name,
                       d.created_at, d.updated_at
                FROM draft_order d
                LEFT JOIN teams owner ON owner.code = d.owner_team_code
                LEFT JOIN teams original ON original.code = d.original_team_code
                WHERE d.draft_year = ?
                ORDER BY CASE d.draft_round WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END,
                         d.pick_number, d.id
                """,
                (int(year),),
            ).fetchall()
        return {"draft_year": int(year), "draft_order": [dict(row) for row in rows]}

    def list_pick_ledger(self, draft_year: Any = None) -> Dict[str, Any]:
        operations = self._read_operations()
        year = draft_year if draft_year is not None else self.current_year()
        with self.db.connect() as conn:
            teams = [dict(row) for row in conn.execute("SELECT id, code, name FROM teams ORDER BY code").fetchall()]
            team_names = {
                str(team.get("code") or "").strip().upper(): str(team.get("name") or team.get("code") or "").strip()
                for team in teams
            }
            assets = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT a.id, a.team_id, holder.code AS holder_team_code,
                           COALESCE(holder.name, holder.code) AS holder_team_name,
                           a.asset_type, a.label, a.year, a.detail, a.draft_pick_type,
                           a.draft_round, a.original_owner, a.draft_pick_sold_to,
                           a.draft_pick_conditional_teams, a.draft_pick_restricted,
                           a.draft_pick_stepien_restricted, a.draft_pick_protected,
                           a.draft_pick_frozen, a.created_at, a.updated_at
                    FROM assets a
                    JOIN teams holder ON holder.id = a.team_id
                    WHERE a.asset_type = 'draft_pick'
                      AND CAST(COALESCE(a.year, '') AS INTEGER) = ?
                    ORDER BY holder.code,
                        CASE COALESCE(a.draft_round, '1st') WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END,
                        CASE COALESCE(a.draft_pick_type, 'own')
                            WHEN 'own' THEN 1 WHEN 'acquired' THEN 2 WHEN 'conditional' THEN 3
                            WHEN 'sold' THEN 4 ELSE 5 END,
                        a.id
                    """,
                    (int(year),),
                ).fetchall()
            ]

        def canonical_key(owner_code: str, draft_round: str) -> str:
            return f"{int(year)}-{'1ST' if draft_round == '1st' else '2ND'}-{owner_code}"

        def original_owner_codes(asset: Dict[str, Any]) -> List[str]:
            pick_type = operations.normalize_pick_type(asset.get("draft_pick_type"))
            holder = operations.normalize_team_code(asset.get("holder_team_code"))
            original = operations.normalize_team_code(asset.get("original_owner"))
            if pick_type == "conditional":
                codes = operations.normalize_team_codes(asset.get("draft_pick_conditional_teams"))
                return codes or ([original] if original else ([holder] if holder else []))
            if pick_type in {"acquired", "sold"}:
                return [original or holder] if (original or holder) else []
            return [holder] if holder else []

        active_by_key: Dict[str, List[Dict[str, Any]]] = {}
        sold_by_key: Dict[str, List[Dict[str, Any]]] = {}
        unexpected_assets: List[Dict[str, Any]] = []
        valid_team_codes = set(team_names)
        for asset in assets:
            draft_round = operations.normalize_pick_round(asset.get("draft_round"))
            pick_type = operations.normalize_pick_type(asset.get("draft_pick_type"))
            owner_codes = [code for code in original_owner_codes(asset) if code]
            if not owner_codes:
                unexpected_assets.append(asset)
                continue
            for owner_code in owner_codes:
                target = sold_by_key if pick_type == "sold" else active_by_key
                target.setdefault(canonical_key(owner_code, draft_round), []).append(asset)
                if owner_code not in valid_team_codes:
                    unexpected_assets.append(asset)

        def asset_summary(asset: Dict[str, Any]) -> Dict[str, Any]:
            holder_code = operations.normalize_team_code(asset.get("holder_team_code"))
            return {
                "asset_id": parse_int(asset.get("id")),
                "holder_team_code": holder_code,
                "holder_team_name": asset.get("holder_team_name") or team_names.get(holder_code or "", holder_code or ""),
                "pick_type": operations.normalize_pick_type(asset.get("draft_pick_type")),
                "label": asset.get("label"),
                "detail": asset.get("detail"),
                "sold_to_team_codes": operations.normalize_team_codes(asset.get("draft_pick_sold_to")),
                "conditional_team_codes": operations.normalize_team_codes(asset.get("draft_pick_conditional_teams")),
                "restricted": bool(parse_bool(asset.get("draft_pick_restricted"))),
                "stepien_restricted": bool(parse_bool(asset.get("draft_pick_stepien_restricted"))),
                "protected": bool(parse_bool(asset.get("draft_pick_protected"))),
                "frozen": bool(parse_bool(asset.get("draft_pick_frozen"))),
            }

        def pick_state(owner_code: str, draft_round: str) -> Dict[str, Any]:
            key = canonical_key(owner_code, draft_round)
            active_summaries = [asset_summary(asset) for asset in active_by_key.get(key, [])]
            sold_summaries = [asset_summary(asset) for asset in sold_by_key.get(key, [])]
            holder_codes: List[str] = []
            holder_names: List[str] = []
            pick_types: List[str] = []
            frozen = False
            for item in active_summaries:
                holder_code = item.get("holder_team_code")
                if holder_code and holder_code not in holder_codes:
                    holder_codes.append(holder_code)
                    holder_names.append(item.get("holder_team_name") or team_names.get(holder_code, holder_code))
                pick_type = item.get("pick_type")
                if pick_type and pick_type not in pick_types:
                    pick_types.append(pick_type)
                frozen = frozen or bool(item.get("frozen"))
            status = (
                "missing" if not active_summaries else
                "duplicate" if len(active_summaries) > 1 else
                "conditional" if "conditional" in pick_types else
                "frozen" if frozen else "ok"
            )
            sold_to_codes: List[str] = []
            for item in sold_summaries:
                for code in item.get("sold_to_team_codes") or []:
                    if code not in sold_to_codes:
                        sold_to_codes.append(code)
            return {
                "canonical_id": key,
                "round": draft_round,
                "original_team_code": owner_code,
                "original_team_name": team_names.get(owner_code, owner_code),
                "status": status,
                "holder_team_codes": holder_codes,
                "holder_team_names": holder_names,
                "asset_ids": [item["asset_id"] for item in active_summaries if item.get("asset_id") is not None],
                "pick_types": pick_types,
                "sold_to_team_codes": sold_to_codes,
                "sold_asset_ids": [item["asset_id"] for item in sold_summaries if item.get("asset_id") is not None],
                "active_assets": active_summaries,
                "sold_assets": sold_summaries,
            }

        rows: List[Dict[str, Any]] = []
        issues: List[Dict[str, Any]] = []
        summary = {"expected": len(teams) * 2, "ok": 0, "missing": 0, "duplicate": 0,
                   "conditional": 0, "frozen": 0, "warning": 0, "error": 0}
        for team in teams:
            owner_code = str(team.get("code") or "").strip().upper()
            first, second = pick_state(owner_code, "1st"), pick_state(owner_code, "2nd")
            rows.append({"team_code": owner_code, "team_name": team.get("name") or owner_code,
                         "first": first, "second": second})
            for state in (first, second):
                status = str(state.get("status") or "missing")
                if status in summary:
                    summary[status] += 1
                if status == "missing":
                    summary["error"] += 1
                    issues.append({"severity": "error", "rule": "missing_pick",
                                   "canonical_id": state["canonical_id"],
                                   "message": f"{state['canonical_id']} no aparece en ningún equipo."})
                elif status == "duplicate":
                    summary["error"] += 1
                    issues.append({"severity": "error", "rule": "duplicate_pick",
                                   "canonical_id": state["canonical_id"], "asset_ids": state["asset_ids"],
                                   "holder_team_codes": state["holder_team_codes"],
                                   "message": f"{state['canonical_id']} aparece en más de un asset activo."})
                elif status in {"conditional", "frozen"}:
                    summary["warning"] += 1
                    issues.append({"severity": "warning", "rule": f"{status}_pick",
                                   "canonical_id": state["canonical_id"], "asset_ids": state["asset_ids"],
                                   "holder_team_codes": state["holder_team_codes"],
                                   "message": f"{state['canonical_id']} requiere revisión: {status}."})
        for asset in unexpected_assets:
            asset_id = parse_int(asset.get("id"))
            issue_key = f"unexpected:{asset_id}"
            if any(str(issue.get("canonical_id")) == issue_key for issue in issues):
                continue
            summary["warning"] += 1
            issues.append({"severity": "warning", "rule": "unexpected_pick_owner",
                           "canonical_id": issue_key, "asset_id": asset_id,
                           "holder_team_code": operations.normalize_team_code(asset.get("holder_team_code")),
                           "message": f"Asset #{asset_id} tiene propietario original no reconocido o vacío."})
        return {"draft_year": int(year), "summary": summary, "rows": rows, "issues": issues}

    def order_entry(self, draft_order_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT d.id, d.draft_year, d.draft_round, d.pick_number,
                       d.owner_team_code,
                       COALESCE(owner.name, d.owner_team_code) AS owner_team_name,
                       d.original_team_code,
                       COALESCE(original.name, d.original_team_code) AS original_team_name,
                       d.created_at, d.updated_at
                FROM draft_order d
                LEFT JOIN teams owner ON owner.code = d.owner_team_code
                LEFT JOIN teams original ON original.code = d.original_team_code
                WHERE d.id = ?
                """,
                (int(draft_order_id),),
            ).fetchone()
        return dict(row) if row else None

    def _live_order_rows(self, conn: Any, draft_year: int) -> List[Dict[str, Any]]:
        return [dict(row) for row in conn.execute(
            """
            SELECT d.id, d.draft_year, d.draft_round, d.pick_number,
                   d.owner_team_code, COALESCE(owner.name, d.owner_team_code) AS owner_team_name,
                   d.original_team_code, COALESCE(original.name, d.original_team_code) AS original_team_name,
                   d.created_at, d.updated_at, s.selection_text, s.option_value, s.custom_text,
                   COALESCE(s.skipped, 0) AS skipped, s.selected_by_email, s.selected_by_name,
                   s.selected_by_role, s.selected_at, s.updated_at AS selection_updated_at,
                   s.version AS selection_version,
                   s.processed_type, s.processed_dead_contract_id, s.processed_asset_id, s.processed_at,
                   pr.id AS pending_request_id, pr.selection_text AS pending_selection_text,
                   pr.option_value AS pending_option_value, pr.custom_text AS pending_custom_text,
                   pr.requester_email AS pending_requester_email, pr.requester_name AS pending_requester_name,
                   pr.created_at AS pending_request_created_at
            FROM draft_order d
            LEFT JOIN teams owner ON owner.code = d.owner_team_code
            LEFT JOIN teams original ON original.code = d.original_team_code
            LEFT JOIN draft_live_selections s ON s.draft_order_id = d.id
            LEFT JOIN gm_draft_pick_requests pr ON pr.draft_order_id = d.id AND pr.status = 'pending'
            WHERE d.draft_year = ?
            ORDER BY CASE d.draft_round WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END,
                     d.pick_number, d.id
            """,
            (int(draft_year),),
        ).fetchall()]

    @staticmethod
    def _live_options(options_text: Any) -> List[str]:
        seen, options = set(), []
        for line in str(options_text or "").splitlines():
            option = line.strip()
            key = option.casefold()
            if option and key not in seen:
                seen.add(key)
                options.append(option)
        return sorted(options, key=lambda value: (value.casefold(), value))

    @staticmethod
    def _first_open_pick_id(rows: List[Dict[str, Any]]) -> Optional[int]:
        for row in rows:
            if not str(row.get("selection_text") or "").strip() and not parse_bool(row.get("skipped")):
                parsed = parse_int(row.get("id"))
                if parsed is not None:
                    return int(parsed)
        return parse_int(rows[0].get("id")) if rows else None

    @staticmethod
    def _pending_request_count(rows: List[Dict[str, Any]]) -> int:
        return sum(1 for row in rows if parse_int(row.get("pending_request_id")) is not None)

    def _requestable_pick_ids(self, rows: List[Dict[str, Any]], current_pick_id: Optional[int]) -> List[int]:
        if self._pending_request_count(rows) >= self._read_operations().max_pending_requests:
            return []
        start_index = 0
        if current_pick_id is not None:
            for index, row in enumerate(rows):
                if parse_int(row.get("id")) == int(current_pick_id):
                    start_index = index
                    break
        for row in rows[start_index:]:
            if str(row.get("selection_text") or "").strip() or parse_bool(row.get("skipped")):
                continue
            if parse_int(row.get("pending_request_id")) is not None:
                continue
            parsed = parse_int(row.get("id"))
            return [int(parsed)] if parsed is not None else []
        return []

    @staticmethod
    def _remaining_seconds(started_at: Any, duration_seconds: int) -> int:
        raw = str(started_at or "").strip()
        if not raw:
            return int(duration_seconds)
        try:
            started = datetime.fromisoformat(raw)
        except ValueError:
            return int(duration_seconds)
        return max(0, int(duration_seconds) - int((datetime.now(UTC) - started).total_seconds()))

    def _live_payload(self, conn: Any, draft_year: int) -> Dict[str, Any]:
        operations = self._read_operations()
        rows = self._live_order_rows(conn, draft_year)
        state = conn.execute("SELECT * FROM draft_live_state WHERE draft_year = ?", (int(draft_year),)).fetchone()
        state_row = dict(state) if state else {}
        duration_seconds = max(10, min(3600, parse_int(state_row.get("duration_seconds")) or 180))
        enabled = parse_bool(state_row.get("enabled"))
        current_pick_id = parse_int(state_row.get("current_draft_order_id"))
        if current_pick_id not in {parse_int(row.get("id")) for row in rows}:
            current_pick_id = self._first_open_pick_id(rows)
        started_at = str(state_row.get("started_at") or "").strip() or None
        options_text = str(state_row.get("options_text") or "")
        pending_request_count = self._pending_request_count(rows)
        return {
            "draft_year": int(draft_year), "enabled": bool(enabled), "current_pick_id": current_pick_id,
            "state_version": parse_int(state_row.get("version")) or 1,
            "requestable_pick_ids": self._requestable_pick_ids(rows, current_pick_id) if enabled else [],
            "pending_request_count": pending_request_count,
            "max_pending_requests": operations.max_pending_requests,
            "duration_seconds": duration_seconds, "started_at": started_at,
            "remaining_seconds": self._remaining_seconds(started_at, duration_seconds) if enabled else duration_seconds,
            "server_now": operations.now(), "options": self._live_options(options_text),
            "options_text": options_text, "draft_order": rows,
        }

    def list_live(self, draft_year: Any = None) -> Dict[str, Any]:
        year = draft_year if draft_year is not None else self.current_year()
        if year < 2000 or year > 2100:
            raise ValueError("invalid_draft_year")
        with self.db.connect() as conn:
            return self._live_payload(conn, int(year))

    def _normalize_order_payload(
        self,
        conn: Any,
        payload: Dict[str, Any],
        *,
        existing: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        operations = self._read_operations()
        source = dict(existing or {})
        source.update(payload)
        draft_year = parse_int(source.get("draft_year"))
        if draft_year is None:
            draft_year = self.current_year()
        if draft_year < 2000 or draft_year > 2100:
            raise ValueError("invalid_draft_year")
        pick_number = parse_int(source.get("pick_number"))
        if pick_number is None or pick_number <= 0 or pick_number > 300:
            raise ValueError("invalid_pick_number")
        draft_round = operations.normalize_pick_round(source.get("draft_round"))
        owner_team_code = operations.normalize_team_code(source.get("owner_team_code"))
        original_team_code = operations.normalize_team_code(source.get("original_team_code"))
        if not owner_team_code or not original_team_code:
            raise ValueError("team_codes_required")
        existing_codes = {
            str(row["code"]).upper()
            for row in conn.execute(
                "SELECT code FROM teams WHERE code IN (?, ?)",
                (owner_team_code, original_team_code),
            ).fetchall()
        }
        if owner_team_code not in existing_codes or original_team_code not in existing_codes:
            raise ValueError("team_not_found")
        return {
            "draft_year": draft_year,
            "draft_round": draft_round,
            "pick_number": pick_number,
            "owner_team_code": owner_team_code,
            "original_team_code": original_team_code,
        }

    def create_order_entry(self, payload: Any) -> Any:
        with self.db.connect() as conn:
            values = self._normalize_order_payload(conn, payload)
            timestamp = self._read_operations().now()
            try:
                cur = conn.execute(
                    """INSERT INTO draft_order (
                           draft_year, draft_round, pick_number, owner_team_code,
                           original_team_code, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        values["draft_year"], values["draft_round"], values["pick_number"],
                        values["owner_team_code"], values["original_team_code"], timestamp, timestamp,
                    ),
                )
            except sqlite3.IntegrityError as err:
                raise ValueError("duplicate_draft_pick") from err
            conn.commit()
            return int(cur.lastrowid)

    def update_order_entry(self, draft_order_id: int, payload: Any) -> Any:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM draft_order WHERE id = ?", (int(draft_order_id),)).fetchone()
            if not row:
                return False
            values = self._normalize_order_payload(conn, payload, existing=dict(row))
            try:
                cur = conn.execute(
                    """UPDATE draft_order
                       SET draft_year = ?, draft_round = ?, pick_number = ?,
                           owner_team_code = ?, original_team_code = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        values["draft_year"], values["draft_round"], values["pick_number"],
                        values["owner_team_code"], values["original_team_code"],
                        self._read_operations().now(), int(draft_order_id),
                    ),
                )
            except sqlite3.IntegrityError as err:
                raise ValueError("duplicate_draft_pick") from err
            conn.commit()
            return cur.rowcount > 0

    def delete_order_entry(self, draft_order_id: int) -> Any:
        with self.db.connect() as conn:
            cur = conn.execute("DELETE FROM draft_order WHERE id = ?", (int(draft_order_id),))
            conn.commit()
            return cur.rowcount > 0

    def _adjacent_pick_id(
        self,
        rows: List[Dict[str, Any]],
        current_pick_id: Optional[int],
        direction: str,
        *,
        prefer_open: bool = False,
    ) -> Optional[int]:
        ids = [int(row["id"]) for row in rows if parse_int(row.get("id")) is not None]
        if not ids:
            return None
        if current_pick_id not in ids:
            return self._first_open_pick_id(rows) or ids[0]
        index = ids.index(int(current_pick_id))
        step = -1 if direction == "previous" else 1
        if prefer_open and step > 0:
            for row in rows[index + 1:]:
                if str(row.get("selection_text") or "").strip() or parse_bool(row.get("skipped")):
                    continue
                parsed = parse_int(row.get("id"))
                if parsed is not None:
                    return int(parsed)
        return ids[max(0, min(len(ids) - 1, index + step))]

    def update_live_settings(self, payload: Any) -> Any:
        draft_year = parse_int(payload.get("draft_year")) or self.current_year()
        if draft_year < 2000 or draft_year > 2100:
            raise ValueError("invalid_draft_year")
        enabled = parse_bool(payload.get("enabled"))
        duration_seconds = max(10, min(3600, parse_int(payload.get("duration_seconds")) or 180))
        current_pick_id = parse_int(payload.get("current_pick_id"))
        reset_timer = parse_bool(payload.get("reset_timer"))
        expected_state_version = parse_int(payload.get("expected_state_version"))
        options_text = (
            "\n".join(str(item).strip() for item in payload.get("options") or [] if str(item).strip())
            if isinstance(payload.get("options"), list)
            else str(payload.get("options_text") or "")
        )
        timestamp = self._read_operations().now()
        with self.db.connect() as conn:
            rows = self._live_order_rows(conn, int(draft_year))
            ids = {parse_int(row.get("id")) for row in rows}
            if current_pick_id is None:
                current_pick_id = self._first_open_pick_id(rows)
            elif current_pick_id not in ids:
                raise ValueError("invalid_current_pick")
            state = conn.execute("SELECT * FROM draft_live_state WHERE draft_year = ?", (int(draft_year),)).fetchone()
            existing = dict(state) if state else {}
            existing_state_version = parse_int(existing.get("version"))
            if expected_state_version is not None and existing_state_version != expected_state_version:
                raise ValueError("stale_entity_version")
            previous_pick_id = parse_int(existing.get("current_draft_order_id"))
            started_at = str(existing.get("started_at") or "").strip() or None
            if enabled and (reset_timer or not started_at or previous_pick_id != current_pick_id or not parse_bool(existing.get("enabled"))):
                started_at = timestamp
            if not enabled:
                started_at = None
            conn.execute(
                """INSERT INTO draft_live_state (
                       draft_year, enabled, current_draft_order_id, duration_seconds,
                       started_at, options_text, version, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                   ON CONFLICT(draft_year) DO UPDATE SET
                       enabled = excluded.enabled,
                       current_draft_order_id = excluded.current_draft_order_id,
                       duration_seconds = excluded.duration_seconds,
                       started_at = excluded.started_at,
                       options_text = excluded.options_text,
                       version = COALESCE(draft_live_state.version, 0) + 1,
                       updated_at = excluded.updated_at""",
                (int(draft_year), 1 if enabled else 0, current_pick_id, duration_seconds,
                 started_at, options_text, timestamp, timestamp),
            )
            conn.commit()
            return self._live_payload(conn, int(draft_year))

    def control_live(self, payload: Any) -> Any:
        draft_year = parse_int(payload.get("draft_year")) or self.current_year()
        if draft_year < 2000 or draft_year > 2100:
            raise ValueError("invalid_draft_year")
        action = str(payload.get("action") or "").strip().lower()
        if action not in {"previous", "next", "restart", "skip"}:
            raise ValueError("invalid_draft_control")
        timestamp = self._read_operations().now()
        expected_state_version = parse_int(payload.get("expected_state_version"))
        with self.db.connect() as conn:
            rows = self._live_order_rows(conn, int(draft_year))
            if not rows:
                raise ValueError("draft_order_empty")
            state = conn.execute("SELECT * FROM draft_live_state WHERE draft_year = ?", (int(draft_year),)).fetchone()
            state_row = dict(state) if state else {}
            existing_state_version = parse_int(state_row.get("version"))
            if expected_state_version is not None and existing_state_version != expected_state_version:
                raise ValueError("stale_entity_version")
            current_pick_id = parse_int(state_row.get("current_draft_order_id")) or self._first_open_pick_id(rows)
            if action == "restart":
                next_pick_id = current_pick_id
            else:
                if action == "skip" and current_pick_id is not None:
                    conn.execute(
                        """INSERT INTO draft_live_selections (
                               draft_order_id, selection_text, option_value, custom_text,
                               skipped, selected_by_email, selected_by_name, selected_by_role,
                               selected_at, version, updated_at
                           ) VALUES (?, 'Saltado', 'Saltado', NULL, 1, NULL, NULL, 'admin', ?, 1, ?)
                           ON CONFLICT(draft_order_id) DO UPDATE SET
                               selection_text = excluded.selection_text,
                               option_value = excluded.option_value,
                               custom_text = excluded.custom_text,
                               skipped = excluded.skipped,
                               selected_by_email = excluded.selected_by_email,
                               selected_by_name = excluded.selected_by_name,
                               selected_by_role = excluded.selected_by_role,
                               selected_at = excluded.selected_at,
                               version = COALESCE(draft_live_selections.version, 0) + 1,
                               updated_at = excluded.updated_at""",
                        (int(current_pick_id), timestamp, timestamp),
                    )
                    rows = self._live_order_rows(conn, int(draft_year))
                next_pick_id = self._adjacent_pick_id(
                    rows, current_pick_id, "previous" if action == "previous" else "next",
                    prefer_open=action in {"next", "skip"},
                )
            duration_seconds = max(10, min(3600, parse_int(state_row.get("duration_seconds")) or 180))
            options_text = str(state_row.get("options_text") or "")
            conn.execute(
                """INSERT INTO draft_live_state (
                       draft_year, enabled, current_draft_order_id, duration_seconds,
                       started_at, options_text, version, created_at, updated_at
                   ) VALUES (?, 1, ?, ?, ?, ?, 1, ?, ?)
                   ON CONFLICT(draft_year) DO UPDATE SET
                       enabled = 1,
                       current_draft_order_id = excluded.current_draft_order_id,
                       started_at = excluded.started_at,
                       version = COALESCE(draft_live_state.version, 0) + 1,
                       updated_at = excluded.updated_at""",
                (int(draft_year), next_pick_id, duration_seconds, timestamp, options_text, timestamp, timestamp),
            )
            conn.commit()
            return self._live_payload(conn, int(draft_year))

    def submit_live_pick(
        self,
        draft_order_id: int,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
        *,
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        timestamp = self._read_operations().now()
        expected_state_version = parse_int(payload.get("expected_state_version"))
        expected_selection_version = parse_int(payload.get("expected_selection_version"))
        with self.db.connect() as conn:
            pick = conn.execute("SELECT * FROM draft_order WHERE id = ?", (int(draft_order_id),)).fetchone()
            if not pick:
                raise ValueError("draft_pick_not_found")
            draft_year = int(pick["draft_year"])
            state = conn.execute("SELECT * FROM draft_live_state WHERE draft_year = ?", (draft_year,)).fetchone()
            state_row = dict(state) if state else {}
            existing_state_version = parse_int(state_row.get("version"))
            if expected_state_version is not None and existing_state_version != expected_state_version:
                raise ValueError("stale_entity_version")
            if not is_admin and not parse_bool(state_row.get("enabled")):
                raise ValueError("draft_mode_inactive")
            current_pick_id = parse_int(state_row.get("current_draft_order_id"))
            if current_pick_id is None:
                current_pick_id = self._first_open_pick_id(self._live_order_rows(conn, draft_year))
            if not is_admin and current_pick_id != int(draft_order_id):
                raise ValueError("not_current_pick")

            if parse_bool(payload.get("clear")):
                selection = conn.execute(
                    "SELECT version FROM draft_live_selections WHERE draft_order_id = ?",
                    (int(draft_order_id),),
                ).fetchone()
                if expected_selection_version is not None and (
                    not selection or parse_int(selection["version"]) != expected_selection_version
                ):
                    raise ValueError("stale_entity_version")
                conn.execute("DELETE FROM draft_live_selections WHERE draft_order_id = ?", (int(draft_order_id),))
            else:
                selection = conn.execute(
                    "SELECT version FROM draft_live_selections WHERE draft_order_id = ?",
                    (int(draft_order_id),),
                ).fetchone()
                if expected_selection_version is not None and (
                    parse_int(selection["version"]) if selection else None
                ) != expected_selection_version:
                    raise ValueError("stale_entity_version")
                option_value = str(payload.get("option_value") or "").strip()
                custom_text = str(payload.get("custom_text") or "").strip()
                skipped = parse_bool(payload.get("skipped"))
                if skipped:
                    selection_text, option_value, custom_text = "Saltado", "Saltado", ""
                elif option_value == "__other__":
                    if not custom_text:
                        raise ValueError("selection_required")
                    selection_text = custom_text
                else:
                    if not option_value:
                        raise ValueError("selection_required")
                    selection_text, custom_text = option_value, ""
                conn.execute(
                    """INSERT INTO draft_live_selections (
                           draft_order_id, selection_text, option_value, custom_text,
                           skipped, selected_by_email, selected_by_name, selected_by_role,
                           selected_at, version, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                       ON CONFLICT(draft_order_id) DO UPDATE SET
                           selection_text = excluded.selection_text,
                           option_value = excluded.option_value,
                           custom_text = excluded.custom_text,
                           skipped = excluded.skipped,
                           selected_by_email = excluded.selected_by_email,
                           selected_by_name = excluded.selected_by_name,
                           selected_by_role = excluded.selected_by_role,
                           selected_at = excluded.selected_at,
                           version = COALESCE(draft_live_selections.version, 0) + 1,
                           updated_at = excluded.updated_at""",
                    (
                        int(draft_order_id), selection_text, option_value, custom_text or None,
                        1 if skipped else 0, str(actor.get("email") or "").strip() or None,
                        str(actor.get("name") or "").strip() or None,
                        str(actor.get("role") or "").strip() or ("admin" if is_admin else "gm"),
                        timestamp, timestamp,
                    ),
                )

            rows = self._live_order_rows(conn, draft_year)
            state = conn.execute("SELECT * FROM draft_live_state WHERE draft_year = ?", (draft_year,)).fetchone()
            state_row = dict(state) if state else state_row
            should_advance = (
                parse_bool(payload.get("advance")) if "advance" in payload
                else current_pick_id == int(draft_order_id) and not parse_bool(payload.get("clear"))
            )
            if should_advance:
                next_pick_id = self._adjacent_pick_id(rows, int(draft_order_id), "next", prefer_open=True)
                if next_pick_id == int(draft_order_id):
                    next_pick_id = None
                duration_seconds = max(10, min(3600, parse_int(state_row.get("duration_seconds")) or 180))
                options_text = str(state_row.get("options_text") or "")
                conn.execute(
                    """INSERT INTO draft_live_state (
                       draft_year, enabled, current_draft_order_id, duration_seconds,
                           started_at, options_text, version, created_at, updated_at
                       ) VALUES (?, 1, ?, ?, ?, ?, 1, ?, ?)
                       ON CONFLICT(draft_year) DO UPDATE SET
                           enabled = 1,
                           current_draft_order_id = excluded.current_draft_order_id,
                           started_at = excluded.started_at,
                           version = COALESCE(draft_live_state.version, 0) + 1,
                           updated_at = excluded.updated_at""",
                    (draft_year, next_pick_id, duration_seconds, timestamp, options_text, timestamp, timestamp),
                )
            conn.commit()
            return self._live_payload(conn, draft_year)

    @staticmethod
    def _pick_request_from_row(row: Any) -> Dict[str, Any]:
        item = dict(row)
        item["request_type"] = "draft_pick"
        item["player_name"] = str(item.get("selection_text") or "")
        item["option_field"] = "draft_pick"
        item["action"] = "selected"
        draft_year = parse_int(item.get("draft_year"))
        item["season_year"] = draft_year
        item["season_label"] = f"Draft {draft_year}" if draft_year else "Draft"
        return item

    def create_pick_request(
        self, draft_order_id: int, payload: Dict[str, Any], requester: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        operations = self._read_operations()
        option_value = str(payload.get("option_value") or "").strip()
        custom_text = str(payload.get("custom_text") or "").strip()
        if not option_value or (option_value == "__other__" and not custom_text):
            raise ValueError("selection_required")
        selection_text = (custom_text if option_value == "__other__" else option_value).strip()
        if not selection_text:
            raise ValueError("selection_required")
        if len(selection_text) > 140:
            raise ValueError("selection_too_long")

        timestamp = operations.now()
        request_id: Optional[int] = None
        with self.db.connect() as conn:
            pick = conn.execute(
                """SELECT d.*, t.id AS owner_team_id, t.code AS owner_team_code
                   FROM draft_order d JOIN teams t ON t.code = d.owner_team_code
                   WHERE d.id = ?""",
                (int(draft_order_id),),
            ).fetchone()
            if not pick:
                return None
            state = conn.execute(
                "SELECT * FROM draft_live_state WHERE draft_year = ?", (int(pick["draft_year"]),)
            ).fetchone()
            state_row = dict(state) if state else {}
            if not parse_bool(state_row.get("enabled")):
                raise ValueError("draft_mode_inactive")
            expected_state_version = parse_int(payload.get("expected_state_version"))
            existing_state_version = parse_int(state_row.get("version"))
            if expected_state_version is not None and expected_state_version != existing_state_version:
                raise ValueError("stale_entity_version")
            rows = self._live_order_rows(conn, int(pick["draft_year"]))
            current_pick_id = parse_int(state_row.get("current_draft_order_id"))
            if current_pick_id not in {parse_int(row.get("id")) for row in rows}:
                current_pick_id = self._first_open_pick_id(rows)
            if int(draft_order_id) not in self._requestable_pick_ids(rows, current_pick_id):
                if self._pending_request_count(rows) >= operations.max_pending_requests:
                    raise ValueError("too_many_pending_draft_picks")
                raise ValueError("not_current_pick")
            if conn.execute(
                """SELECT draft_order_id FROM draft_live_selections
                   WHERE draft_order_id = ? AND COALESCE(selection_text, '') != ''""",
                (int(draft_order_id),),
            ).fetchone():
                raise ValueError("pick_already_selected")
            existing = conn.execute(
                "SELECT id FROM gm_draft_pick_requests WHERE draft_order_id = ? AND status = 'pending'",
                (int(draft_order_id),),
            ).fetchone()
            requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
            requester_email = str(requester.get("email") or "").strip() if requester else None
            requester_name = str(requester.get("name") or "").strip() if requester else None
            if existing:
                request_id = int(existing["id"])
                conn.execute(
                    """UPDATE gm_draft_pick_requests SET requester_user_id = ?, requester_email = ?,
                           requester_name = ?, option_value = ?, custom_text = ?, selection_text = ?, updated_at = ?
                       WHERE id = ?""",
                    (requester_user_id, requester_email, requester_name, option_value, custom_text or None,
                     selection_text, timestamp, request_id),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO gm_draft_pick_requests (
                           draft_order_id, team_id, requester_user_id, requester_email, requester_name,
                           option_value, custom_text, selection_text, status, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                    (int(draft_order_id), int(pick["owner_team_id"]), requester_user_id, requester_email,
                     requester_name, option_value, custom_text or None, selection_text, timestamp, timestamp),
                )
                request_id = int(cur.lastrowid)
                if self.workflows:
                    self.workflows.record_creation_conn(
                        conn, "gm_draft_pick_request", request_id, "pending", actor=requester,
                        reason="draft_pick_submitted", timestamp=timestamp,
                        metadata={"draft_order_id": int(draft_order_id),
                                  "team_code": str(pick["owner_team_code"]),
                                  "selection_text": selection_text},
                    )
            conn.commit()
        return self.pick_request(request_id) if request_id is not None else None

    def pick_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                """SELECT r.*, d.draft_year, d.draft_round, d.pick_number,
                          d.owner_team_code, d.original_team_code,
                          COALESCE(owner.name, d.owner_team_code) AS team_name,
                          owner.code AS team_code,
                          COALESCE(original.name, d.original_team_code) AS original_team_name
                   FROM gm_draft_pick_requests r
                   JOIN draft_order d ON d.id = r.draft_order_id
                   JOIN teams owner ON owner.id = r.team_id
                   LEFT JOIN teams original ON original.code = d.original_team_code
                   WHERE r.id = ?""",
                (int(request_id),),
            ).fetchone()
        return self._pick_request_from_row(row) if row else None

    def list_pick_requests(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        params: List[Any] = []
        where = ""
        if normalized_status and normalized_status != "all":
            where = "WHERE r.status = ?"
            params.append(normalized_status)
        with self.db.connect() as conn:
            rows = conn.execute(
                f"""SELECT r.*, d.draft_year, d.draft_round, d.pick_number,
                           d.owner_team_code, d.original_team_code,
                           COALESCE(owner.name, d.owner_team_code) AS team_name,
                           owner.code AS team_code,
                           COALESCE(original.name, d.original_team_code) AS original_team_name
                    FROM gm_draft_pick_requests r
                    JOIN draft_order d ON d.id = r.draft_order_id
                    JOIN teams owner ON owner.id = r.team_id
                    LEFT JOIN teams original ON original.code = d.original_team_code
                    {where}
                    ORDER BY CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,
                             r.created_at DESC, r.id DESC""",
                params,
            ).fetchall()
        return [self._pick_request_from_row(row) for row in rows]

    def mark_pick_request_decided(
        self,
        request_id: int,
        status: str,
        admin: Dict[str, Any],
        note: Optional[str] = None,
        *,
        expected_version: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        operations = self._read_operations()
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            raise ValueError("invalid_status")
        if not self.workflows:
            raise RuntimeError("draft_workflow_transition_not_configured")
        timestamp = operations.now()
        with self.db.transaction("IMMEDIATE") as conn:
            try:
                self.workflows.transition_conn(
                    conn, "gm_draft_pick_request", int(request_id), normalized_status,
                    actor=admin, reason=note or f"admin_{normalized_status}",
                    updates={
                        "admin_email": str(admin.get("email") or "").strip() if admin else None,
                        "admin_name": str(admin.get("name") or "").strip() if admin else None,
                        "admin_decision_note": note, "updated_at": timestamp, "decided_at": timestamp,
                    },
                    timestamp=timestamp,
                    expected_version=expected_version,
                )
            except WorkflowTransitionError as exc:
                if exc.code in {"workflow_not_found", "invalid_transition", "transition_conflict"}:
                    return None
                if exc.code == "version_conflict":
                    raise ValueError("stale_entity_version") from exc
                raise
        return self.pick_request(request_id)

    def _rookie_scale_salary_for_pick(
        self, settings: Dict[str, str], salary_season: int, pick_number: int
    ) -> Dict[str, Any]:
        operations = self._read_operations()
        if not operations.parse_amount_like:
            raise RuntimeError("draft_amount_parser_not_configured")
        checked_keys: List[str] = []

        def setting_amount(key: str) -> Optional[float]:
            checked_keys.append(key)
            parsed = operations.parse_amount_like(settings.get(key))
            return parsed if parsed is not None and parsed > 0 else None

        exact_key = f"rookie_scale_{int(salary_season)}_{int(pick_number)}"
        exact_amount = setting_amount(exact_key)
        if exact_amount is not None:
            return {"salary": exact_amount, "salary_season": int(salary_season),
                    "setting_key": exact_key, "source": "configured", "checked_keys": checked_keys}
        base_key = f"rookie_scale_2025_{int(pick_number)}"
        base_amount = setting_amount(base_key) if int(salary_season) != 2025 else None
        if base_amount is not None:
            base_cap = operations.parse_amount_like(settings.get("salary_cap_2025")) or 154_647_000.0
            season_cap = (
                operations.parse_amount_like(settings.get(f"salary_cap_{int(salary_season)}"))
                or operations.parse_amount_like(settings.get("salary_cap_2025")) or base_cap
            )
            if base_cap > 0 and season_cap > 0:
                return {"salary": base_amount * (season_cap / base_cap),
                        "salary_season": int(salary_season), "setting_key": base_key,
                        "source": "salary_cap_scaled_from_2025", "checked_keys": checked_keys}
        return {"salary": None, "salary_season": int(salary_season), "setting_key": exact_key,
                "source": "missing", "checked_keys": checked_keys}

    def process_results(self, draft_year: Any = None) -> Dict[str, Any]:
        operations = self._read_operations()
        year = parse_int(str(draft_year)) if draft_year is not None else self.current_year()
        if year is None or year < operations.contract_min_year or year > operations.contract_max_year:
            raise ValueError("unsupported_draft_year")
        if not operations.parse_salary_amount or not operations.resolve_profile_for_new_row:
            raise RuntimeError("draft_result_operations_not_configured")
        timestamp = operations.now()
        created_holds: List[Dict[str, Any]] = []
        created_rights: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        with self.db.transaction("IMMEDIATE") as conn:
            settings = {str(row["key"]): str(row["value"]) for row in conn.execute(
                "SELECT key, value FROM app_settings"
            ).fetchall()}
            rows = [dict(row) for row in conn.execute(
                """SELECT d.id AS draft_order_id, d.draft_year, d.draft_round, d.pick_number,
                          d.owner_team_code, d.original_team_code, t.id AS team_id,
                          COALESCE(t.name, d.owner_team_code) AS team_name, s.selection_text,
                          COALESCE(s.skipped, 0) AS skipped, s.processed_type,
                          s.processed_dead_contract_id, s.processed_asset_id, s.processed_at
                   FROM draft_order d JOIN teams t ON t.code = d.owner_team_code
                   LEFT JOIN draft_live_selections s ON s.draft_order_id = d.id
                   WHERE d.draft_year = ?
                   ORDER BY CASE d.draft_round WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END,
                            d.pick_number, d.id""",
                (int(year),),
            ).fetchall()]
            for row in rows:
                draft_order_id = parse_int(row.get("draft_order_id"))
                pick_number = parse_int(row.get("pick_number"))
                draft_round = operations.normalize_pick_round(row.get("draft_round"))
                selection_text = str(row.get("selection_text") or "").strip()
                team_code = operations.normalize_team_code(row.get("owner_team_code")) or ""
                team_id = parse_int(row.get("team_id"))
                if not draft_order_id or not team_id or not team_code:
                    continue
                base_result = {"draft_order_id": draft_order_id, "team_code": team_code,
                               "pick_number": pick_number, "draft_round": draft_round}
                if parse_bool(row.get("processed_at")) or str(row.get("processed_type") or "").strip():
                    skipped.append({**base_result, "reason": "already_processed"})
                    continue
                if parse_bool(row.get("skipped")):
                    skipped.append({**base_result, "reason": "pick_skipped"})
                    continue
                if not selection_text:
                    skipped.append({**base_result, "reason": "no_selection"})
                    continue
                if draft_round == "1st":
                    if pick_number is None or not 1 <= pick_number <= 30:
                        errors.append({**base_result, "selection": selection_text,
                                       "error": "rookie_scale_pick_out_of_range"})
                        continue
                    scale = self._rookie_scale_salary_for_pick(settings, int(year), int(pick_number))
                    projected_salary = scale.get("salary")
                    if projected_salary is None or projected_salary <= 0:
                        errors.append({**base_result, "selection": selection_text,
                                       "error": "missing_rookie_scale_salary",
                                       "salary_season": scale.get("salary_season"),
                                       "setting_key": scale.get("setting_key"),
                                       "checked_keys": scale.get("checked_keys") or []})
                        continue
                    salary_texts = {season: None for season in operations.contract_seasons}
                    salary_season = parse_int(scale.get("salary_season")) or int(year)
                    salary_texts[salary_season] = str(int(round(projected_salary)))
                    max_order = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM dead_contracts WHERE team_id = ?",
                        (team_id,),
                    ).fetchone()["mx"]
                    profile_id = operations.resolve_profile_for_new_row(
                        conn, {"name": selection_text}, name=selection_text, timestamp=timestamp
                    )
                    salary_values: List[Any] = []
                    for season in range(2025, 2031):
                        salary_text = salary_texts.get(season)
                        salary_values.extend((salary_text, operations.parse_salary_amount(salary_text)))
                    cur = conn.execute(
                        """INSERT INTO dead_contracts (
                               team_id, profile_id, row_order, dead_type, label, amount_text, amount_num,
                               exclude_from_gasto, exclude_from_cap,
                               salary_2025_text, salary_2025_num, salary_2026_text, salary_2026_num,
                               salary_2027_text, salary_2027_num, salary_2028_text, salary_2028_num,
                               salary_2029_text, salary_2029_num, salary_2030_text, salary_2030_num,
                               created_at, updated_at
                           ) VALUES (?, ?, ?, 'draft_hold', ?, ?, ?, 1, 0,
                                     ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (team_id, profile_id, int(max_order) + 1, selection_text,
                         salary_texts.get(2025), operations.parse_salary_amount(salary_texts.get(2025)),
                         *salary_values, timestamp, timestamp),
                    )
                    dead_contract_id = int(cur.lastrowid)
                    if profile_id is not None and operations.record_player_transaction_conn:
                        operations.record_player_transaction_conn(
                            conn, profile_id=int(profile_id), dead_contract_id=dead_contract_id,
                            action="draft_cap_hold", team_code=team_code,
                            summary=f"{team_code} añade el cap hold de draft de {selection_text}",
                            details={"draft_year": int(year), "salary_season": salary_season,
                                     "draft_round": draft_round, "pick_number": pick_number,
                                     "projected_salary": int(round(projected_salary)),
                                     "projected_salary_source": scale.get("source"),
                                     "rookie_scale_setting_key": scale.get("setting_key")},
                            created_at=timestamp,
                        )
                    conn.execute(
                        """UPDATE draft_live_selections SET processed_type = 'draft_cap_hold',
                               processed_dead_contract_id = ?, processed_asset_id = NULL,
                               processed_at = ?, updated_at = ? WHERE draft_order_id = ?""",
                        (dead_contract_id, timestamp, timestamp, draft_order_id),
                    )
                    created_holds.append({"draft_order_id": draft_order_id,
                                          "dead_contract_id": dead_contract_id, "team_code": team_code,
                                          "pick_number": pick_number, "selection": selection_text,
                                          "projected_salary": int(round(projected_salary)),
                                          "salary_season": salary_season,
                                          "projected_salary_source": scale.get("source"),
                                          "rookie_scale_setting_key": scale.get("setting_key")})
                    continue
                if draft_round == "2nd":
                    max_order = conn.execute(
                        "SELECT COALESCE(MAX(row_order), 0) AS mx FROM assets WHERE team_id = ?", (team_id,)
                    ).fetchone()["mx"]
                    cur = conn.execute(
                        """INSERT INTO assets (
                               team_id, row_order, asset_type, year, label, detail, amount_text, amount_num,
                               draft_pick_type, draft_round, original_owner, exception_type,
                               draft_pick_restricted, draft_pick_stepien_restricted, draft_pick_protected,
                               draft_pick_sold_to, draft_pick_conditional_teams, draft_pick_frozen,
                               created_at, updated_at
                           ) VALUES (?, ?, 'player_right', ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL,
                                     0, 0, 0, NULL, NULL, 0, ?, ?)""",
                        (team_id, int(max_order) + 1, str(int(year)), selection_text,
                         f"Draft {int(year)} · Pick #{pick_number} · 2ª ronda", timestamp, timestamp),
                    )
                    asset_id = int(cur.lastrowid)
                    conn.execute(
                        """UPDATE draft_live_selections SET processed_type = 'player_right',
                               processed_dead_contract_id = NULL, processed_asset_id = ?,
                               processed_at = ?, updated_at = ? WHERE draft_order_id = ?""",
                        (asset_id, timestamp, timestamp, draft_order_id),
                    )
                    created_rights.append({"draft_order_id": draft_order_id, "asset_id": asset_id,
                                           "team_code": team_code, "pick_number": pick_number,
                                           "selection": selection_text})
                    continue
                skipped.append({**base_result, "reason": "unsupported_round"})
            return {"ok": not errors, "draft_year": int(year),
                    "created_cap_holds": created_holds, "created_player_rights": created_rights,
                    "skipped": skipped, "errors": errors,
                    "draft_live": self._live_payload(conn, int(year))}
