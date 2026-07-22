"""Press publication and user-notification HTTP routes."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import ParseResult, parse_qs

try:
    from ..domain_rules import parse_int
    from ..routing import bytes_response, error_response, exact_route, json_response, predicate_route
except ImportError:  # pragma: no cover
    from domain_rules import parse_int
    from routing import bytes_response, error_response, exact_route, json_response, predicate_route


ARTICLE_IMAGE_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def list_notifications(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    if not handler._authorize("notifications.view"):
        return
    session = handler._current_session() or {}
    if str(session.get("role") or "").strip().lower() not in {"gm", "co_admin"}:
        return json_response(200, {"notifications": []})
    query = parse_qs(parsed.query)
    unread_raw = str((query.get("unread") or ["1"])[0] or "").strip().lower()
    limit = parse_int((query.get("limit") or ["20"])[0]) or 20
    notifications = handler.app.user_notifications.list_for_session(
        session, unread_only=unread_raw not in {"0", "false", "no"}, limit=limit
    )
    return json_response(200, {"notifications": notifications})


def _article_path(path: str) -> bool:
    parts = path.strip("/").split("/")
    return len(parts) in {4, 5} and parts[:3] == ["api", "news", "articles"]


def get_article(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    parts = parsed.path.strip("/").split("/")
    article_id = parse_int(parts[3])
    if article_id is None:
        return error_response(400, "invalid_article_id")
    if len(parts) == 5 and parts[4] == "image":
        image = handler.app.press_articles.image(article_id)
        if not image:
            return error_response(404, "not_found")
        image_bytes, mime_type = image
        extension = ARTICLE_IMAGE_EXTENSIONS.get(mime_type, "img")
        return bytes_response(
            200,
            image_bytes,
            mime_type,
            headers={
                "Cache-Control": "public, max-age=31536000, immutable",
                "Content-Disposition": f'inline; filename="anba-article-{article_id}.{extension}"',
                "X-Content-Type-Options": "nosniff",
            },
        )
    if len(parts) == 5:
        return error_response(404, "not_found")
    article = handler.app.press_articles.get(article_id)
    if not article:
        return error_response(404, "article_not_found")
    return json_response(200, {"article": article})


def _notification_read_path(path: str) -> bool:
    parts = path.strip("/").split("/")
    return len(parts) == 5 and parts[:3] == ["api", "me", "notifications"] and parts[4] == "read"


def mark_notification_read(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]):
    if not handler._authorize("notifications.read") or not handler._require_csrf():
        return
    try:
        notification_id = int(parsed.path.strip("/").split("/")[3])
    except ValueError:
        return error_response(400, "invalid_notification_id")
    if not handler.app.user_notifications.mark_read(notification_id, handler._current_session() or {}):
        return error_response(404, "notification_not_found")
    return json_response(200, {"ok": True})


def publish_article(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]):
    payload = payload or {}
    if not handler._require_csrf() or not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.article.write"):
        return
    article_text = str(payload.get("text") or payload.get("article_text") or "").strip()
    try:
        result = handler.app.press_publication.publish(
            article_text,
            lambda article_id: handler._public_url(f"/news?article={article_id}"),
            payload.get("discord_custom_image"),
            handler._current_session() or {},
        )
    except ValueError as err:
        return error_response(400, str(err) or "invalid_article")
    except RuntimeError as err:
        return error_response(503, str(err) or "discord_not_configured")
    except HTTPError as err:
        detail = handler._http_error_excerpt(err)
        handler.log_error("Discord press article failed: %s", detail)
        return error_response(502, "discord_post_failed", detail=detail)
    except (URLError, TimeoutError, OSError) as err:
        detail = str(err)
        handler.log_error("Discord press article failed: %s", detail)
        return error_response(502, "discord_post_failed", detail=detail)
    article_id = result.get("article_id") or result.get("id")
    entity_id = str(article_id or result.get("message_id") or "discord")
    details = {
        "channel_id": result.get("channel_id"), "message_id": result.get("message_id"),
        "article_url": result.get("article_url"), "text_length": len(article_text), "has_image": True,
    }
    integration_outbox_ids = [str(result.get("outbox_event_id"))] if result.get("outbox_event_id") else []
    handler._log_admin_action(
        "launch",
        "press_article",
        entity_id,
        None,
        details,
        command_id=f"press-article:{entity_id}:launch",
        validation_result="valid",
        entity_versions={
            "article_id": article_id,
            "channel_id": result.get("channel_id"),
            "message_id": result.get("message_id"),
            "article_url": result.get("article_url"),
            "text_length": len(article_text),
            "has_image": True,
        },
        integration_outbox_ids=integration_outbox_ids,
    )
    return json_response(200, {"ok": True, **result})


PRESS_GET_ROUTES = (
    exact_route("/api/me/notifications", list_notifications),
    predicate_route("press-article", _article_path, get_article),
)
PRESS_POST_ROUTES = (
    predicate_route("notification-read", _notification_read_path, mark_notification_read, permission="notifications.read", csrf=True, mutates_league_state=True),
    exact_route("/api/admin/launch-article", publish_article, permission="admin.article.write", csrf=True, mutates_league_state=True),
)
