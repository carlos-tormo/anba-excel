"""Press publication and user-notification HTTP routes."""

from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import ParseResult, parse_qs

try:
    from ..domain_rules import parse_int
    from ..routing import exact_route, predicate_route
except ImportError:  # pragma: no cover
    from domain_rules import parse_int
    from routing import exact_route, predicate_route


ARTICLE_IMAGE_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def list_notifications(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    if not handler._authorize("notifications.view"):
        return
    session = handler._current_session() or {}
    if str(session.get("role") or "").strip().lower() not in {"gm", "co_admin"}:
        handler._json(200, {"notifications": []})
        return
    query = parse_qs(parsed.query)
    unread_raw = str((query.get("unread") or ["1"])[0] or "").strip().lower()
    limit = parse_int((query.get("limit") or ["20"])[0]) or 20
    notifications = handler.db.list_user_notifications_for_session(
        session, unread_only=unread_raw not in {"0", "false", "no"}, limit=limit
    )
    handler._json(200, {"notifications": notifications})


def _article_path(path: str) -> bool:
    parts = path.strip("/").split("/")
    return len(parts) in {4, 5} and parts[:3] == ["api", "news", "articles"]


def get_article(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    parts = parsed.path.strip("/").split("/")
    article_id = parse_int(parts[3])
    if article_id is None:
        handler._json(400, {"error": "invalid_article_id"})
        return
    if len(parts) == 5 and parts[4] == "image":
        image = handler.db.get_press_article_image(article_id)
        if not image:
            handler._json(404, {"error": "not_found"})
            return
        image_bytes, mime_type = image
        extension = ARTICLE_IMAGE_EXTENSIONS.get(mime_type, "img")
        handler._bytes_response(200, image_bytes, mime_type, headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Disposition": f'inline; filename="anba-article-{article_id}.{extension}"',
            "X-Content-Type-Options": "nosniff",
        })
        return
    if len(parts) == 5:
        handler._json(404, {"error": "not_found"})
        return
    article = handler.db.get_press_article(article_id)
    if not article:
        handler._json(404, {"error": "article_not_found"})
        return
    handler._json(200, {"article": article})


def _notification_read_path(path: str) -> bool:
    parts = path.strip("/").split("/")
    return len(parts) == 5 and parts[:3] == ["api", "me", "notifications"] and parts[4] == "read"


def mark_notification_read(handler: Any, parsed: ParseResult, _payload: Optional[Dict[str, Any]]) -> None:
    if not handler._authorize("notifications.read") or not handler._require_csrf():
        return
    try:
        notification_id = int(parsed.path.strip("/").split("/")[3])
    except ValueError:
        handler._json(400, {"error": "invalid_notification_id"})
        return
    if not handler.db.mark_user_notification_read(notification_id, handler._current_session() or {}):
        handler._json(404, {"error": "notification_not_found"})
        return
    handler._json(200, {"ok": True})


def publish_article(handler: Any, _parsed: ParseResult, payload: Optional[Dict[str, Any]]) -> None:
    payload = payload or {}
    if not handler._require_csrf() or not handler._require_sensitive_rate_limit("admin_post"):
        return
    if not handler._authorize("admin.article.write"):
        return
    article_text = str(payload.get("text") or payload.get("article_text") or "").strip()
    try:
        image_attachment = handler._discord_custom_image_attachment(payload.get("discord_custom_image"))
        if not image_attachment:
            raise ValueError("article_image_required")
        file_bytes, _filename, mime_type = image_attachment
        article = handler.db.create_press_article(article_text, file_bytes, mime_type, handler._current_session() or {})
        article_id = int(article.get("id") or 0)
        result = handler._post_press_article(article_text, handler._public_url(f"/news?article={article_id}"), image_attachment)
        handler.db.update_press_article_discord(article_id, str(result.get("channel_id") or ""), str(result.get("message_id") or ""))
    except ValueError as err:
        handler._json(400, {"error": str(err) or "invalid_article"})
        return
    except RuntimeError as err:
        handler._json(503, {"error": str(err) or "discord_not_configured"})
        return
    except HTTPError as err:
        detail = handler._http_error_excerpt(err)
        handler.log_error("Discord press article failed: %s", detail)
        handler._json(502, {"error": "discord_post_failed", "detail": detail})
        return
    except (URLError, TimeoutError, OSError) as err:
        detail = str(err)
        handler.log_error("Discord press article failed: %s", detail)
        handler._json(502, {"error": "discord_post_failed", "detail": detail})
        return
    handler._log_admin_action("launch", "press_article", result.get("message_id") or "discord", None, {
        "channel_id": result.get("channel_id"), "message_id": result.get("message_id"),
        "article_url": result.get("article_url"), "text_length": len(article_text), "has_image": True,
    })
    handler._json(200, {"ok": True, **result})


PRESS_GET_ROUTES = (
    exact_route("/api/me/notifications", list_notifications),
    predicate_route("press-article", _article_path, get_article),
)
PRESS_POST_ROUTES = (
    predicate_route("notification-read", _notification_read_path, mark_notification_read),
    exact_route("/api/admin/launch-article", publish_article),
)

