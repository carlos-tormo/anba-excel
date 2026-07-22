"""Framework-neutral route dispatch and request validation."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence
from urllib.parse import ParseResult

try:
    from .domain_rules import parse_float, parse_int
except ImportError:  # pragma: no cover - supports direct script execution.
    from domain_rules import parse_float, parse_int


class RequestValidationError(ValueError):
    def __init__(self, error: str, **details: Any):
        super().__init__(error)
        self.error = error
        self.details = details

    def response_payload(self) -> Dict[str, Any]:
        return {"error": self.error, **self.details}


@dataclass(frozen=True)
class RouteResponse:
    status: int
    payload: Any = None
    headers: Dict[str, Any] = field(default_factory=dict)
    content_type: str = "application/json; charset=utf-8"
    body: Optional[bytes] = None


def json_response(status: int, payload: Any, headers: Optional[Dict[str, Any]] = None) -> RouteResponse:
    return RouteResponse(status=status, payload=payload, headers=dict(headers or {}))


def bytes_response(
    status: int,
    body: bytes,
    content_type: str,
    headers: Optional[Dict[str, Any]] = None,
) -> RouteResponse:
    return RouteResponse(status=status, body=body, content_type=content_type, headers=dict(headers or {}))


def redirect_response(
    location: str,
    *,
    status: int = 302,
    headers: Optional[Dict[str, Any]] = None,
) -> RouteResponse:
    response_headers: Dict[str, Any] = {"Location": str(location)}
    response_headers.update(dict(headers or {}))
    return RouteResponse(
        status=status,
        body=b"",
        content_type="text/plain; charset=utf-8",
        headers=response_headers,
    )


def error_response(status: int, error: str, **details: Any) -> RouteResponse:
    return json_response(status, {"error": error, **details})


def response_from_exception(exc: Exception) -> RouteResponse:
    if isinstance(exc, RequestValidationError):
        return json_response(400, exc.response_payload())
    if isinstance(exc, ValueError):
        error = str(exc) or "invalid_request"
        return error_response(413 if error == "request_too_large" else 400, error)
    return error_response(500, "internal_error")


RouteHandler = Callable[[Any, ParseResult, Optional[Dict[str, Any]]], Optional[RouteResponse]]
PathMatcher = Callable[[str], bool]


@dataclass(frozen=True)
class Route:
    name: str
    matches: PathMatcher
    handler: RouteHandler
    method: Optional[str] = None
    path: Optional[str] = None
    permission: Optional[str] = None
    csrf: bool = False
    mutates_league_state: bool = False
    auth_exempt_reason: Optional[str] = None


def route_with_method(route: Route, method: str) -> Route:
    return replace(route, method=str(method or "").upper())


def exact_route(
    path: str,
    handler: RouteHandler,
    *,
    name: Optional[str] = None,
    permission: Optional[str] = None,
    csrf: bool = False,
    mutates_league_state: bool = False,
    auth_exempt_reason: Optional[str] = None,
) -> Route:
    return Route(
        name or f"exact:{path}",
        lambda candidate: candidate == path,
        handler,
        path=path,
        permission=permission,
        csrf=csrf,
        mutates_league_state=mutates_league_state,
        auth_exempt_reason=auth_exempt_reason,
    )


def prefix_route(
    prefix: str,
    handler: RouteHandler,
    *,
    name: Optional[str] = None,
    permission: Optional[str] = None,
    csrf: bool = False,
    mutates_league_state: bool = False,
    auth_exempt_reason: Optional[str] = None,
) -> Route:
    return Route(
        name or f"prefix:{prefix}",
        lambda candidate: candidate.startswith(prefix),
        handler,
        path=prefix,
        permission=permission,
        csrf=csrf,
        mutates_league_state=mutates_league_state,
        auth_exempt_reason=auth_exempt_reason,
    )


def predicate_route(
    name: str,
    matches: PathMatcher,
    handler: RouteHandler,
    *,
    path: Optional[str] = None,
    permission: Optional[str] = None,
    csrf: bool = False,
    mutates_league_state: bool = False,
    auth_exempt_reason: Optional[str] = None,
) -> Route:
    """Register a route whose path shape is more specific than a plain prefix."""
    return Route(
        name,
        matches,
        handler,
        path=path or name,
        permission=permission,
        csrf=csrf,
        mutates_league_state=mutates_league_state,
        auth_exempt_reason=auth_exempt_reason,
    )


def dispatch_routes(
    request_handler: Any,
    parsed: ParseResult,
    routes: Sequence[Route],
    payload: Optional[Dict[str, Any]] = None,
) -> bool:
    for route in routes:
        if route.matches(parsed.path):
            try:
                setattr(request_handler, "_current_route_name", route.name)
            except Exception:
                pass
            result = route.handler(request_handler, parsed, payload)
            if isinstance(result, RouteResponse):
                responder = getattr(request_handler, "_send_route_response", None)
                if callable(responder):
                    responder(result)
                else:
                    if result.body is not None:
                        byte_responder = getattr(request_handler, "_bytes_response", None)
                        if callable(byte_responder):
                            byte_responder(result.status, result.body, result.content_type, result.headers)
                        else:
                            request_handler._json(result.status, result.payload, result.headers)
                    elif result.headers:
                        request_handler._json(result.status, result.payload, result.headers)
                    else:
                        request_handler._json(result.status, result.payload)
            return True
    return False


def validate_json_structure(
    payload: Any,
    *,
    max_depth: int,
    max_container_items: int,
    max_object_fields: int,
    max_total_nodes: int,
    max_key_length: int,
) -> None:
    """Bound decoded JSON complexity before route-specific validation runs."""
    node_count = 0
    stack = [(payload, 1)]
    while stack:
        value, depth = stack.pop()
        node_count += 1
        if node_count > max_total_nodes:
            raise RequestValidationError("payload_too_complex")
        if depth > max_depth:
            raise RequestValidationError("payload_too_deep")
        if isinstance(value, dict):
            if len(value) > max_object_fields:
                raise RequestValidationError("object_too_large")
            for key, child in value.items():
                if not isinstance(key, str) or len(key) > max_key_length:
                    raise RequestValidationError("invalid_json_key")
                stack.append((child, depth + 1))
        elif isinstance(value, list):
            if len(value) > max_container_items:
                raise RequestValidationError("list_too_large")
            stack.extend((child, depth + 1) for child in value)


def validate_payload_fields(
    payload: Dict[str, Any],
    allowed_fields: Iterable[str],
    *,
    required_fields: Iterable[str] = (),
) -> None:
    allowed = set(allowed_fields)
    required = set(required_fields)
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise RequestValidationError("unknown_fields", fields=unknown)
    missing = sorted(field for field in required if field not in payload)
    if missing:
        raise RequestValidationError("missing_fields", fields=missing)


def validate_unique_integer_ids(values: Any, *, field: str, max_items: int = 1_000) -> List[int]:
    if not isinstance(values, list):
        raise RequestValidationError("invalid_list", field=field)
    if len(values) > max_items:
        raise RequestValidationError("list_too_large", field=field, max_items=max_items)
    parsed: List[int] = []
    seen = set()
    for value in values:
        item = parse_int(value)
        if item is None or item <= 0:
            raise RequestValidationError("invalid_id", field=field)
        if item in seen:
            raise RequestValidationError("duplicate_ids", field=field, id=item)
        seen.add(item)
        parsed.append(item)
    return parsed


def validate_text_field(
    payload: Dict[str, Any],
    field: str,
    *,
    max_length: int,
    required: bool = False,
) -> None:
    if field not in payload:
        if required:
            raise RequestValidationError("missing_fields", fields=[field])
        return
    value = payload.get(field)
    if value is None and not required:
        return
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise RequestValidationError("invalid_field", field=field)
    text = str(value).strip()
    if required and not text:
        raise RequestValidationError("invalid_field", field=field)
    if len(text) > max_length:
        raise RequestValidationError("field_too_long", field=field, max_length=max_length)


def validate_integer_range(payload: Dict[str, Any], field: str, *, minimum: int, maximum: int) -> None:
    if field not in payload or payload.get(field) in (None, ""):
        return
    parsed = parse_int(payload.get(field))
    if parsed is None or parsed < minimum or parsed > maximum:
        raise RequestValidationError(
            "invalid_integer_range",
            field=field,
            minimum=minimum,
            maximum=maximum,
        )


def validate_number_range(
    payload: Dict[str, Any],
    field: str,
    *,
    minimum: float,
    maximum: float,
    required: bool = False,
) -> None:
    if field not in payload or payload.get(field) in (None, ""):
        if required:
            raise RequestValidationError("missing_fields", fields=[field])
        return
    value = payload.get(field)
    if isinstance(value, bool):
        raise RequestValidationError("invalid_number_range", field=field, minimum=minimum, maximum=maximum)
    parsed = parse_float(value)
    if parsed is None or not math.isfinite(parsed) or parsed < minimum or parsed > maximum:
        raise RequestValidationError("invalid_number_range", field=field, minimum=minimum, maximum=maximum)


def validate_boolean_field(payload: Dict[str, Any], field: str) -> None:
    if field in payload and not isinstance(payload.get(field), bool):
        raise RequestValidationError("invalid_boolean", field=field)


def validate_team_code_field(payload: Dict[str, Any], field: str = "team_code") -> None:
    if field not in payload or payload.get(field) in (None, ""):
        return
    value = payload.get(field)
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{3}", value.strip()):
        raise RequestValidationError("invalid_team_code", field=field)
