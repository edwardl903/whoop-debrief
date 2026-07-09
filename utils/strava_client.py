"""Strava API v3 client.

All Strava API calls in the pipeline go through this module.

Handles:
- OAuth 2.0 Bearer auth
- Automatic access token refresh on 401
- Page-based pagination (?page=N&per_page=50)
- Exponential backoff retry (urllib3 Retry via HTTPAdapter)

Note: Unlike WHOOP, Strava refresh tokens are static (do not rotate on each
use), so there is no need to persist an updated refresh token after a refresh.
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

_BASE_URL = "https://www.strava.com/api/v3"
_TOKEN_URL = "https://www.strava.com/oauth/token"
_PAGE_SIZE = 50
_MAX_RETRIES = 3
_BACKOFF_FACTOR = 1.0
_RETRY_STATUSES = {429, 500, 502, 503, 504}


class TokenRefreshError(Exception):
    """Raised when the Strava OAuth token refresh fails."""


class StravaAPIError(Exception):
    """Raised for non-retriable Strava API errors."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"Strava API {status_code}: {body}")
        self.status_code = status_code


class StravaClient:
    """Strava API v3 client. One instance per pipeline run.

    Requires config.strava_configured == True before instantiation.
    Callers should check config.strava_configured and skip if False.
    """

    def __init__(self, config: Config) -> None:
        if not config.strava_configured:
            raise ValueError(
                "Strava credentials not configured. Set STRAVA_CLIENT_ID, "
                "STRAVA_CLIENT_SECRET, STRAVA_ACCESS_TOKEN, STRAVA_REFRESH_TOKEN."
            )
        self._config = config
        self._access_token: str = config.strava_access_token  # type: ignore[assignment]
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
        logger.info("Refreshing Strava access token")
        payload: dict[str, str] = {
            "grant_type": "refresh_token",
            "client_id": self._config.strava_client_id,  # type: ignore[assignment]
            "client_secret": self._config.strava_client_secret,  # type: ignore[assignment]
            "refresh_token": self._config.strava_refresh_token,  # type: ignore[assignment]
        }
        resp = self._session.post(_TOKEN_URL, data=payload, timeout=30)
        if not resp.ok:
            raise TokenRefreshError(
                f"Token refresh failed ({resp.status_code}): {resp.text}"
            )
        tokens = resp.json()
        self._access_token = tokens["access_token"]
        # Strava refresh tokens are static, but rotate them if Strava ever returns a new one.
        logger.info("Strava access token refreshed successfully")

    # -------------------------------------------------------- low-level fetch

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
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
            raise StravaAPIError(resp.status_code, resp.text)
        return resp.json()

    def _paginate(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Generator[dict[str, Any], None, None]:
        """Page through a Strava list endpoint (page + per_page style)."""
        params = dict(params or {})
        params["per_page"] = _PAGE_SIZE
        page = 1
        while True:
            params["page"] = page
            records: list[dict[str, Any]] = self._get(path, params)
            logger.debug(
                "Fetched page",
                extra={"path": path, "page": page, "records": len(records)},
            )
            if not records:
                break
            yield from records
            if len(records) < _PAGE_SIZE:
                break
            page += 1

    # ------------------------------------------------------- public endpoints

    def get_runs(self, after: datetime | None = None) -> list[dict[str, Any]]:
        """Return all runs, optionally after a given timestamp.

        Strava's /athlete/activities accepts `after` as a Unix epoch integer.
        We filter to sport_type == "Run" | "TrailRun" | "VirtualRun" client-side
        because the API has no type filter parameter.
        """
        params: dict[str, Any] = {}
        if after:
            utc_after = after if after.tzinfo else after.replace(tzinfo=timezone.utc)
            params["after"] = int(utc_after.timestamp())

        run_types = {"Run", "TrailRun", "VirtualRun"}
        return [
            r
            for r in self._paginate("/athlete/activities", params)
            if r.get("sport_type") in run_types
        ]
