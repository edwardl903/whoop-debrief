"""Unit tests for WhoopClient.

All HTTP calls are mocked via unittest.mock. No real network requests.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from utils.config import Config
from utils.whoop_client import TokenRefreshError, WhoopAPIError, WhoopClient, _fmt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg() -> Config:
    return Config(
        whoop_client_id="cid",
        whoop_client_secret="csec",
        whoop_redirect_uri="http://localhost:8080/callback",
        whoop_access_token="tok_access",
        whoop_refresh_token="tok_refresh",
        strava_client_id=None,
        strava_client_secret=None,
        strava_access_token=None,
        strava_refresh_token=None,
        bq_project="proj",
        bq_dataset_raw="whoop_raw",
        bq_dataset_dbt="whoop_dbt",
        bq_location="us-central1",
        google_credentials_json=None,
        google_credentials_path="/tmp/sa.json",
    )


@pytest.fixture
def client(cfg: Config) -> WhoopClient:
    return WhoopClient(cfg)


def _ok_response(body: dict) -> MagicMock:
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
# Pagination
# ---------------------------------------------------------------------------


class TestPagination:
    def test_single_page_returns_all_records(self, client: WhoopClient) -> None:
        records = [{"id": 1}, {"id": 2}]
        with patch.object(
            client, "_get", return_value={"records": records, "next_token": None}
        ):
            result = client.get_cycles()
        assert result == records

    def test_multi_page_concatenates_records(self, client: WhoopClient) -> None:
        page1 = {"records": [{"id": 1}], "next_token": "tok_page2"}
        page2 = {"records": [{"id": 2}], "next_token": None}
        with patch.object(client, "_get", side_effect=[page1, page2]):
            result = client.get_cycles()
        assert len(result) == 2
        assert [r["id"] for r in result] == [1, 2]

    def test_empty_response_returns_empty_list(self, client: WhoopClient) -> None:
        with patch.object(
            client, "_get", return_value={"records": [], "next_token": None}
        ):
            result = client.get_sleeps()
        assert result == []

    def test_next_token_passed_on_subsequent_call(self, client: WhoopClient) -> None:
        page1 = {"records": [{"id": 1}], "next_token": "abc"}
        page2 = {"records": [{"id": 2}], "next_token": None}
        with patch.object(client, "_get", side_effect=[page1, page2]) as mock_get:
            client.get_cycles()
        # Second call should include nextToken
        _, second_params = mock_get.call_args_list[1][0]
        assert second_params.get("nextToken") == "abc"


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    def test_401_triggers_refresh_and_retries(self, client: WhoopClient) -> None:
        unauthorized = _error_response(401)
        unauthorized.ok = False
        ok = _ok_response({"records": [], "next_token": None})

        refresh_resp = _ok_response(
            {"access_token": "new_tok", "refresh_token": "new_ref"}
        )

        with (
            patch.object(client._session, "get", side_effect=[unauthorized, ok]),
            patch.object(client._session, "post", return_value=refresh_resp),
        ):
            result = client._get("/cycle")

        assert result == {"records": [], "next_token": None}
        assert client._access_token == "new_tok"
        assert client._refresh_token == "new_ref"

    def test_refresh_failure_raises_token_refresh_error(self, client: WhoopClient) -> None:
        unauthorized = _error_response(401)
        bad_refresh = _error_response(400, "invalid_grant")

        with (
            patch.object(client._session, "get", return_value=unauthorized),
            patch.object(client._session, "post", return_value=bad_refresh),
        ):
            with pytest.raises(TokenRefreshError):
                client._get("/cycle")

    def test_refresh_keeps_old_refresh_token_if_not_returned(
        self, client: WhoopClient
    ) -> None:
        unauthorized = _error_response(401)
        ok = _ok_response({})
        # WHOOP sometimes does not return a new refresh_token
        refresh_resp = _ok_response({"access_token": "new_tok"})

        original_refresh = client._refresh_token
        with (
            patch.object(client._session, "get", side_effect=[unauthorized, ok]),
            patch.object(client._session, "post", return_value=refresh_resp),
        ):
            client._get("/cycle")

        assert client._refresh_token == original_refresh

    def test_refresh_includes_scope_and_redirect_uri(self, client: WhoopClient) -> None:
        refresh_resp = _ok_response({"access_token": "new_tok"})
        with patch.object(client._session, "post", return_value=refresh_resp) as mock_post:
            client._refresh_access_token()
        _, kwargs = mock_post.call_args
        data = kwargs["data"]
        assert data["scope"] == "offline"
        assert data["redirect_uri"] == "http://localhost:8080/callback"


class TestApiErrors:
    def test_500_raises_whoop_api_error(self, client: WhoopClient) -> None:
        with patch.object(
            client._session, "get", return_value=_error_response(500, "Internal Server Error")
        ):
            with pytest.raises(WhoopAPIError) as exc_info:
                client._get("/cycle")
        assert exc_info.value.status_code == 500

    def test_403_raises_whoop_api_error(self, client: WhoopClient) -> None:
        with patch.object(
            client._session, "get", return_value=_error_response(403, "Forbidden")
        ):
            with pytest.raises(WhoopAPIError) as exc_info:
                client._get("/sleep")
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Date parameter formatting
# ---------------------------------------------------------------------------


class TestDateParams:
    def test_start_passed_to_get(self, client: WhoopClient) -> None:
        start = datetime(2024, 3, 1, tzinfo=timezone.utc)
        with patch.object(
            client, "_get", return_value={"records": [], "next_token": None}
        ) as mock_get:
            client.get_cycles(start=start)
        _, params = mock_get.call_args[0]
        assert "start" in params
        assert "2024-03-01" in params["start"]

    def test_end_passed_to_get(self, client: WhoopClient) -> None:
        end = datetime(2024, 3, 15, tzinfo=timezone.utc)
        with patch.object(
            client, "_get", return_value={"records": [], "next_token": None}
        ) as mock_get:
            client.get_workouts(end=end)
        _, params = mock_get.call_args[0]
        assert "end" in params

    def test_no_dates_passes_no_date_params(self, client: WhoopClient) -> None:
        with patch.object(
            client, "_get", return_value={"records": [], "next_token": None}
        ) as mock_get:
            client.get_recoveries()
        _, params = mock_get.call_args[0]
        assert "start" not in params
        assert "end" not in params

    def test_fmt_naive_datetime_treated_as_utc(self) -> None:
        naive = datetime(2024, 1, 1, 12, 0, 0)
        result = _fmt(naive)
        assert result == "2024-01-01T12:00:00.000Z"

    def test_fmt_aware_datetime(self) -> None:
        aware = datetime(2024, 6, 15, 8, 30, 0, tzinfo=timezone.utc)
        result = _fmt(aware)
        assert result == "2024-06-15T08:30:00.000Z"


# ---------------------------------------------------------------------------
# Endpoint methods
# ---------------------------------------------------------------------------


class TestEndpoints:
    def test_get_user_profile_calls_correct_path(self, client: WhoopClient) -> None:
        profile = {"user_id": 42, "email": "test@example.com"}
        with patch.object(client, "_get", return_value=profile) as mock_get:
            result = client.get_user_profile()
        mock_get.assert_called_once_with("/user/profile/basic")
        assert result == profile

    @pytest.mark.parametrize(
        "method, expected_path",
        [
            ("get_cycles", "/cycle"),
            ("get_sleeps", "/activity/sleep"),
            ("get_recoveries", "/recovery"),
            ("get_workouts", "/activity/workout"),
        ],
    )
    def test_endpoint_paths(
        self, client: WhoopClient, method: str, expected_path: str
    ) -> None:
        with patch.object(
            client, "_get", return_value={"records": [], "next_token": None}
        ) as mock_get:
            getattr(client, method)()
        called_path, _ = mock_get.call_args[0]
        assert called_path == expected_path
