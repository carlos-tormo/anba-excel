"""Persistence for GM minimum-target submissions and administration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .base import LeagueRepository


class GMMinimumTargetRepository(LeagueRepository):
    def get_submission_rows(self, user_id: int) -> Dict[str, Any]:
        with self.db.connect() as conn:
            user = conn.execute(
                """
                SELECT u.id, u.email, u.display_name,
                       GROUP_CONCAT(t.code, ',') AS team_codes
                FROM users u
                LEFT JOIN user_team_assignments ut ON ut.user_id = u.id
                LEFT JOIN teams t ON t.id = ut.team_id
                WHERE u.id = ?
                GROUP BY u.id
                """,
                (user_id,),
            ).fetchone()
            if not user:
                raise ValueError("user_not_found")
            status = conn.execute(
                "SELECT * FROM gm_minimum_target_status WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            targets = conn.execute(
                """
                SELECT mt.*, f.name AS free_agent_name, f.position, f.rating,
                       f.free_agent_type, f.rights_team_code
                FROM gm_minimum_targets mt
                JOIN free_agents f ON f.id = mt.free_agent_id
                WHERE mt.user_id = ?
                ORDER BY mt.rank
                """,
                (user_id,),
            ).fetchall()
            return {
                "user": dict(user),
                "status": dict(status) if status else None,
                "targets": [dict(row) for row in targets],
            }

    def replace_submission(
        self,
        user_id: int,
        team_code: Optional[str],
        targets: Sequence[Dict[str, Any]],
        timestamp: str,
    ) -> None:
        with self.db.connect() as conn:
            self._validate_team(conn, team_code)
            resolved: List[Dict[str, Any]] = []
            for target in targets:
                row = conn.execute(
                    "SELECT id, profile_id, name FROM free_agents WHERE id = ?",
                    (target["free_agent_id"],),
                ).fetchone()
                if not row:
                    raise ValueError("free_agent_not_found")
                resolved.append(
                    {
                        **target,
                        "free_agent_id": int(row["id"]),
                        "profile_id": row["profile_id"],
                        "player_name": str(row["name"] or "").strip(),
                    }
                )
            conn.execute("DELETE FROM gm_minimum_targets WHERE user_id = ?", (user_id,))
            conn.executemany(
                """
                INSERT INTO gm_minimum_targets
                    (user_id, rank, free_agent_id, profile_id, player_name, role,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        user_id, target["rank"], target["free_agent_id"],
                        target["profile_id"], target["player_name"], target["role"],
                        timestamp, timestamp,
                    )
                    for target in resolved
                ],
            )
            self._upsert_status(conn, user_id, team_code, omitted=False, timestamp=timestamp)
            conn.commit()

    def omit_submission(self, user_id: int, team_code: Optional[str], timestamp: str) -> None:
        with self.db.connect() as conn:
            self._validate_team(conn, team_code)
            conn.execute("DELETE FROM gm_minimum_targets WHERE user_id = ?", (user_id,))
            self._upsert_status(conn, user_id, team_code, omitted=True, timestamp=timestamp)
            conn.commit()

    @staticmethod
    def _validate_team(conn: Any, team_code: Optional[str]) -> None:
        if team_code and not conn.execute(
            "SELECT 1 FROM teams WHERE code = ?", (team_code,)
        ).fetchone():
            raise ValueError("team_not_found")

    @staticmethod
    def _upsert_status(
        conn: Any,
        user_id: int,
        team_code: Optional[str],
        *,
        omitted: bool,
        timestamp: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO gm_minimum_target_status
                (user_id, team_code, answered, omitted, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                team_code = excluded.team_code,
                answered = 1,
                omitted = excluded.omitted,
                updated_at = excluded.updated_at
            """,
            (user_id, team_code, int(omitted), timestamp, timestamp),
        )

    def remove_target(self, user_id: int, rank: int, timestamp: str) -> bool:
        with self.db.connect() as conn:
            existing = conn.execute(
                "SELECT 1 FROM gm_minimum_targets WHERE user_id = ? AND rank = ?",
                (user_id, rank),
            ).fetchone()
            if not existing:
                return False
            conn.execute(
                "DELETE FROM gm_minimum_targets WHERE user_id = ? AND rank = ?",
                (user_id, rank),
            )
            conn.execute(
                "UPDATE gm_minimum_target_status SET updated_at = ? WHERE user_id = ?",
                (timestamp, user_id),
            )
            conn.commit()
            return True

    def list_handicap_rows(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT team_code, handicap FROM gm_minimum_target_handicaps ORDER BY team_code"
                ).fetchall()
            ]

    def set_handicap(self, team_code: str, handicap: int, timestamp: str) -> None:
        with self.db.connect() as conn:
            self._validate_team(conn, team_code)
            if handicap == 0:
                conn.execute(
                    "DELETE FROM gm_minimum_target_handicaps WHERE team_code = ?",
                    (team_code,),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO gm_minimum_target_handicaps (team_code, handicap, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(team_code) DO UPDATE SET
                        handicap = excluded.handicap,
                        updated_at = excluded.updated_at
                    """,
                    (team_code, handicap, timestamp),
                )
            conn.commit()

    def list_admin_submission_rows(self) -> Dict[str, List[Dict[str, Any]]]:
        with self.db.connect() as conn:
            users = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT u.id, u.email, u.display_name,
                           COALESCE(u.is_co_admin, 0) AS is_co_admin,
                           GROUP_CONCAT(t.code, ',') AS team_codes,
                           s.answered, s.omitted, s.updated_at
                    FROM users u
                    LEFT JOIN user_team_assignments ut ON ut.user_id = u.id
                    LEFT JOIN teams t ON t.id = ut.team_id
                    LEFT JOIN gm_minimum_target_status s ON s.user_id = u.id
                    WHERE COALESCE(u.is_co_admin, 0) = 1
                       OR ut.user_id IS NOT NULL OR s.user_id IS NOT NULL
                    GROUP BY u.id
                    ORDER BY COALESCE(t.code, ''),
                             COALESCE(u.display_name, u.email) COLLATE NOCASE
                    """
                ).fetchall()
            ]
            if not users:
                return {"users": [], "targets": []}
            placeholders = ",".join("?" for _ in users)
            targets = [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT mt.*, f.position, f.rating, f.free_agent_type,
                           f.rights_team_code
                    FROM gm_minimum_targets mt
                    JOIN free_agents f ON f.id = mt.free_agent_id
                    WHERE mt.user_id IN ({placeholders})
                    ORDER BY mt.user_id, mt.rank
                    """,
                    tuple(int(user["id"]) for user in users),
                ).fetchall()
            ]
            return {"users": users, "targets": targets}

    def scoring_rows(self) -> Dict[str, Any]:
        with self.db.connect() as conn:
            return {
                "teams": [dict(row) for row in conn.execute("SELECT code, name FROM teams")],
                "users": [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT u.id, u.email, u.display_name,
                               GROUP_CONCAT(t.code, ',') AS team_codes
                        FROM users u
                        LEFT JOIN user_team_assignments ut ON ut.user_id = u.id
                        LEFT JOIN teams t ON t.id = ut.team_id
                        GROUP BY u.id
                        """
                    ).fetchall()
                ],
                "appeals": [dict(row) for row in conn.execute("SELECT * FROM free_agent_team_appeal")],
                "handicaps": [
                    dict(row)
                    for row in conn.execute(
                        "SELECT team_code, handicap FROM gm_minimum_target_handicaps"
                    ).fetchall()
                ],
                "targets": [
                    dict(row)
                    for row in conn.execute(
                        """
                        SELECT mt.user_id, mt.rank, mt.free_agent_id, mt.profile_id,
                               mt.player_name, mt.role, f.position, f.rating,
                               f.rights_team_code, pp.date_of_birth
                        FROM gm_minimum_targets mt
                        JOIN free_agents f ON f.id = mt.free_agent_id
                        LEFT JOIN player_profiles pp
                          ON pp.id = COALESCE(mt.profile_id, f.profile_id)
                        ORDER BY mt.user_id, mt.rank
                        """
                    ).fetchall()
                ],
            }
