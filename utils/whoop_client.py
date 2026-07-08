"""WHOOP API v1 client.

All API calls in the pipeline go through this module. Never construct
requests sessions or call the WHOOP API inline elsewhere.

Handles:
- OAuth 2.0 Bearer auth
- Automatic access token refresh on 401
- Cursor-based pagination (next_token)
- Exponential backoff retry (urllib3 Retry via HTTPAdapter)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Generator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.config import Config

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.prod.whoop.com/developer/v1"
_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
_PAGE_LIMIT = 25
_MAX_RETRIES = 3
_BACKOFF_FACTOR = 1.0
# Status codes that trigger a urllib3-level retry (before our 401 logic)
_RETRY_STATUSES = {429, 500, 502, 503, 504}


class TokenRefreshError(Exception):
    """Raised when the OAuth refresh token exchange fails."""


class WhoopAPIError(Exception):
    """Raised for non-retriable WHOOP API errors."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"WHOOP API {status_code}: {body}")
        self.status_code = status_code


class WhoopClient:
    """WHOOP API v1 client. One instance per pipeline run."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._access_token = config.whoop_access_token
        self._refresh_token = config.whoop_refresh_token
        self._session = self._build_session()

    # ------------------------------------------------------------------ setup

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry_policy = Retry(
            total=_MAX_RETRIES,
            backoff_factor=_BACKOFF_FACTOR,
            status_forcelist=_RETRY_STATUSES,
            allowed_methods=["GET", "POST"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_policy)
        session.mount("https://", adapter)
        return session

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    # ---------------------------------------------------------- token refresh

    def _refresh_access_token(self) -> None:
        logger.info("Refreshing WHOOP access token")
        resp = self._session.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._config.whoop_client_id,
                "client_secret": self._config.whoop_client_secret,
            },
            timeout=30,
        )
        if not resp.ok:
            raise TokenRefreshError(
                f"Token refresh failed ({resp.status_code}): {resp.text}"
            )
        tokens = resp.json()
        self._access_token = tokens["access_token"]
        # WHOOP may or may not return a new refresh token
        self._refresh_token = tokens.get("refresh_token", self._refresh_token)
        logger.info("Access token refreshed successfully")

    # -------------------------------------------------------- low-level fetch

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{_BASE_URL}{path}"
        resp = self._session.get(
            url, headers=self._auth_headers(), params=params, timeout=30
        )
        if resp.status_code == 401:
            self._refresh_access_token()
            resp = self._session.get(
                url, headers=self._auth_headers(), params=params, timeout=30
            )
        if not resp.ok:
            raise WhoopAPIError(resp.status_code, resp.text)
        return resp.json()

    def _paginate(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Generator[dict[str, Any], None, None]:
        params = dict(params or {})
        params["limit"] = _PAGE_LIMIT
        page = 0
        while True:
            data = self._get(path, params)
            records: list[dict[str, Any]] = data.get("records", [])
            logger.debug(
                "Fetched page",
                extra={"path": path, "page": page, "records": len(records)},
            )
            yield from records
            next_token: str | None = data.get("next_token")
            if not next_token:
                break
            params["nextToken"] = next_token
            page += 1

    # ------------------------------------------------------- public endpoints

    def get_cycles(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return all daily strain cycles in the given window."""
        return list(self._paginate("/cycle", _date_params(start, end)))

    def get_sleeps(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return all sleep records in the given window."""
        return list(self._paginate("/activity/sleep", _date_params(start, end)))

    def get_recoveries(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return all recovery records in the given window."""
        return list(self._paginate("/recovery", _date_params(start, end)))

    def get_workouts(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Return all workout records in the given window."""
        return list(self._paginate("/activity/workout", _date_params(start, end)))

    def get_user_profile(self) -> dict[str, Any]:
        """Return the authenticated user's basic profile."""
        return self._get("/user/profile/basic")


# -------------------------------------------------------------------- helpers


def _date_params(
    start: datetime | None, end: datetime | None
) -> dict[str, str]:
    """Convert datetime bounds to WHOOP API query parameters."""
    params: dict[str, str] = {}
    if start:
        params["start"] = _fmt(start)
    if end:
        params["end"] = _fmt(end)
    return params


def _fmt(dt: datetime) -> str:
    """Format a datetime as the ISO 8601 string WHOOP expects."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
