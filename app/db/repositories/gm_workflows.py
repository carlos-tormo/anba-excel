"""SQL ownership for co-admin votes and score administration."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

try:
    from ...domain._values import parse_bool, parse_int
    from ...workflow_states import WorkflowTransitionError
except ImportError:  # pragma: no cover
    from domain._values import parse_bool, parse_int
    from workflow_states import WorkflowTransitionError

from .base import LeagueRepository


class CoadminVoteRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Callable[[], str], normalize_team_code: Callable[[Any], Optional[str]], normalize_team_codes: Callable[[Any], List[str]]) -> None:
        super().__init__(db)
        self.now = now
        self.normalize_team_code = normalize_team_code
        self.normalize_team_codes = normalize_team_codes

    def _coadmin_vote_from_row(self, cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["id"] = parse_int(item.get("id"))
        item["status"] = str(item.get("status") or "open").strip().lower() or "open"
        return item

    def _coadmin_expected_voters(self, conn: sqlite3.Connection) -> List[Dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT
                u.id,
                u.email,
                u.display_name,
                GROUP_CONCAT(t.code, ',') AS team_codes
            FROM users u
            LEFT JOIN user_team_assignments a ON a.user_id = u.id
            LEFT JOIN teams t ON t.id = a.team_id
            WHERE COALESCE(u.is_co_admin, 0) = 1
            GROUP BY u.id
            ORDER BY lower(u.email)
            """
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "email": row["email"],
                "display_name": row["display_name"],
                "team_codes": self.normalize_team_codes(row["team_codes"]),
            }
            for row in rows
        ]

    def create_coadmin_vote(self, title: Any, actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        cleaned_title = str(title or "").strip()
        if not cleaned_title:
            raise ValueError("title_required")
        if len(cleaned_title) > 140:
            raise ValueError("title_too_long")
        actor = actor or {}
        timestamp = self.now()
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO coadmin_votes (
                    title, status, created_by_email, created_by_name, created_at, updated_at
                ) VALUES (?, 'open', ?, ?, ?, ?)
                """,
                (
                    cleaned_title,
                    str(actor.get("email") or "").strip() or None,
                    str(actor.get("name") or "").strip() or None,
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            vote_id = int(cur.lastrowid)
        vote = self.get_coadmin_vote(vote_id)
        if not vote:
            raise RuntimeError("Failed to create co-admin vote")
        return vote

    def get_coadmin_vote(self, vote_id: Any) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(vote_id)
        if parsed_id is None:
            return None
        with self.db.connect() as conn:
            cur = conn.execute("SELECT * FROM coadmin_votes WHERE id = ?", (parsed_id,))
            row = cur.fetchone()
            return self._coadmin_vote_from_row(cur, row) if row else None

    def set_coadmin_vote_status(
        self,
        vote_id: Any,
        status: Any,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(vote_id)
        normalized_status = str(status or "").strip().lower()
        if parsed_id is None:
            raise ValueError("invalid_vote_id")
        if normalized_status not in {"open", "closed"}:
            raise ValueError("invalid_status")
        timestamp = self.now()
        with self.db.connect() as conn:
            existing = conn.execute("SELECT id FROM coadmin_votes WHERE id = ?", (parsed_id,)).fetchone()
            if not existing:
                return None
            conn.execute(
                """
                UPDATE coadmin_votes
                SET status = ?,
                    updated_at = ?,
                    closed_at = CASE WHEN ? = 'closed' THEN ? ELSE NULL END
                WHERE id = ?
                """,
                (normalized_status, timestamp, normalized_status, timestamp, parsed_id),
            )
            conn.commit()
        return self.get_coadmin_vote(parsed_id)

    def list_admin_coadmin_votes(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            expected_voters = self._coadmin_expected_voters(conn)
            expected_count = len(expected_voters)
            vote_cur = conn.execute(
                """
                SELECT *
                FROM coadmin_votes
                ORDER BY
                    CASE status WHEN 'open' THEN 0 ELSE 1 END,
                    datetime(created_at) DESC,
                    id DESC
                """
            )
            votes = [self._coadmin_vote_from_row(vote_cur, row) for row in vote_cur.fetchall()]
            teams = [dict(row) for row in conn.execute("SELECT id, code, name FROM teams ORDER BY code").fetchall()]
            for vote in votes:
                vote_id = int(vote["id"] or 0)
                submitted_rows = conn.execute(
                    """
                    SELECT DISTINCT voter_user_id
                    FROM coadmin_vote_scores
                    WHERE vote_id = ?
                    """,
                    (vote_id,),
                ).fetchall()
                submitted_ids = {int(row["voter_user_id"]) for row in submitted_rows}
                avg_rows = conn.execute(
                    """
                    SELECT
                        t.id AS team_id,
                        t.code AS team_code,
                        t.name AS team_name,
                        COUNT(s.score) AS vote_count,
                        AVG(s.score) AS average_score
                    FROM teams t
                    LEFT JOIN coadmin_vote_scores s
                        ON s.target_team_id = t.id
                       AND s.vote_id = ?
                    GROUP BY t.id
                    ORDER BY t.code
                    """,
                    (vote_id,),
                ).fetchall()
                averages = []
                for row in avg_rows:
                    average_score = row["average_score"]
                    averages.append(
                        {
                            "team_id": int(row["team_id"]),
                            "team_code": row["team_code"],
                            "team_name": row["team_name"],
                            "vote_count": int(row["vote_count"] or 0),
                            "average_score": round(float(average_score), 2) if average_score is not None else None,
                        }
                    )
                averages.sort(
                    key=lambda item: (
                        item["average_score"] is None,
                        -(item["average_score"] or 0),
                        str(item["team_code"] or ""),
                    )
                )
                score_rows = conn.execute(
                    """
                    SELECT
                        s.voter_user_id,
                        s.voter_email,
                        s.voter_name,
                        s.voter_team_code,
                        t.id AS target_team_id,
                        t.code AS target_team_code,
                        t.name AS target_team_name,
                        s.score,
                        s.updated_at
                    FROM coadmin_vote_scores s
                    JOIN teams t ON t.id = s.target_team_id
                    WHERE s.vote_id = ?
                    ORDER BY
                        lower(COALESCE(NULLIF(s.voter_name, ''), s.voter_email, CAST(s.voter_user_id AS TEXT))),
                        t.code
                    """,
                    (vote_id,),
                ).fetchall()
                voter_lookup = {int(voter["id"]): voter for voter in expected_voters}
                individual_by_voter: Dict[int, Dict[str, Any]] = {}
                for row in score_rows:
                    voter_id = int(row["voter_user_id"])
                    expected_voter = voter_lookup.get(voter_id, {})
                    item = individual_by_voter.setdefault(
                        voter_id,
                        {
                            "voter_user_id": voter_id,
                            "voter_email": row["voter_email"] or expected_voter.get("email"),
                            "voter_name": row["voter_name"] or expected_voter.get("display_name"),
                            "voter_team_code": row["voter_team_code"],
                            "team_codes": expected_voter.get("team_codes") or self.normalize_team_codes(row["voter_team_code"]),
                            "scores": [],
                        },
                    )
                    item["scores"].append(
                        {
                            "team_id": int(row["target_team_id"]),
                            "team_code": row["target_team_code"],
                            "team_name": row["target_team_name"],
                            "score": int(row["score"]),
                            "updated_at": row["updated_at"],
                        }
                    )
                individual_scores = list(individual_by_voter.values())
                individual_scores.sort(
                    key=lambda item: str(item.get("voter_name") or item.get("voter_email") or item.get("voter_user_id") or "").lower()
                )
                vote["expected_voter_count"] = expected_count
                vote["submitted_voter_count"] = len(submitted_ids)
                vote["all_submitted"] = expected_count > 0 and len(submitted_ids) >= expected_count
                vote["averages"] = averages
                vote["individual_scores"] = individual_scores
                vote["voters"] = [
                    {
                        **voter,
                        "submitted": int(voter["id"]) in submitted_ids,
                    }
                    for voter in expected_voters
                ]
                vote["teams"] = teams
            return votes

    def list_coadmin_votes_for_session(self, session: Dict[str, Any]) -> Dict[str, Any]:
        user_id = parse_int(session.get("user_id"))
        role = str(session.get("role") or "").strip().lower()
        if user_id is None or role != "co_admin":
            return {"votes": [], "own_team_codes": []}
        own_team_codes = self.normalize_team_codes(session.get("team_codes"))
        with self.db.connect() as conn:
            team_rows = conn.execute("SELECT id, code, name FROM teams ORDER BY code").fetchall()
            target_teams = [
                {"id": int(row["id"]), "code": row["code"], "name": row["name"]}
                for row in team_rows
                if str(row["code"] or "").strip().upper() not in own_team_codes
            ]
            vote_cur = conn.execute(
                """
                SELECT *
                FROM coadmin_votes
                WHERE status = 'open'
                ORDER BY datetime(created_at) DESC, id DESC
                """
            )
            votes = [self._coadmin_vote_from_row(vote_cur, row) for row in vote_cur.fetchall()]
            expected_count = len(self._coadmin_expected_voters(conn))
            for vote in votes:
                vote_id = int(vote["id"] or 0)
                score_rows = conn.execute(
                    """
                    SELECT t.code AS team_code, s.score
                    FROM coadmin_vote_scores s
                    JOIN teams t ON t.id = s.target_team_id
                    WHERE s.vote_id = ? AND s.voter_user_id = ?
                    """,
                    (vote_id, user_id),
                ).fetchall()
                scores = {str(row["team_code"]).upper(): int(row["score"]) for row in score_rows}
                submitted_count = conn.execute(
                    """
                    SELECT COUNT(DISTINCT voter_user_id)
                    FROM coadmin_vote_scores
                    WHERE vote_id = ?
                    """,
                    (vote_id,),
                ).fetchone()[0]
                vote["target_teams"] = target_teams
                vote["scores"] = scores
                vote["submitted"] = len(scores) >= len(target_teams) and len(target_teams) > 0
                vote["submitted_voter_count"] = int(submitted_count or 0)
                vote["expected_voter_count"] = expected_count
            return {"votes": votes, "own_team_codes": own_team_codes}

    def submit_coadmin_vote(
        self,
        vote_id: Any,
        scores: Any,
        session: Dict[str, Any],
    ) -> Dict[str, Any]:
        parsed_vote_id = parse_int(vote_id)
        user_id = parse_int(session.get("user_id"))
        if parsed_vote_id is None:
            raise ValueError("invalid_vote_id")
        if user_id is None or str(session.get("role") or "").strip().lower() != "co_admin":
            raise ValueError("coadmin_required")
        if not isinstance(scores, dict):
            raise ValueError("scores_required")
        own_team_codes = self.normalize_team_codes(session.get("team_codes"))
        with self.db.connect() as conn:
            vote_row = conn.execute("SELECT id, status FROM coadmin_votes WHERE id = ?", (parsed_vote_id,)).fetchone()
            if not vote_row:
                raise ValueError("vote_not_found")
            if str(vote_row["status"] or "").lower() != "open":
                raise ValueError("vote_closed")

            team_rows = conn.execute("SELECT id, code FROM teams ORDER BY code").fetchall()
            team_by_code = {str(row["code"]).upper(): int(row["id"]) for row in team_rows}
            target_codes = [code for code in team_by_code if code not in own_team_codes]
            normalized_scores: Dict[str, int] = {}
            for raw_code, raw_score in scores.items():
                code = self.normalize_team_code(raw_code)
                if not code or code not in team_by_code:
                    raise ValueError("invalid_team_code")
                if code in own_team_codes:
                    raise ValueError("own_team_score_not_allowed")
                score = parse_int(raw_score)
                if score is None or score < 1 or score > 100:
                    raise ValueError("invalid_score")
                normalized_scores[code] = int(score)
            missing = [code for code in target_codes if code not in normalized_scores]
            extra = [code for code in normalized_scores if code not in target_codes]
            if missing:
                raise ValueError(f"missing_scores:{','.join(missing)}")
            if extra:
                raise ValueError("invalid_score_targets")

            timestamp = self.now()
            voter_email = str(session.get("email") or "").strip() or None
            voter_name = str(session.get("name") or "").strip() or None
            voter_team_code = own_team_codes[0] if own_team_codes else None
            for code, score in normalized_scores.items():
                conn.execute(
                    """
                    INSERT INTO coadmin_vote_scores (
                        vote_id,
                        voter_user_id,
                        voter_email,
                        voter_name,
                        voter_team_code,
                        target_team_id,
                        score,
                        created_at,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(vote_id, voter_user_id, target_team_id)
                    DO UPDATE SET
                        voter_email = excluded.voter_email,
                        voter_name = excluded.voter_name,
                        voter_team_code = excluded.voter_team_code,
                        score = excluded.score,
                        updated_at = excluded.updated_at
                    """,
                    (
                        parsed_vote_id,
                        user_id,
                        voter_email,
                        voter_name,
                        voter_team_code,
                        team_by_code[code],
                        score,
                        timestamp,
                        timestamp,
                    ),
                )
            conn.execute("UPDATE coadmin_votes SET updated_at = ? WHERE id = ?", (timestamp, parsed_vote_id))
            conn.commit()
        refreshed = self.list_coadmin_votes_for_session(session)
        return next((vote for vote in refreshed.get("votes", []) if int(vote.get("id") or 0) == parsed_vote_id), {})


@dataclass(frozen=True)
class GMRequestOperations:
    now: Callable[[], str]
    normalize_team_code: Callable[[Any], Optional[str]]
    contract_min_year: int
    contract_max_year: int


class GMRequestRepository(LeagueRepository):
    def __init__(self, db: Any, operations: GMRequestOperations, *, workflows: Any) -> None:
        super().__init__(db)
        self.operations = operations
        self.workflows = workflows

    def list_requests(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        params: List[Any] = []
        where = ""
        if normalized_status and normalized_status != "all":
            where = "WHERE r.status = ?"
            params.append(normalized_status)
        with self.db.connect() as conn:
            option_rows = conn.execute(
                f"""SELECT r.*, p.name AS player_name, t.code AS team_code, t.name AS team_name
                    FROM gm_option_requests r JOIN players p ON p.id = r.player_id
                    JOIN teams t ON t.id = r.team_id {where}
                    ORDER BY CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,
                             r.created_at DESC, r.id DESC""",
                params,
            ).fetchall()
            offer_rows = conn.execute(
                f"""SELECT r.*, f.name AS player_name, f.profile_id, f.position, f.rating,
                           f.free_agent_type, f.rights_team_code,
                           t.code AS team_code, t.name AS team_name
                    FROM gm_free_agent_offer_requests r
                    LEFT JOIN free_agents f ON f.id = r.free_agent_id
                    JOIN teams t ON t.id = r.team_id {where}
                    ORDER BY CASE r.status WHEN 'pending' THEN 0 ELSE 1 END,
                             r.created_at DESC, r.id DESC""",
                params,
            ).fetchall()
        return [self._gm_option_request_from_row(None, row) for row in option_rows] + [
            self._gm_free_agent_offer_request_from_row(None, row) for row in offer_rows
        ]

    def _gm_option_request_from_row(self, cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["request_type"] = "option"
        raw_field = str(item.get("option_field") or "")
        salary_text_match = re.fullmatch(r"salary_(20\d{2})_text", raw_field)
        if salary_text_match and str(item.get("action") or "").strip().lower() == "renounced":
            item["request_type"] = "bird_rights_renounce"
            season_year = parse_int(salary_text_match.group(1))
            item["season_year"] = season_year
            item["season_label"] = f"{season_year}-{(season_year + 1) % 100:02d}" if season_year else ""
            return item
        match = re.fullmatch(r"option_(20\d{2})", raw_field)
        season_year = parse_int(match.group(1)) if match else None
        item["season_year"] = season_year
        item["season_label"] = f"{season_year}-{(season_year + 1) % 100:02d}" if season_year else ""
        return item

    def _gm_free_agent_offer_request_from_row(self, cursor: sqlite3.Cursor, row: sqlite3.Row) -> Dict[str, Any]:
        item = dict(row)
        item["request_type"] = "free_agent_offer"
        item["action"] = "offered"
        item["option_field"] = "free_agent_offer"
        offer_type = str(item.get("offer_type") or "free_agent_offer").strip().lower()
        item["option_value"] = "Renovación" if offer_type == "renewal" else "Oferta FA"
        raw_payload = str(item.get("offer_payload_json") or "{}")
        try:
            offer_payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            offer_payload = {}
        if not isinstance(offer_payload, dict):
            offer_payload = {}
        item["offer_payload"] = offer_payload
        if not str(item.get("player_name") or "").strip():
            item["player_name"] = str(offer_payload.get("player_name") or offer_payload.get("name") or "Agente libre")
        contract_type = str(offer_payload.get("contract_type") or "").strip() or "Sin tipo"
        years = parse_int(offer_payload.get("years"))
        years_text = f"{years} año(s)" if years is not None and years > 0 else "Sin duración"
        item["season_label"] = f"{contract_type} · {years_text}"
        item["offer_contract_type"] = contract_type
        item["offer_years"] = years
        return item

    def offer_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Decode an offer request selected by another repository read model."""
        return self._gm_free_agent_offer_request_from_row(None, row)

    def get_gm_option_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            cur = conn.execute(
                """
                SELECT
                    r.*,
                    p.name AS player_name,
                    t.code AS team_code,
                    t.name AS team_name
                FROM gm_option_requests r
                JOIN players p ON p.id = r.player_id
                JOIN teams t ON t.id = r.team_id
                WHERE r.id = ?
                """,
                (int(request_id),),
            )
            row = cur.fetchone()
            return self._gm_option_request_from_row(cur, row) if row else None

    def record_admin_option_decision(
        self,
        player_id: int,
        option_field: str,
        option_value: str,
        action: str,
        admin: Dict[str, Any],
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        field = str(option_field or "").strip()
        if not re.fullmatch(r"option_(20\d{2})", field):
            raise ValueError("invalid_option_field")
        option = str(option_value or "").strip().upper()
        if option not in {"TO", "PO", "QO", "GAP"}:
            raise ValueError("invalid_option_value")
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"accepted", "rejected"}:
            raise ValueError("invalid_option_action")

        timestamp = self.operations.now()
        with self.db.transaction("IMMEDIATE") as conn:
            player = conn.execute(
                f"SELECT id, team_id, {field} AS current_option FROM players WHERE id = ?",
                (int(player_id),),
            ).fetchone()
            if not player:
                return None
            cur = conn.execute(
                """INSERT INTO gm_option_requests (
                       player_id, team_id, requester_user_id, requester_email,
                       requester_name, option_field, option_value, action, status,
                       created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (
                    int(player_id),
                    int(player["team_id"]),
                    parse_int(str(admin.get("user_id") or "")) if admin else None,
                    str(admin.get("email") or "").strip() if admin else None,
                    str(admin.get("name") or "").strip() if admin else None,
                    field,
                    option,
                    normalized_action,
                    timestamp,
                    timestamp,
                ),
            )
            request_id = int(cur.lastrowid)
            metadata = {
                "player_id": int(player_id),
                "option_field": field,
                "option_value": option,
                "action": normalized_action,
            }
            self.workflows.record_creation_conn(
                conn,
                "gm_option_request",
                request_id,
                "pending",
                actor=admin,
                reason="admin_option_decision_created",
                command_id=f"gm-option:{request_id}:created",
                metadata=metadata,
                timestamp=timestamp,
            )
            self.workflows.transition_conn(
                conn,
                "gm_option_request",
                request_id,
                "approved",
                actor=admin,
                reason="admin_option_decision_recorded",
                command_id=f"gm-option:{request_id}:approved",
                updates={
                    "admin_email": str(admin.get("email") or "").strip() if admin else None,
                    "admin_name": str(admin.get("name") or "").strip() if admin else None,
                    "admin_decision_note": note,
                    "updated_at": timestamp,
                    "decided_at": timestamp,
                },
                metadata=metadata,
                timestamp=timestamp,
            )
        return self.get_gm_option_request(request_id)

    def _get_gm_free_agent_offer_request_conn(
        self,
        conn: sqlite3.Connection,
        request_id: int,
    ) -> Optional[Dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT
                r.*,
                f.name AS player_name,
                f.profile_id,
                f.position,
                f.rating,
                f.free_agent_type,
                f.rights_team_code,
                t.code AS team_code,
                t.name AS team_name
            FROM gm_free_agent_offer_requests r
            LEFT JOIN free_agents f ON f.id = r.free_agent_id
            JOIN teams t ON t.id = r.team_id
            WHERE r.id = ?
            """,
            (int(request_id),),
        )
        row = cur.fetchone()
        return self._gm_free_agent_offer_request_from_row(cur, row) if row else None

    def get_gm_free_agent_offer_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            return self._get_gm_free_agent_offer_request_conn(conn, request_id)

    def create_gm_option_request(
        self,
        player_id: int,
        option_field: str,
        option_value: str,
        action: str,
        requester: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        field = str(option_field or "").strip()
        match = re.fullmatch(r"option_(20\d{2})", field)
        if not match:
            raise ValueError("invalid_option_field")
        option = str(option_value or "").strip().upper()
        if option not in {"TO", "QO", "GAP"}:
            raise ValueError("invalid_option_value")
        normalized_action = str(action or "").strip().lower()
        if normalized_action not in {"accepted", "rejected"}:
            raise ValueError("invalid_option_action")

        timestamp = self.operations.now()
        request_id: Optional[int] = None
        with self.db.connect() as conn:
            cur = conn.execute(
                f"""
                SELECT p.id, COALESCE(pp.name, p.name) AS name, p.team_id, p.{field} AS current_option, t.code AS team_code
                FROM players p
                LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                JOIN teams t ON t.id = p.team_id
                WHERE p.id = ?
                """,
                (int(player_id),),
            )
            player = cur.fetchone()
            if not player:
                return None
            current_option = str(player["current_option"] or "").strip().upper()
            if current_option != option:
                raise ValueError("option_mismatch")

            existing = conn.execute(
                """
                SELECT id
                FROM gm_option_requests
                WHERE player_id = ? AND option_field = ? AND status = 'pending'
                """,
                (int(player_id), field),
            ).fetchone()
            if existing:
                request_id = int(existing["id"])
                requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
                conn.execute(
                    """
                    UPDATE gm_option_requests
                    SET
                        requester_user_id = ?,
                        requester_email = ?,
                        requester_name = ?,
                        option_value = ?,
                        action = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        option,
                        normalized_action,
                        timestamp,
                        request_id,
                    ),
                )
            else:
                requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
                req_cur = conn.execute(
                    """
                    INSERT INTO gm_option_requests (
                        player_id,
                        team_id,
                        requester_user_id,
                        requester_email,
                        requester_name,
                        option_field,
                        option_value,
                        action,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        int(player_id),
                        int(player["team_id"]),
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        field,
                        option,
                        normalized_action,
                        timestamp,
                        timestamp,
                    ),
                )
                request_id = int(req_cur.lastrowid)
                self.workflows.record_creation_conn(
                    conn,
                    "gm_option_request",
                    request_id,
                    "pending",
                    actor=requester,
                    reason="option_request_submitted",
                    timestamp=timestamp,
                    metadata={
                        "player_id": int(player_id),
                        "option_field": field,
                        "option_value": option,
                        "action": normalized_action,
                    },
                )
            conn.commit()

        return self.get_gm_option_request(request_id) if request_id is not None else None

    def create_gm_bird_rights_renounce_request(
        self,
        player_id: int,
        season_year: int,
        rights_value: str,
        requester: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        season = parse_int(season_year)
        if season is None or season < self.operations.contract_min_year or season > self.operations.contract_max_year:
            raise ValueError("invalid_renounce_season")
        field = f"salary_{season}_text"
        rights = str(rights_value or "").strip().upper()
        if rights not in {"FB", "EB", "NB"}:
            raise ValueError("invalid_bird_rights_value")

        timestamp = self.operations.now()
        request_id: Optional[int] = None
        with self.db.connect() as conn:
            settings_cur = conn.execute("SELECT key, value FROM app_settings")
            settings = {str(row["key"]): str(row["value"]) for row in settings_cur.fetchall()}
            current_year = parse_int(settings.get("current_year")) or 2025
            if not parse_bool(settings.get("free_agency_mode")):
                raise ValueError("free_agency_mode_required")
            if season != int(current_year):
                raise ValueError("invalid_renounce_season")

            cur = conn.execute(
                f"""
                SELECT p.id, COALESCE(pp.name, p.name) AS name, p.team_id, p.{field} AS current_rights, t.code AS team_code
                FROM players p
                LEFT JOIN player_profiles pp ON pp.id = p.profile_id
                JOIN teams t ON t.id = p.team_id
                WHERE p.id = ?
                """,
                (int(player_id),),
            )
            player = cur.fetchone()
            if not player:
                return None
            current_rights = str(player["current_rights"] or "").strip().upper()
            if current_rights != rights:
                raise ValueError("bird_rights_mismatch")

            existing = conn.execute(
                """
                SELECT id
                FROM gm_option_requests
                WHERE player_id = ? AND option_field = ? AND status = 'pending'
                """,
                (int(player_id), field),
            ).fetchone()
            requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
            if existing:
                request_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE gm_option_requests
                    SET
                        requester_user_id = ?,
                        requester_email = ?,
                        requester_name = ?,
                        option_value = ?,
                        action = 'renounced',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        rights,
                        timestamp,
                        request_id,
                    ),
                )
            else:
                req_cur = conn.execute(
                    """
                    INSERT INTO gm_option_requests (
                        player_id,
                        team_id,
                        requester_user_id,
                        requester_email,
                        requester_name,
                        option_field,
                        option_value,
                        action,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'renounced', 'pending', ?, ?)
                    """,
                    (
                        int(player_id),
                        int(player["team_id"]),
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        field,
                        rights,
                        timestamp,
                        timestamp,
                    ),
                )
                request_id = int(req_cur.lastrowid)
                self.workflows.record_creation_conn(
                    conn,
                    "gm_option_request",
                    request_id,
                    "pending",
                    actor=requester,
                    reason="bird_rights_renounce_requested",
                    timestamp=timestamp,
                    metadata={
                        "player_id": int(player_id),
                        "season_year": int(season),
                        "rights_value": rights,
                    },
                )
            conn.commit()

        return self.get_gm_option_request(request_id) if request_id is not None else None

    def create_gm_free_agent_offer_request(
        self,
        free_agent_id: int,
        team_code: str,
        payload: Dict[str, Any],
        requester: Dict[str, Any],
        offer_type: str = "free_agent_offer",
    ) -> Optional[Dict[str, Any]]:
        normalized_team = self.operations.normalize_team_code(team_code)
        if not normalized_team:
            raise ValueError("invalid_team_code")
        normalized_offer_type = str(offer_type or "free_agent_offer").strip().lower()
        if normalized_offer_type not in {"free_agent_offer", "renewal"}:
            normalized_offer_type = "free_agent_offer"
        offer_payload = dict(payload) if isinstance(payload, dict) else {}
        requester_user_id = parse_int(str(requester.get("user_id") or "")) if requester else None
        timestamp = self.operations.now()
        request_id: Optional[int] = None
        with self.db.transaction("IMMEDIATE") as conn:
            free_agent = conn.execute(
                "SELECT id, name, profile_id FROM free_agents WHERE id = ?",
                (int(free_agent_id),),
            ).fetchone()
            if not free_agent:
                return None
            offer_payload.setdefault("player_name", free_agent["name"])
            if free_agent["profile_id"] is not None:
                offer_payload.setdefault("profile_id", free_agent["profile_id"])
            offer_payload_json = json.dumps(offer_payload, ensure_ascii=False, sort_keys=True)
            team = conn.execute(
                "SELECT id FROM teams WHERE code = ?",
                (normalized_team,),
            ).fetchone()
            if not team:
                raise ValueError("invalid_team_code")
            existing = conn.execute(
                """
                SELECT id
                FROM gm_free_agent_offer_requests
                WHERE free_agent_id = ? AND team_id = ? AND status = 'pending'
                """,
                (int(free_agent_id), int(team["id"])),
            ).fetchone()
            if existing:
                request_id = int(existing["id"])
                conn.execute(
                    """
                    UPDATE gm_free_agent_offer_requests
                    SET
                        requester_user_id = ?,
                        requester_email = ?,
                        requester_name = ?,
                        offer_payload_json = ?,
                        offer_type = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        offer_payload_json,
                        normalized_offer_type,
                        timestamp,
                        request_id,
                    ),
                )
            else:
                req_cur = conn.execute(
                    """
                    INSERT INTO gm_free_agent_offer_requests (
                        free_agent_id,
                        team_id,
                        requester_user_id,
                        requester_email,
                        requester_name,
                        offer_payload_json,
                        offer_type,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        int(free_agent_id),
                        int(team["id"]),
                        requester_user_id,
                        str(requester.get("email") or "").strip() if requester else None,
                        str(requester.get("name") or "").strip() if requester else None,
                        offer_payload_json,
                        normalized_offer_type,
                        timestamp,
                        timestamp,
                    ),
                )
                request_id = int(req_cur.lastrowid)
                self.workflows.record_creation_conn(
                    conn,
                    "gm_free_agent_offer_request",
                    request_id,
                    "pending",
                    actor=requester,
                    reason="offer_submitted",
                    timestamp=timestamp,
                    metadata={
                        "team_code": normalized_team,
                        "free_agent_id": int(free_agent_id),
                        "offer_type": normalized_offer_type,
                    },
                )

        return self.get_gm_free_agent_offer_request(request_id) if request_id is not None else None

    def mark_gm_option_request_decided(
        self,
        request_id: int,
        status: str,
        admin: Dict[str, Any],
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            raise ValueError("invalid_status")
        timestamp = self.operations.now()
        with self.db.transaction("IMMEDIATE") as conn:
            try:
                self.workflows.transition_conn(
                    conn,
                    "gm_option_request",
                    int(request_id),
                    normalized_status,
                    actor=admin,
                    reason=note or f"admin_{normalized_status}",
                    updates={
                        "admin_email": str(admin.get("email") or "").strip() if admin else None,
                        "admin_name": str(admin.get("name") or "").strip() if admin else None,
                        "admin_decision_note": note,
                        "updated_at": timestamp,
                        "decided_at": timestamp,
                    },
                    timestamp=timestamp,
                )
            except WorkflowTransitionError as exc:
                if exc.code in {"workflow_not_found", "invalid_transition", "transition_conflict"}:
                    return None
                raise
        return self.get_gm_option_request(request_id)

    def cancel_gm_free_agent_offer_request(
        self,
        request_id: Any,
        team_code: Any,
        actor: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(request_id)
        normalized_team = self.operations.normalize_team_code(team_code)
        if parsed_id is None or parsed_id <= 0:
            raise ValueError("invalid_request_id")
        if not normalized_team:
            raise ValueError("team_code_required")
        with self.db.transaction("IMMEDIATE") as conn:
            cur = conn.execute(
                """
                SELECT
                    r.*,
                    f.name AS player_name,
                    f.profile_id,
                    f.position,
                    f.rating,
                    f.free_agent_type,
                    f.rights_team_code,
                    t.code AS team_code,
                    t.name AS team_name
                FROM gm_free_agent_offer_requests r
                LEFT JOIN free_agents f ON f.id = r.free_agent_id
                JOIN teams t ON t.id = r.team_id
                WHERE r.id = ? AND t.code = ?
                """,
                (parsed_id, normalized_team),
            )
            row = cur.fetchone()
            if not row:
                return None
            item = self._gm_free_agent_offer_request_from_row(cur, row)
            if str(item.get("status") or "").strip().lower() != "pending":
                raise ValueError("offer_not_pending")
            try:
                self.workflows.transition_conn(
                    conn,
                    "gm_free_agent_offer_request",
                    parsed_id,
                    "cancelled",
                    actor=actor,
                    reason="offer_cancelled_by_team",
                    updates={"updated_at": self.operations.now(), "decided_at": self.operations.now()},
                    command_id=f"gm-free-agent-offer:{parsed_id}:cancelled",
                )
            except WorkflowTransitionError as err:
                raise ValueError("offer_not_pending")
            item["status"] = "cancelled"
            return item
