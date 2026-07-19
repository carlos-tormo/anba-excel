"""Google OAuth 2.0 HTTP transport."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict
from urllib.parse import urlencode
from urllib.request import Request, urlopen


UrlOpener = Callable[..., Any]


@dataclass(frozen=True)
class GoogleOAuthConfig:
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    timeout_seconds: int = 15
    authorization_url: str = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url: str = "https://oauth2.googleapis.com/token"
    userinfo_url: str = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleOAuthIntegration:
    def __init__(self, config: GoogleOAuthConfig, *, opener: UrlOpener = urlopen):
        self.config = config
        self._open = opener

    def enabled(self) -> bool:
        return bool(self.config.client_id and self.config.client_secret and self.config.redirect_uri)

    def authorization_url(self, state: str) -> str:
        params = urlencode(
            {
                "client_id": self.config.client_id,
                "redirect_uri": self.config.redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "prompt": "select_account",
            }
        )
        return f"{self.config.authorization_url}?{params}"

    def exchange_code(self, code: str) -> Dict[str, Any]:
        payload = urlencode(
            {
                "code": code,
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "redirect_uri": self.config.redirect_uri,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8")
        request = Request(
            self.config.token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return self._json_response(request)

    def fetch_userinfo(self, access_token: str) -> Dict[str, Any]:
        request = Request(
            self.config.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        return self._json_response(request)

    def _json_response(self, request: Request) -> Dict[str, Any]:
        with self._open(request, timeout=self.config.timeout_seconds) as response:
            parsed = json.loads(response.read().decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}

