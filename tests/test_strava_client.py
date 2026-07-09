"""Unit tests for StravaClient.

All HTTP calls are mocked via unittest.mock. No real network requests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from utils.config import Config
from utils.strava_client import StravaAPIError, StravaClient, TokenRefreshError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> Config:
    defaults = dict(
        whoop_client_id="wcid",
        whoop_client_secret="wsec",
        whoop_redirect_uri="http://localhost:8080/callback",
        whoop_access_token="wtok",
        whoop_refresh_token="wref",
        strava_client_id="scid",
        strava_client_secret="ssec",
        strava_access_token="stok",
        strava_refresh_token="sref",
        bq_project="proj",
        bq_dataset_raw="whoop_raw",
        bq_dataset_dbt="whoop_dbt",
        bq_location="us-central1",
        google_credentials_json=None,
        google_credentials_path="/tmp/sa.json",
    )
    defaults.update(overrides)
    return Config(**defaults)


@pytest.fixture
def cfg() -> Config:
    return _make_config()


@pytest.fixture
def client(cfg: Config) -> StravaClient:
    return StravaClient(cfg)


def _ok_response(body) -> MagicMock:
    resp = MagicMock()
    resp.ok = True
    resp.status_code = 200
    resp.json.return_value = body
    return resp


def _error_response(status: int, text: str = "error") -> MagicMock:
    resp = MagicMock()
    resp.ok = False
    resp.status_code = status
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Instantiation guard
# ---------------------------------------------------------------------------


class TestInstantiation:
    def test_raises_if_strava_not_configured(self) -> None:
        cfg = _make_config(strava_access_token=None)
        with pytest.raises(ValueError, match="Strava credentials not configured"):
            StravaClient(cfg)

    def test_ok_when_all_credentials_present(self, cfg: Config) -> None:
        client = StravaClient(cfg)
        assert client._access_token == "stok"


# ---------------------------------------------------------------------------
# Page-based pagination
# ---------------------------------------------------------------------------


class TestPagination:
    def test_single_full_page_fetches_next_page(self, client: StravaClient) -> None:
        # First page has PAGE_SIZE records, second is empty -> stop.
        from utils.strava_client import _PAGE_SIZE
        page1 = [{"id": i, "sport_type": "Run"} for i in range(_PAGE_SIZE)]
        page2: list = []
        with patch.object(client, "_get", side_effect=[page1, page2]):
            result = client.get_runs()
        assert len(result) == _PAGE_SIZE

    def test_partial_page_stops_immediately(self, client: StravaClient) -> None:
        page1 = [{"id": 1, "sport_type": "Run"}, {"id": 2, "sport_type": "Run"}]
        with patch.object(client, "_get", return_value=page1):
            result = client.get_runs()
        assert len(result) == 2

    def test_empty_first_page_returns_empty_list(self, client: StravaClient) -> None:
        with patch.object(client, "_get", return_value=[]):
            result = client.get_runs()
        assert result == []

    def test_page_number_increments(self, client: StravaClient) -> None:
        from utils.strava_client import _PAGE_SIZE
        page1 = [{"id": i, "sport_type": "Run"} for i in range(_PAGE_SIZE)]
        page2: list = []
        # Capture param snapshots at call time because _paginate mutates params in-place.
        captured_pages: list[int] = []

        def capture_get(path, params):
            captured_pages.append(params.get("page"))
            if params["page"] == 1:
                return page1
            return page2

        with patch.object(client, "_get", side_effect=capture_get):
            client.get_runs()

        assert captured_pages == [1, 2]


# ---------------------------------------------------------------------------
# Sport-type filtering
# ---------------------------------------------------------------------------


class TestSportTypeFilter:
    def test_filters_out_non_run_activities(self, client: StravaClient) -> None:
        activities = [
            {"id": 1, "sport_type": "Run"},
            {"id": 2, "sport_type": "Ride"},
            {"id": 3, "sport_type": "TrailRun"},
            {"id": 4, "sport_type": "Swim"},
            {"id": 5, "sport_type": "VirtualRun"},
        ]
        with patch.object(client, "_get", return_value=activities):
            result = client.get_runs()
        ids = [r["id"] for r in result]
        assert ids == [1, 3, 5]

    def test_all_non_runs_returns_empty(self, client: StravaClient) -> None:
        activities = [{"id": 1, "sport_type": "Ride"}, {"id": 2, "sport_type": "Swim"}]
        with patch.object(client, "_get", return_value=activities):
            result = client.get_runs()
        assert result == []


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    def test_401_triggers_refresh_and_retries(self, client: StravaClient) -> None:
        unauthorized = _error_response(401)
        ok = _ok_response([{"id": 1, "sport_type": "Run"}])
        refresh_resp = _ok_response({"access_token": "new_tok", "refresh_token": "new_ref"})

        with (
            patch.object(client._session, "get", side_effect=[unauthorized, ok]),
            patch.object(client._session, "post", return_value=refresh_resp),
        ):
            result = client._get("/athlete/activities")

        assert result == [{"id": 1, "sport_type": "Run"}]
        assert client._access_token == "new_tok"

    def test_refresh_failure_raises_token_refresh_error(self, client: StravaClient) -> None:
        unauthorized = _error_response(401)
        bad_refresh = _error_response(400, "invalid_grant")

        with (
            patch.object(client._session, "get", return_value=unauthorized),
            patch.object(client._session, "post", return_value=bad_refresh),
        ):
            with pytest.raises(TokenRefreshError):
                client._get("/athlete/activities")

    def test_refresh_payload_uses_config_credentials(self, client: StravaClient) -> None:
        refresh_resp = _ok_response({"access_token": "new_tok"})
        with patch.object(client._session, "post", return_value=refresh_resp) as mock_post:
            client._refresh_access_token()
        _, kwargs = mock_post.call_args
        data = kwargs["data"]
        assert data["grant_type"] == "refresh_token"
        assert data["client_id"] == "scid"
        assert data["client_secret"] == "ssec"
        assert data["refresh_token"] == "sref"


# ---------------------------------------------------------------------------
# API errors
# ---------------------------------------------------------------------------


class TestApiErrors:
    def test_500_raises_strava_api_error(self, client: StravaClient) -> None:
        with patch.object(
            client._session, "get", return_value=_error_response(500, "Internal Server Error")
        ):
            with pytest.raises(StravaAPIError) as exc_info:
                client._get("/athlete/activities")
        assert exc_info.value.status_code == 500

    def test_403_raises_strava_api_error(self, client: StravaClient) -> None:
        with patch.object(
            client._session, "get", return_value=_error_response(403, "Forbidden")
        ):
            with pytest.raises(StravaAPIError) as exc_info:
                client._get("/athlete/activities")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# After param (watermark)
# ---------------------------------------------------------------------------


class TestAfterParam:
    def test_after_passed_as_unix_epoch(self, client: StravaClient) -> None:
        after = datetime(2024, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        with patch.object(client, "_get", return_value=[]) as mock_get:
            client.get_runs(after=after)
        _, params = mock_get.call_args[0]
        expected_epoch = int(after.timestamp())
        assert params["after"] == expected_epoch

    def test_no_after_omits_param(self, client: StravaClient) -> None:
        with patch.object(client, "_get", return_value=[]) as mock_get:
            client.get_runs()
        _, params = mock_get.call_args[0]
        assert "after" not in params

    def test_naive_after_treated_as_utc(self, client: StravaClient) -> None:
        naive = datetime(2024, 6, 1, 0, 0, 0)
        aware = datetime(2024, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        with patch.object(client, "_get", return_value=[]) as mock_get:
            client.get_runs(after=naive)
        _, params = mock_get.call_args[0]
        assert params["after"] == int(aware.timestamp())
