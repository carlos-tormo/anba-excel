"""HTTP route functions extracted from the server request handler."""

try:
    from .admin_data import ADMIN_DATA_GET_ROUTES, ADMIN_DATA_POST_ROUTES
    from .delete import DELETE_ROUTES as BASE_DELETE_ROUTES
    from .free_agency import FREE_AGENCY_GET_ROUTES, FREE_AGENCY_PATCH_ROUTES, FREE_AGENCY_POST_ROUTES
    from .get import GET_ROUTES as BASE_GET_ROUTES
    from .get_remaining import GET_REMAINING_ROUTES
    from .gm_office import GM_OFFICE_GET_ROUTES, GM_OFFICE_POST_ROUTES
    from .owner_office import (
        OWNER_OFFICE_GET_ROUTES,
        OWNER_OFFICE_MULTIPART_POST_ROUTES,
        OWNER_OFFICE_PATCH_ROUTES,
        OWNER_OFFICE_POST_ROUTES,
    )
    from .players import PLAYER_POST_ROUTES
    from .press import PRESS_GET_ROUTES, PRESS_POST_ROUTES
    from .patch import PATCH_ROUTES as BASE_PATCH_ROUTES
    from .patch_remaining import PATCH_REMAINING_ROUTES
    from .post import POST_ROUTES as BASE_POST_ROUTES
    from .post_remaining import EARLY_POST_ROUTES as BASE_EARLY_POST_ROUTES, POST_REMAINING_ROUTES
    from .trade_archive import (
        TRADE_ARCHIVE_DELETE_ROUTES,
        TRADE_ARCHIVE_GET_ROUTES,
        TRADE_ARCHIVE_PATCH_ROUTES,
        TRADE_ARCHIVE_POST_ROUTES,
    )
    from ..routing import route_with_method
except ImportError:  # pragma: no cover - supports direct script execution via app/server.py.
    from routes.admin_data import ADMIN_DATA_GET_ROUTES, ADMIN_DATA_POST_ROUTES
    from routes.delete import DELETE_ROUTES as BASE_DELETE_ROUTES
    from routes.free_agency import FREE_AGENCY_GET_ROUTES, FREE_AGENCY_PATCH_ROUTES, FREE_AGENCY_POST_ROUTES
    from routes.get import GET_ROUTES as BASE_GET_ROUTES
    from routes.get_remaining import GET_REMAINING_ROUTES
    from routes.gm_office import GM_OFFICE_GET_ROUTES, GM_OFFICE_POST_ROUTES
    from routes.owner_office import (
        OWNER_OFFICE_GET_ROUTES,
        OWNER_OFFICE_MULTIPART_POST_ROUTES,
        OWNER_OFFICE_PATCH_ROUTES,
        OWNER_OFFICE_POST_ROUTES,
    )
    from routes.players import PLAYER_POST_ROUTES
    from routes.press import PRESS_GET_ROUTES, PRESS_POST_ROUTES
    from routes.patch import PATCH_ROUTES as BASE_PATCH_ROUTES
    from routes.patch_remaining import PATCH_REMAINING_ROUTES
    from routes.post import POST_ROUTES as BASE_POST_ROUTES
    from routes.post_remaining import EARLY_POST_ROUTES as BASE_EARLY_POST_ROUTES, POST_REMAINING_ROUTES
    from routes.trade_archive import (
        TRADE_ARCHIVE_DELETE_ROUTES,
        TRADE_ARCHIVE_GET_ROUTES,
        TRADE_ARCHIVE_PATCH_ROUTES,
        TRADE_ARCHIVE_POST_ROUTES,
    )
    from routing import route_with_method

GET_ROUTES = tuple(route_with_method(route, "GET") for route in (
    *BASE_GET_ROUTES,
    *FREE_AGENCY_GET_ROUTES,
    *OWNER_OFFICE_GET_ROUTES,
    *GM_OFFICE_GET_ROUTES,
    *PRESS_GET_ROUTES,
    *ADMIN_DATA_GET_ROUTES,
    *TRADE_ARCHIVE_GET_ROUTES,
    *GET_REMAINING_ROUTES,
))
POST_ROUTES = tuple(route_with_method(route, "POST") for route in (
    *BASE_POST_ROUTES,
    *FREE_AGENCY_POST_ROUTES,
    *OWNER_OFFICE_POST_ROUTES,
    *GM_OFFICE_POST_ROUTES,
    *PLAYER_POST_ROUTES,
    *PRESS_POST_ROUTES,
    *ADMIN_DATA_POST_ROUTES,
    *TRADE_ARCHIVE_POST_ROUTES,
    *POST_REMAINING_ROUTES,
))
PATCH_ROUTES = tuple(route_with_method(route, "PATCH") for route in (
    *BASE_PATCH_ROUTES,
    *FREE_AGENCY_PATCH_ROUTES,
    *OWNER_OFFICE_PATCH_ROUTES,
    *TRADE_ARCHIVE_PATCH_ROUTES,
    *PATCH_REMAINING_ROUTES,
))
DELETE_ROUTES = tuple(route_with_method(route, "DELETE") for route in (
    *BASE_DELETE_ROUTES,
    *TRADE_ARCHIVE_DELETE_ROUTES,
))
EARLY_POST_ROUTES = tuple(route_with_method(route, "POST") for route in BASE_EARLY_POST_ROUTES)
OWNER_OFFICE_MULTIPART_POST_ROUTES = tuple(
    route_with_method(route, "POST") for route in OWNER_OFFICE_MULTIPART_POST_ROUTES
)

__all__ = [
    "DELETE_ROUTES",
    "EARLY_POST_ROUTES",
    "GET_ROUTES",
    "OWNER_OFFICE_MULTIPART_POST_ROUTES",
    "PATCH_ROUTES",
    "POST_ROUTES",
]
