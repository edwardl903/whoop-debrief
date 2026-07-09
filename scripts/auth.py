"""One-time OAuth 2.0 authorization code flow for WHOOP and Strava APIs.

Run once locally to obtain access and refresh tokens, which are then
saved to .env. GitHub Actions uses the stored tokens; they refresh
automatically mid-run via WhoopClient / StravaClient.

Usage:
    make auth             # WHOOP (default)
    make strava-auth      # Strava
    python3.13 scripts/auth.py --service whoop
    python3.13 scripts/auth.py --service strava
"""
from __future__ import annotations

import argparse
import os
import secrets
import string
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import requests
from dotenv import load_dotenv, set_key

# WHOOP OAuth endpoints
_WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
_WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
_WHOOP_SCOPES = "offline read:recovery read:cycles read:sleep read:workout read:profile"

# Strava OAuth endpoints
_STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
_STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
_STRAVA_SCOPES = "activity:read_all"

# Keep backward-compatible aliases (WHOOP defaults)
_AUTH_URL = _WHOOP_AUTH_URL
_TOKEN_URL = _WHOOP_TOKEN_URL
_SCOPES = _WHOOP_SCOPES

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


def _run_oauth_flow(
    service: str,
    auth_url: str,
    token_url: str,
    scope: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    token_env_keys: dict[str, str],
    extra_token_params: dict[str, str] | None = None,
) -> None:
    """Generic OAuth 2.0 authorization code flow. Shared by WHOOP and Strava."""
    parsed = urlparse(redirect_uri)
    port = parsed.port or 8080

    state = _generate_state()
    _expected_state["value"] = state

    auth_params = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": state,
        }
    )
    full_auth_url = f"{auth_url}?{auth_params}"

    print(f"Listening on port {port} for the OAuth callback...")
    print(f"Opening {service} authorization page...\n{full_auth_url}\n")
    webbrowser.open(full_auth_url)

    code = _capture_code(port)

    if _auth_error["value"]:
        print(f"\nAuthorization failed: {_auth_error['value']}")
        print(f"Close any old {service} login tabs and run the auth command again.")
        return

    if not code:
        print(
            f"\nNo code received automatically. After approving in {service}, your browser "
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
            print("State mismatch. Run the auth command again and use the new browser tab.")
            return
        code = pasted_code

    if not code:
        print("No authorization code received. Did you complete the login?")
        return

    print("Code received. Exchanging for tokens...")
    payload: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    if extra_token_params:
        payload.update(extra_token_params)

    resp = requests.post(token_url, data=payload, timeout=30)
    if not resp.ok:
        print(f"Token exchange failed ({resp.status_code}): {resp.text}")
        return

    tokens = resp.json()
    env_path = ".env"

    for env_key, token_key in token_env_keys.items():
        value = tokens.get(token_key)
        if value:
            set_key(env_path, env_key, str(value))

    expires_in = tokens.get("expires_in", "unknown")
    print(f"Tokens saved to {env_path} (expires_in: {expires_in}s)")


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="One-time OAuth flow for WHOOP or Strava."
    )
    parser.add_argument(
        "--service",
        choices=["whoop", "strava"],
        default="whoop",
        help="Which service to authenticate. Default: whoop.",
    )
    args = parser.parse_args()

    redirect_uri = os.getenv("WHOOP_REDIRECT_URI", "http://localhost:8080/callback")

    if args.service == "strava":
        client_id = os.environ.get("STRAVA_CLIENT_ID")
        client_secret = os.environ.get("STRAVA_CLIENT_SECRET")
        if not client_id or not client_secret:
            print(
                "STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET must be set in .env "
                "before running Strava auth."
            )
            return
        _run_oauth_flow(
            service="Strava",
            auth_url=_STRAVA_AUTH_URL,
            token_url=_STRAVA_TOKEN_URL,
            scope=_STRAVA_SCOPES,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            token_env_keys={
                "STRAVA_ACCESS_TOKEN": "access_token",
                "STRAVA_REFRESH_TOKEN": "refresh_token",
            },
        )
        print("Run 'make fetch-strava' to test the Strava pipeline.")
    else:
        client_id = os.environ["WHOOP_CLIENT_ID"]
        client_secret = os.environ["WHOOP_CLIENT_SECRET"]
        _run_oauth_flow(
            service="WHOOP",
            auth_url=_WHOOP_AUTH_URL,
            token_url=_WHOOP_TOKEN_URL,
            scope=_WHOOP_SCOPES,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            token_env_keys={
                "WHOOP_ACCESS_TOKEN": "access_token",
                "WHOOP_REFRESH_TOKEN": "refresh_token",
            },
        )
        print("Run 'make fetch' to test the WHOOP pipeline.")


if __name__ == "__main__":
    main()
