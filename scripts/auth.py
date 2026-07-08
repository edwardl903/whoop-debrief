"""One-time OAuth 2.0 authorization code flow for WHOOP API.

Run once locally to obtain access and refresh tokens, which are then
saved to .env. GitHub Actions uses the stored tokens; they refresh
automatically mid-run via WhoopClient.

Usage:
    make auth
    python3.13 scripts/auth.py
"""
from __future__ import annotations

import os
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv, set_key

_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
_SCOPES = (
    "offline read:recovery read:cycles read:sleep read:workout read:profile"
)

_auth_code: dict[str, str | None] = {"value": None}


class _CallbackHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures the authorization code from the redirect."""

    def do_GET(self) -> None:
        params = parse_qs(urlparse(self.path).query)
        _auth_code["value"] = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(
            b"Authorization successful. You can close this browser tab."
        )

    def log_message(self, *args: object) -> None:
        # Suppress default Apache-style access log noise
        pass


def _capture_code(port: int) -> str | None:
    server = HTTPServer(("localhost", port), _CallbackHandler)
    server.handle_request()
    return _auth_code["value"]


def main() -> None:
    load_dotenv()

    client_id = os.environ["WHOOP_CLIENT_ID"]
    client_secret = os.environ["WHOOP_CLIENT_SECRET"]
    redirect_uri = os.getenv("WHOOP_REDIRECT_URI", "http://localhost:8080/callback")

    parsed = urlparse(redirect_uri)
    port = parsed.port or 8080

    auth_params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _SCOPES,
        }
    )
    auth_url = f"{_AUTH_URL}?{auth_params}"

    print(f"Opening WHOOP authorization page...\n{auth_url}\n")
    webbrowser.open(auth_url)

    print(f"Listening on port {port} for the OAuth callback...")
    code = _capture_code(port)

    if not code:
        print("No authorization code received. Did you complete the login?")
        return

    print("Code received. Exchanging for tokens...")
    resp = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    resp.raise_for_status()
    tokens = resp.json()

    env_path = ".env"
    set_key(env_path, "WHOOP_ACCESS_TOKEN", tokens["access_token"])
    set_key(env_path, "WHOOP_REFRESH_TOKEN", tokens["refresh_token"])

    expires_in = tokens.get("expires_in", "unknown")
    print(f"Tokens saved to {env_path} (expires_in: {expires_in}s)")
    print("Run 'make fetch' to test the pipeline.")


if __name__ == "__main__":
    main()
