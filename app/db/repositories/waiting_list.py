"""Waiting-list persistence."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from ...domain._values import parse_int
except ImportError:  # pragma: no cover
    from domain._values import parse_int

from .base import LeagueRepository


class WaitingListRepository(LeagueRepository):
    def __init__(self, db: Any, *, now: Any) -> None:
        super().__init__(db)
        self.now = now

    @staticmethod
    def _optional_text(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> Dict[str, Any]:
        position = int(row["position"] or 0)
        return {
            "id": int(row["id"]),
            "position": position,
            "plaza": position,
            "display_name": row["display_name"],
            "name": row["display_name"],
            "registered_at": row["registered_at"],
            "discord_id": row["discord_id"],
            "user_id": row["user_id"],
            "source": row["source"],
            "notes": row["notes"],
            "last_interest_confirmed_at": row["last_interest_confirmed_at"],
            "last_interest_prompted_at": row["last_interest_prompted_at"],
            "version": int(row["version"] or 1),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def token_digest(token: Any) -> str:
        text = str(token or "").strip()
        if not text:
            raise ValueError("waiting_list_invite_token_required")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _expires_at(timestamp: str, ttl_seconds: int) -> str:
        try:
            base = datetime.fromisoformat(str(timestamp or ""))
        except ValueError:
            base = datetime.now().astimezone()
        return (base + timedelta(seconds=max(60, int(ttl_seconds or 0)))).isoformat()

    @staticmethod
    def _row_to_invite(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": int(row["id"]),
            "discord_id": row["discord_id"],
            "discord_username": row["discord_username"],
            "status": row["status"],
            "expires_at": row["expires_at"],
            "accepted_at": row["accepted_at"],
            "declined_at": row["declined_at"],
            "consumed_at": row["consumed_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _raise_integrity_error(err: sqlite3.IntegrityError) -> None:
        message = str(err or "")
        if "waiting_list_entries.discord_id" in message:
            raise ValueError("waiting_list_discord_id_already_exists") from err
        if "waiting_list_entries.user_id" in message:
            raise ValueError("waiting_list_user_already_exists") from err
        raise ValueError("waiting_list_integrity_error") from err

    def _next_position_conn(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 AS next_position FROM waiting_list_entries").fetchone()
        return int((row or {})["next_position"] or 1)

    def _normalize_positions_conn(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT id FROM waiting_list_entries ORDER BY position ASC, id ASC").fetchall()
        for index, row in enumerate(rows, start=1):
            conn.execute("UPDATE waiting_list_entries SET position = ? WHERE id = ?", (index, int(row["id"])))

    def list(self) -> Dict[str, Any]:
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, position, display_name, registered_at, discord_id, user_id,
                       source, notes, last_interest_confirmed_at, last_interest_prompted_at,
                       version, created_at, updated_at
                FROM waiting_list_entries
                ORDER BY position ASC, id ASC
                """
            ).fetchall()
            entries = [self._row_to_entry(row) for row in rows]
        return {"entries": entries}

    def get(self, entry_id: Any) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(entry_id)
        if parsed_id is None:
            return None
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, position, display_name, registered_at, discord_id, user_id,
                       source, notes, last_interest_confirmed_at, last_interest_prompted_at,
                       version, created_at, updated_at
                FROM waiting_list_entries
                WHERE id = ?
                """,
                (parsed_id,),
            ).fetchone()
            return self._row_to_entry(row) if row else None

    def create(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.db.transaction("IMMEDIATE") as conn:
            timestamp = self.now()
            display_name = self._optional_text(payload.get("display_name") or payload.get("name"))
            if not display_name:
                raise ValueError("waiting_list_name_required")
            registered_at = self._optional_text(payload.get("registered_at")) or timestamp[:10]
            position = parse_int(payload.get("position") if "position" in payload else payload.get("plaza"))
            explicit_position = position is not None and position >= 1
            if position is None or position < 1:
                position = self._next_position_conn(conn)
            elif explicit_position:
                conn.execute(
                    "UPDATE waiting_list_entries SET position = position + 1 WHERE position >= ?",
                    (int(position),),
                )
            try:
                cur = conn.execute(
                    """
                    INSERT INTO waiting_list_entries (
                        position, display_name, registered_at, discord_id, user_id,
                        source, notes, last_interest_confirmed_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(position),
                        display_name,
                        registered_at,
                        self._optional_text(payload.get("discord_id")),
                        parse_int(payload.get("user_id")),
                        self._optional_text(payload.get("source")) or "manual",
                        self._optional_text(payload.get("notes")),
                        self._optional_text(payload.get("last_interest_confirmed_at")),
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as err:
                self._raise_integrity_error(err)
            entry_id = int(cur.lastrowid)
            self._normalize_positions_conn(conn)
            row = conn.execute(
                """
                SELECT id, position, display_name, registered_at, discord_id, user_id,
                       source, notes, last_interest_confirmed_at, last_interest_prompted_at,
                       version, created_at, updated_at
                FROM waiting_list_entries
                WHERE id = ?
                """,
                (entry_id,),
            ).fetchone()
            return self._row_to_entry(row)

    def update(self, entry_id: Any, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        parsed_id = parse_int(entry_id)
        if parsed_id is None:
            return None
        with self.db.transaction("IMMEDIATE") as conn:
            existing = conn.execute(
                "SELECT id, position FROM waiting_list_entries WHERE id = ?",
                (parsed_id,),
            ).fetchone()
            if not existing:
                return None
            fields: List[str] = []
            values: List[Any] = []
            field_map = {
                "position": parse_int(payload.get("position") if "position" in payload else payload.get("plaza")),
                "display_name": self._optional_text(payload.get("display_name") or payload.get("name")),
                "registered_at": self._optional_text(payload.get("registered_at")),
                "discord_id": self._optional_text(payload.get("discord_id")),
                "user_id": parse_int(payload.get("user_id")),
                "notes": self._optional_text(payload.get("notes")),
                "last_interest_confirmed_at": self._optional_text(payload.get("last_interest_confirmed_at")),
                "last_interest_prompted_at": self._optional_text(payload.get("last_interest_prompted_at")),
            }
            for key, value in field_map.items():
                if key in payload or (key == "position" and "plaza" in payload) or (key == "display_name" and "name" in payload):
                    if key == "display_name" and not value:
                        raise ValueError("waiting_list_name_required")
                    if key == "position" and (value is None or value < 1):
                        raise ValueError("invalid_waiting_list_position")
                    if key == "position":
                        old_position = int(existing["position"] or 0)
                        new_position = int(value)
                        if new_position < old_position:
                            conn.execute(
                                """
                                UPDATE waiting_list_entries
                                SET position = position + 1
                                WHERE id <> ? AND position >= ? AND position < ?
                                """,
                                (parsed_id, new_position, old_position),
                            )
                        elif new_position > old_position:
                            conn.execute(
                                """
                                UPDATE waiting_list_entries
                                SET position = position - 1
                                WHERE id <> ? AND position > ? AND position <= ?
                                """,
                                (parsed_id, old_position, new_position),
                            )
                    fields.append(f"{key} = ?")
                    values.append(value)
            if not fields:
                return self.get(parsed_id)
            timestamp = self.now()
            fields.extend(["version = version + 1", "updated_at = ?"])
            values.extend([timestamp, parsed_id])
            try:
                conn.execute(f"UPDATE waiting_list_entries SET {', '.join(fields)} WHERE id = ?", values)
            except sqlite3.IntegrityError as err:
                self._raise_integrity_error(err)
            if "position" in field_map and ("position" in payload or "plaza" in payload):
                self._normalize_positions_conn(conn)
            row = conn.execute(
                """
                SELECT id, position, display_name, registered_at, discord_id, user_id,
                       source, notes, last_interest_confirmed_at, last_interest_prompted_at,
                       version, created_at, updated_at
                FROM waiting_list_entries
                WHERE id = ?
                """,
                (parsed_id,),
            ).fetchone()
            return self._row_to_entry(row) if row else None

    def delete(self, entry_id: Any) -> bool:
        parsed_id = parse_int(entry_id)
        if parsed_id is None:
            return False
        with self.db.transaction("IMMEDIATE") as conn:
            cur = conn.execute("DELETE FROM waiting_list_entries WHERE id = ?", (parsed_id,))
            if cur.rowcount:
                self._normalize_positions_conn(conn)
            return cur.rowcount > 0

    def upsert_discord_signup(
        self,
        *,
        discord_id: Any,
        display_name: Any = None,
        user_id: Any = None,
    ) -> Dict[str, Any]:
        normalized_discord_id = self._optional_text(discord_id)
        if not normalized_discord_id:
            raise ValueError("discord_id_required")
        with self.db.transaction("IMMEDIATE") as conn:
            existing = conn.execute(
                "SELECT id FROM waiting_list_entries WHERE discord_id = ?",
                (normalized_discord_id,),
            ).fetchone()
            timestamp = self.now()
            if existing:
                entry_id = int(existing["id"])
                updates = ["last_interest_confirmed_at = ?", "updated_at = ?", "version = version + 1"]
                values: List[Any] = [timestamp, timestamp]
                name = self._optional_text(display_name)
                if name:
                    updates.append("display_name = ?")
                    values.append(name)
                parsed_user_id = parse_int(user_id)
                if parsed_user_id is not None:
                    updates.append("user_id = ?")
                    values.append(parsed_user_id)
                values.append(entry_id)
                try:
                    conn.execute(f"UPDATE waiting_list_entries SET {', '.join(updates)} WHERE id = ?", values)
                except sqlite3.IntegrityError as err:
                    self._raise_integrity_error(err)
            else:
                name = self._optional_text(display_name) or f"Discord {normalized_discord_id}"
                try:
                    cur = conn.execute(
                        """
                        INSERT INTO waiting_list_entries (
                            position, display_name, registered_at, discord_id, user_id,
                            source, last_interest_confirmed_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 'discord', ?, ?, ?)
                        """,
                        (
                            self._next_position_conn(conn),
                            name,
                            timestamp[:10],
                            normalized_discord_id,
                            parse_int(user_id),
                            timestamp,
                            timestamp,
                            timestamp,
                        ),
                    )
                except sqlite3.IntegrityError as err:
                    self._raise_integrity_error(err)
                entry_id = int(cur.lastrowid)
            self._normalize_positions_conn(conn)
            row = conn.execute(
                """
                SELECT id, position, display_name, registered_at, discord_id, user_id,
                       source, notes, last_interest_confirmed_at, last_interest_prompted_at,
                       version, created_at, updated_at
                FROM waiting_list_entries
                WHERE id = ?
                """,
                (entry_id,),
            ).fetchone()
            return self._row_to_entry(row)

    def create_invite(
        self,
        *,
        discord_id: Any,
        discord_username: Any = None,
        ttl_seconds: int = 604800,
    ) -> Dict[str, Any]:
        normalized_discord_id = self._optional_text(discord_id)
        if not normalized_discord_id:
            raise ValueError("discord_id_required")
        token = secrets.token_urlsafe(32)
        digest = self.token_digest(token)
        timestamp = self.now()
        expires_at = self._expires_at(timestamp, ttl_seconds)
        with self.db.transaction("IMMEDIATE") as conn:
            cur = conn.execute(
                """
                INSERT INTO waiting_list_invites (
                    token_digest, discord_id, discord_username, status,
                    expires_at, created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
                """,
                (
                    digest,
                    normalized_discord_id,
                    self._optional_text(discord_username),
                    expires_at,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                """
                SELECT id, discord_id, discord_username, status, expires_at,
                       accepted_at, declined_at, consumed_at, created_at, updated_at
                FROM waiting_list_invites
                WHERE id = ?
                """,
                (int(cur.lastrowid),),
            ).fetchone()
        return {"token": token, "invite": self._row_to_invite(row)}

    def invite_by_token(self, token: Any) -> Optional[Dict[str, Any]]:
        digest = self.token_digest(token)
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, discord_id, discord_username, status, expires_at,
                       accepted_at, declined_at, consumed_at, created_at, updated_at
                FROM waiting_list_invites
                WHERE token_digest = ?
                """,
                (digest,),
            ).fetchone()
        return self._row_to_invite(row) if row else None

    def mark_invite_accepted(self, token: Any) -> Optional[Dict[str, Any]]:
        digest = self.token_digest(token)
        timestamp = self.now()
        with self.db.transaction("IMMEDIATE") as conn:
            conn.execute(
                """
                UPDATE waiting_list_invites
                SET status = CASE WHEN status = 'pending' THEN 'accepted' ELSE status END,
                    accepted_at = COALESCE(accepted_at, ?),
                    updated_at = ?
                WHERE token_digest = ? AND status IN ('pending', 'accepted')
                """,
                (timestamp, timestamp, digest),
            )
            row = conn.execute(
                """
                SELECT id, discord_id, discord_username, status, expires_at,
                       accepted_at, declined_at, consumed_at, created_at, updated_at
                FROM waiting_list_invites
                WHERE token_digest = ?
                """,
                (digest,),
            ).fetchone()
        return self._row_to_invite(row) if row else None

    def mark_invite_declined(
        self,
        *,
        discord_id: Any,
        discord_username: Any = None,
    ) -> Dict[str, Any]:
        normalized_discord_id = self._optional_text(discord_id)
        if not normalized_discord_id:
            raise ValueError("discord_id_required")
        timestamp = self.now()
        with self.db.transaction("IMMEDIATE") as conn:
            cur = conn.execute(
                """
                INSERT INTO waiting_list_invites (
                    token_digest, discord_id, discord_username, status,
                    expires_at, declined_at, created_at, updated_at
                ) VALUES (?, ?, ?, 'declined', ?, ?, ?, ?)
                """,
                (
                    f"declined:{normalized_discord_id}:{secrets.token_urlsafe(16)}",
                    normalized_discord_id,
                    self._optional_text(discord_username),
                    timestamp,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                """
                SELECT id, discord_id, discord_username, status, expires_at,
                       accepted_at, declined_at, consumed_at, created_at, updated_at
                FROM waiting_list_invites
                WHERE id = ?
                """,
                (int(cur.lastrowid),),
            ).fetchone()
        return self._row_to_invite(row)

    def consume_invite_for_user(
        self,
        *,
        token: Any,
        user_id: Any,
        display_name: Any = None,
    ) -> Optional[Dict[str, Any]]:
        digest = self.token_digest(token)
        parsed_user_id = parse_int(user_id)
        if parsed_user_id is None:
            raise ValueError("user_id_required")
        timestamp = self.now()
        with self.db.transaction("IMMEDIATE") as conn:
            invite = conn.execute(
                """
                SELECT id, discord_id, discord_username, status, expires_at
                FROM waiting_list_invites
                WHERE token_digest = ?
                """,
                (digest,),
            ).fetchone()
            if not invite:
                return None
            if str(invite["status"] or "") not in {"pending", "accepted"}:
                return None
            if str(invite["expires_at"] or "") <= timestamp:
                conn.execute(
                    "UPDATE waiting_list_invites SET status = 'expired', updated_at = ? WHERE id = ?",
                    (timestamp, int(invite["id"])),
                )
                return None
            entry_name = (
                self._optional_text(display_name)
                or self._optional_text(invite["discord_username"])
                or f"Discord {invite['discord_id']}"
            )
            existing = conn.execute(
                """
                SELECT id FROM waiting_list_entries
                WHERE discord_id = ? OR user_id = ?
                ORDER BY id
                LIMIT 1
                """,
                (str(invite["discord_id"]), parsed_user_id),
            ).fetchone()
            if existing:
                entry_id = int(existing["id"])
                try:
                    conn.execute(
                        """
                        UPDATE waiting_list_entries
                        SET display_name = ?,
                            discord_id = ?,
                            user_id = ?,
                            last_interest_confirmed_at = ?,
                            updated_at = ?,
                            version = version + 1
                        WHERE id = ?
                        """,
                        (entry_name, str(invite["discord_id"]), parsed_user_id, timestamp, timestamp, entry_id),
                    )
                except sqlite3.IntegrityError as err:
                    self._raise_integrity_error(err)
            else:
                try:
                    cur = conn.execute(
                        """
                        INSERT INTO waiting_list_entries (
                            position, display_name, registered_at, discord_id, user_id,
                            source, last_interest_confirmed_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 'discord_invite', ?, ?, ?)
                        """,
                        (
                            self._next_position_conn(conn),
                            entry_name,
                            timestamp[:10],
                            str(invite["discord_id"]),
                            parsed_user_id,
                            timestamp,
                            timestamp,
                            timestamp,
                        ),
                    )
                except sqlite3.IntegrityError as err:
                    self._raise_integrity_error(err)
                entry_id = int(cur.lastrowid)
            conn.execute(
                """
                UPDATE waiting_list_invites
                SET status = 'consumed', consumed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (timestamp, timestamp, int(invite["id"])),
            )
            self._normalize_positions_conn(conn)
            row = conn.execute(
                """
                SELECT id, position, display_name, registered_at, discord_id, user_id,
                       source, notes, last_interest_confirmed_at, last_interest_prompted_at,
                       version, created_at, updated_at
                FROM waiting_list_entries
                WHERE id = ?
                """,
                (entry_id,),
            ).fetchone()
            return self._row_to_entry(row) if row else None
