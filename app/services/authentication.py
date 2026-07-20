"""Authentication workflows built on OAuth transport and user persistence."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterable, Mapping
from urllib.error import HTTPError, URLError

try:
    from ..auth.policies import normalize_team_codes
    from ..domain_rules import parse_bool
except ImportError:  # pragma: no cover
    from auth.policies import normalize_team_codes
    from domain_rules import parse_bool


class GoogleOAuthCompletionError(ValueError):
    """Expected failure while completing a Google OAuth callback."""


class GoogleOAuthService:
    def __init__(
        self,
        integration: Any,
        users: Any,
        *,
        admin_emails: Iterable[str],
        gm_accounts: Mapping[str, Iterable[str]],
        now: Callable[[], str],
    ) -> None:
        self.integration = integration
        self.users = users
        self.admin_emails = {str(email).strip().lower() for email in admin_emails}
        self.gm_accounts = {
            str(email).strip().lower(): normalize_team_codes(team_codes)
            for email, team_codes in gm_accounts.items()
        }
        self.now = now

    def _role_for_email(self, email: str) -> tuple[str, list[str]]:
        if email in self.admin_emails:
            return "admin", []
        access = self.users.access_for_email(email)
        team_codes = normalize_team_codes(access.get("team_codes"))
        if parse_bool(access.get("is_co_admin")):
            return "co_admin", team_codes
        if team_codes:
            return "gm", team_codes
        configured_codes = self.gm_accounts.get(email, [])
        return ("gm", configured_codes) if configured_codes else ("guest", [])

    def complete(self, code: str) -> Dict[str, Any]:
        try:
            token_data = self.integration.exchange_code(code)
            access_token = token_data.get("access_token")
            if not access_token:
                raise GoogleOAuthCompletionError("google_token_failed")
            userinfo = self.integration.fetch_userinfo(access_token)
        except GoogleOAuthCompletionError:
            raise
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as err:
            raise GoogleOAuthCompletionError("google_exchange_failed") from err

        google_sub = str(userinfo.get("sub") or "").strip()
        email = str(userinfo.get("email") or "").strip().lower()
        if not google_sub or not email:
            raise GoogleOAuthCompletionError("google_profile_invalid")
        name = str(userinfo.get("name") or "").strip() or None
        picture = str(userinfo.get("picture") or "").strip() or None
        user = self.users.upsert_google_user(google_sub, email, name, picture)
        role, team_codes = self._role_for_email(email)
        return {
            "role": role,
            "team_codes": team_codes,
            "session": {
                "provider": "google",
                "user_id": user["id"],
                "email": email,
                "name": user.get("display_name") or email,
                "role": role,
                "team_codes": team_codes,
                "team_code": team_codes[0] if team_codes else None,
                "logged_in_at": self.now(),
            },
        }
