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
import secrets
import string
import time
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
_CALLBACK_TIMEOUT_SEC = 120
_STATE_CHARS = string.ascii_letters + string.digits

_auth_code: dict[str, str | None] = {"value": None}
_auth_error: dict[str, str | None] = {"value": None}
_expected_state: dict[str, str] = {"value": ""}


def _generate_state() -> str:
    """WHOOP requires state to be exactly 8 characters."""
    return "".join(secrets.choice(_STATE_CHARS) for _ in range(8))


class _CallbackHandler(BaseHTTPRequestHandler):
    """Captures the authorization code from the OAuth redirect."""

    def do_GET(self) -> None:
        params = parse_qs(urlparse(self.path).query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        if error:
            _auth_error["value"] = error
            body = f"Authorization failed: {error}".encode()
            status = 400
        elif code:
            if state != _expected_state["value"]:
                _auth_error["value"] = "state_mismatch"
                body = b"Authorization failed: state mismatch. Run make auth again."
                status = 400
            else:
                _auth_code["value"] = code
                body = b"Authorization successful. You can close this browser tab."
                status = 200
        else:
            body = b"Waiting for authorization..."
            status = 404

        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


def _parse_callback_url(url: str) -> tuple[str | None, str | None, str | None]:
    params = parse_qs(urlparse(url.strip()).query)
    code = params.get("code", [None])[0]
    state = params.get("state", [None])[0]
    error = params.get("error", [None])[0]
    return code, state, error


def _capture_code(port: int, timeout_sec: int = _CALLBACK_TIMEOUT_SEC) -> str | None:
    """Listen until WHOOP redirects with ?code=... or timeout."""
    _auth_code["value"] = None
    _auth_error["value"] = None
    server = HTTPServer(("localhost", port), _CallbackHandler)
    server.timeout = 1

    deadline = time.time() + timeout_sec
    while time.time() < deadline and not _auth_code["value"] and not _auth_error["value"]:
        server.handle_request()

    return _auth_code["value"]


def main() -> None:
    load_dotenv()

    client_id = os.environ["WHOOP_CLIENT_ID"]
    client_secret = os.environ["WHOOP_CLIENT_SECRET"]
    redirect_uri = os.getenv("WHOOP_REDIRECT_URI", "http://localhost:8080/callback")

    parsed = urlparse(redirect_uri)
    port = parsed.port or 8080

    state = _generate_state()
    _expected_state["value"] = state

    auth_params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _SCOPES,
            "state": state,
        }
    )
    auth_url = f"{_AUTH_URL}?{auth_params}"

    print(f"Listening on port {port} for the OAuth callback...")
    print(f"Opening WHOOP authorization page...\n{auth_url}\n")
    webbrowser.open(auth_url)

    code = _capture_code(port)

    if _auth_error["value"]:
        print(f"\nAuthorization failed: {_auth_error['value']}")
        print("Close any old WHOOP login tabs and run `make auth` again.")
        return

    if not code:
        print(
            "\nNo code received automatically. After approving in WHOOP, your browser "
            "redirects to a localhost URL that may not load. That is fine."
        )
        pasted = input(
            "Paste the full redirect URL from your browser address bar: "
        ).strip()
        pasted_code, pasted_state, pasted_error = _parse_callback_url(pasted)
        if pasted_error:
            print(f"Authorization failed: {pasted_error}")
            return
        if pasted_state != state:
            print("State mismatch. Run `make auth` again and use the new browser tab.")
            return
        code = pasted_code

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
    if not resp.ok:
        print(f"Token exchange failed ({resp.status_code}): {resp.text}")
        return

    tokens = resp.json()

    env_path = ".env"
    set_key(env_path, "WHOOP_ACCESS_TOKEN", tokens["access_token"])
    set_key(env_path, "WHOOP_REFRESH_TOKEN", tokens["refresh_token"])

    expires_in = tokens.get("expires_in", "unknown")
    print(f"Tokens saved to {env_path} (expires_in: {expires_in}s)")
    print("Run 'make fetch' to test the pipeline.")


if __name__ == "__main__":
    main()
