"""DELETE route functions."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional
from urllib.parse import ParseResult

try:
    from ..routing import RouteResponse, error_response, json_response, prefix_route
except ImportError:  # pragma: no cover - supports direct script execution.
    from routing import RouteResponse, error_response, json_response, prefix_route


def _path_id(parsed: ParseResult) -> Optional[int]:
    try:
        return int(parsed.path.split("/")[-1])
    except ValueError:
        return None


def _delete_simple(
    handler: Any,
    parsed: ParseResult,
    *,
    policy: str,
    invalid_id_error: str,
    entity: str,
    delete: Callable[[int], bool],
) -> Optional[RouteResponse]:
    if not handler._authorize(policy):
        return
    entity_id = _path_id(parsed)
    if entity_id is None:
        return error_response(400, invalid_id_error)
    ok = delete(entity_id)
    if ok:
        handler._log_admin_action("delete", entity, str(entity_id))
    return json_response(200 if ok else 404, {"ok": ok})


def delete_free_agent(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    return _delete_simple(
        handler,
        parsed,
        policy="admin.free_agent.write",
        invalid_id_error="invalid_free_agent_id",
        entity="free_agent",
        delete=handler.app.free_agency.delete_free_agent,
    )


def delete_draft_order(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    return _delete_simple(
        handler,
        parsed,
        policy="admin.draft_order.write",
        invalid_id_error="invalid_draft_order_id",
        entity="draft_order",
        delete=handler.app.draft.delete_order_entry,
    )


def delete_player_transaction(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    return _delete_simple(
        handler,
        parsed,
        policy="admin.player_profile.write",
        invalid_id_error="invalid_transaction_id",
        entity="player_transaction",
        delete=handler.app.players.delete_transaction,
    )


def delete_salary_history(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    return _delete_simple(
        handler,
        parsed,
        policy="admin.player_profile.write",
        invalid_id_error="invalid_salary_history_id",
        entity="player_salary_history",
        delete=handler.app.players.delete_salary_history,
    )


def delete_player_profile(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    if not handler._authorize("admin.player_profile.write"):
        return
    profile_id = _path_id(parsed)
    if profile_id is None:
        return error_response(400, "invalid_profile_id")
    result = handler.app.player_identity.delete_profile(profile_id)
    if not result.get("ok"):
        return error_response(404, result.get("error") or "not_found")
    handler._log_admin_action(
        "delete",
        "player_profile",
        str(profile_id),
        details={"deleted": result.get("deleted") or {}},
        before=result.get("profile") or {},
        after=None,
    )
    return json_response(200, result)


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
) -> Optional[RouteResponse]:
    entity_id = _path_id(parsed)
    if entity_id is None:
        return error_response(400, invalid_id_error)
    before = get_record(entity_id)
    if not before:
        return error_response(404, missing_error)
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
    return json_response(200 if ok else 404, {"ok": ok})


def delete_player(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    return _delete_team_resource(
        handler,
        parsed,
        invalid_id_error="invalid_player_id",
        missing_error="player_not_found",
        policy="admin.player.remove",
        entity="player",
        get_record=handler.app.players.record,
        delete=handler.app.players.delete,
    )


def delete_asset(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    return _delete_team_resource(
        handler,
        parsed,
        invalid_id_error="invalid_asset_id",
        missing_error="asset_not_found",
        policy="admin.draft_asset.write",
        entity="asset",
        get_record=handler.app.assets.asset,
        delete=handler.app.assets.delete_asset,
    )


def delete_dead_contract(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> Optional[RouteResponse]:
    return _delete_team_resource(
        handler,
        parsed,
        invalid_id_error="invalid_dead_contract_id",
        missing_error="dead_contract_not_found",
        policy="admin.dead_contract.write",
        entity="dead_contract",
        get_record=handler.app.assets.dead_contract,
        delete=handler.app.assets.delete_dead_contract,
    )


DELETE_ROUTES = (
    prefix_route("/api/free-agents/", delete_free_agent, permission="admin.free_agent.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/draft-order/", delete_draft_order, permission="admin.draft_order.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/player-transactions/", delete_player_transaction, permission="admin.player_profile.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/player-salary-history/", delete_salary_history, permission="admin.player_profile.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/player-profiles/", delete_player_profile, permission="admin.player_profile.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/players/", delete_player, permission="admin.player.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/assets/", delete_asset, permission="admin.draft_asset.write", csrf=True, mutates_league_state=True),
    prefix_route("/api/dead-contracts/", delete_dead_contract, permission="admin.dead_contract.write", csrf=True, mutates_league_state=True),
)
