"""Draft application service.

HTTP adapters remain responsible for authentication, authorization, status-code
mapping, audit emission, and notification delivery. This service coordinates
draft order management, live-draft operations, and GM pick decisions.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from ..db.repositories.draft import DraftRepository
except ImportError:  # pragma: no cover - supports direct script execution.
    from db.repositories.draft import DraftRepository


class DraftService:
    def __init__(self, db: Any) -> None:
        if isinstance(db, DraftRepository):
            self.repository = db
        else:
            self.repository = getattr(db, "_draft_repository", None) or DraftRepository(db)

    def current_year(self) -> int:
        return int(self.repository.current_year())

    def list_order(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        return self.repository.list_order(draft_year)

    def list_pick_ledger(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        return self.repository.list_pick_ledger(draft_year)

    def order_entry(self, draft_order_id: int) -> Optional[Dict[str, Any]]:
        return self.repository.order_entry(int(draft_order_id))

    def create_order_entry(self, payload: Dict[str, Any]) -> int:
        return int(self.repository.create_order_entry(payload))

    def update_order_entry(self, draft_order_id: int, payload: Dict[str, Any]) -> bool:
        return bool(self.repository.update_order_entry(int(draft_order_id), payload))

    def delete_order_entry(self, draft_order_id: int) -> bool:
        return bool(self.repository.delete_order_entry(int(draft_order_id)))

    def list_live(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        return self.repository.list_live(draft_year)

    def update_live_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.repository.update_live_settings(payload)

    def control_live(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.repository.control_live(payload)

    def process_results(self, draft_year: Optional[int] = None) -> Dict[str, Any]:
        return self.repository.process_results(draft_year)

    def submit_pick(
        self,
        draft_order_id: int,
        payload: Dict[str, Any],
        actor: Dict[str, Any],
        *,
        is_admin: bool,
        pick: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        draft_pick = pick or self.order_entry(draft_order_id)
        if not draft_pick:
            raise ValueError("draft_pick_not_found")

        if is_admin:
            live = self.repository.submit_live_pick(
                int(draft_order_id), payload, actor or {}, is_admin=True
            )
            return {
                "pick": draft_pick,
                "request": None,
                "draft_live": live,
                "submitted_for_review": False,
            }

        request = self.repository.create_pick_request(
            int(draft_order_id), payload, actor or {}
        )
        if not request:
            raise ValueError("draft_pick_not_found")
        live = self.list_live(self._optional_int(draft_pick.get("draft_year")))
        live["request"] = request
        return {
            "pick": draft_pick,
            "request": request,
            "draft_live": live,
            "submitted_for_review": True,
        }

    def pick_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        return self.repository.pick_request(int(request_id))

    def decide_pick_request(
        self,
        request_id: int,
        decision: str,
        actor: Dict[str, Any],
        *,
        note: Optional[str] = None,
        request: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"approved", "rejected"}:
            raise ValueError("invalid_decision")
        request_before = request or self.pick_request(request_id)
        if not request_before:
            raise ValueError("request_not_found")
        if str(request_before.get("status") or "").strip().lower() != "pending":
            raise ValueError("request_already_decided")

        normalized_note = str(note or "").strip() or None
        if normalized_decision == "rejected":
            updated = self.repository.mark_pick_request_decided(
                int(request_id), "rejected", actor or {}, normalized_note
            )
            if not updated:
                raise ValueError("request_already_decided")
            return {
                "decision": normalized_decision,
                "request_before": request_before,
                "request": updated,
                "draft_live": None,
            }

        requester = {
            "email": request_before.get("requester_email"),
            "name": request_before.get("requester_name"),
            "role": "gm",
        }
        self.repository.submit_live_pick(
            int(request_before.get("draft_order_id")),
            {
                "option_value": request_before.get("option_value") or "__other__",
                "custom_text": (
                    request_before.get("custom_text")
                    or request_before.get("selection_text")
                    or ""
                ),
                "advance": True,
            },
            requester,
            is_admin=True,
        )
        updated = self.repository.mark_pick_request_decided(
            int(request_id), "approved", actor or {}, normalized_note
        )
        if not updated:
            raise ValueError("request_already_decided")
        live = self.list_live(self._optional_int(request_before.get("draft_year")))
        return {
            "decision": normalized_decision,
            "request_before": request_before,
            "request": updated,
            "draft_live": live,
        }

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        try:
            return int(value) if value is not None and str(value).strip() else None
        except (TypeError, ValueError):
            return None
