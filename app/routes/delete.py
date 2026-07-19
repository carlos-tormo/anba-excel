"""DELETE route functions."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..routing import prefix_route
except ImportError:  # pragma: no cover - supports direct script execution.
    from routing import prefix_route


def _path_id(handler: Any, parsed: ParseResult, error: str) -> Optional[int]:
    try:
        return int(parsed.path.split("/")[-1])
    except ValueError:
        handler._json(400, {"error": error})
        return None


def _delete_simple(
    handler: Any,
    parsed: ParseResult,
    *,
    policy: str,
    invalid_id_error: str,
    entity: str,
    delete: Callable[[int], bool],
) -> None:
    if not handler._authorize(policy):
        return
    entity_id = _path_id(handler, parsed, invalid_id_error)
    if entity_id is None:
        return
    ok = delete(entity_id)
    if ok:
        handler._log_admin_action("delete", entity, str(entity_id))
    handler._json(200 if ok else 404, {"ok": ok})


def delete_free_agent(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    _delete_simple(
        handler,
        parsed,
        policy="admin.free_agent.write",
        invalid_id_error="invalid_free_agent_id",
        entity="free_agent",
        delete=handler.db.delete_free_agent,
    )


def delete_draft_order(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    _delete_simple(
        handler,
        parsed,
        policy="admin.draft_order.write",
        invalid_id_error="invalid_draft_order_id",
        entity="draft_order",
        delete=handler._draft_service().delete_order_entry,
    )


def delete_player_transaction(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    _delete_simple(
        handler,
        parsed,
        policy="admin.player_profile.write",
        invalid_id_error="invalid_transaction_id",
        entity="player_transaction",
        delete=handler.db.delete_player_transaction,
    )


def delete_salary_history(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    _delete_simple(
        handler,
        parsed,
        policy="admin.player_profile.write",
        invalid_id_error="invalid_salary_history_id",
        entity="player_salary_history",
        delete=handler.db.delete_player_salary_history,
    )


def delete_player_profile(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    if not handler._authorize("admin.player_profile.write"):
        return
    profile_id = _path_id(handler, parsed, "invalid_profile_id")
    if profile_id is None:
        return
    result = handler._player_identity_service().delete_profile(profile_id)
    if not result.get("ok"):
        handler._json(404, {"error": result.get("error") or "not_found"})
        return
    handler._log_admin_action(
        "delete",
        "player_profile",
        str(profile_id),
        details={"deleted": result.get("deleted") or {}},
        before=result.get("profile") or {},
        after=None,
    )
    handler._json(200, result)


def _delete_team_resource(
    handler: Any,
    parsed: ParseResult,
    *,
    invalid_id_error: str,
    missing_error: str,
    policy: str,
    entity: str,
    get_record: Callable[[int], Optional[Dict[str, Any]]],
    delete: Callable[[int], bool],
) -> None:
    entity_id = _path_id(handler, parsed, invalid_id_error)
    if entity_id is None:
        return
    before = get_record(entity_id)
    if not before:
        handler._json(404, {"error": missing_error})
        return
    if not handler._authorize(policy, {"team_code": before.get("team_code")}):
        return
    ok = delete(entity_id)
    if ok:
        handler._log_admin_action(
            "delete",
            entity,
            str(entity_id),
            before.get("team_code"),
            before=before,
        )
    handler._json(200 if ok else 404, {"ok": ok})


def delete_player(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    _delete_team_resource(
        handler,
        parsed,
        invalid_id_error="invalid_player_id",
        missing_error="player_not_found",
        policy="admin.player.remove",
        entity="player",
        get_record=handler.db.get_player_record,
        delete=handler.db.delete_player,
    )


def delete_asset(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    _delete_team_resource(
        handler,
        parsed,
        invalid_id_error="invalid_asset_id",
        missing_error="asset_not_found",
        policy="admin.draft_asset.write",
        entity="asset",
        get_record=handler.db.get_asset_record,
        delete=handler.db.delete_asset,
    )


def delete_dead_contract(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    _delete_team_resource(
        handler,
        parsed,
        invalid_id_error="invalid_dead_contract_id",
        missing_error="dead_contract_not_found",
        policy="admin.dead_contract.write",
        entity="dead_contract",
        get_record=handler.db.get_dead_contract_record,
        delete=handler.db.delete_dead_contract,
    )


DELETE_ROUTES = (
    prefix_route("/api/free-agents/", delete_free_agent),
    prefix_route("/api/draft-order/", delete_draft_order),
    prefix_route("/api/player-transactions/", delete_player_transaction),
    prefix_route("/api/player-salary-history/", delete_salary_history),
    prefix_route("/api/player-profiles/", delete_player_profile),
    prefix_route("/api/players/", delete_player),
    prefix_route("/api/assets/", delete_asset),
    prefix_route("/api/dead-contracts/", delete_dead_contract),
)
