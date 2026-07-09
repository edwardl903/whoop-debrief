"""Unit tests for scripts/fetch_strava.py.

All external I/O (BigQuery, Strava API) is mocked. No real network or BQ calls.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from scripts.fetch_strava import _flatten_run, ingest_endpoint, main
from utils.config import Config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> Config:
    defaults = dict(
        whoop_client_id="wcid",
        whoop_client_secret="wsec",
        whoop_redirect_uri=None,
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


_SAMPLE_RUN = {
    "id": 12345,
    "name": "Morning Run",
    "sport_type": "Run",
    "start_date": "2024-06-01T07:00:00Z",
    "distance": 8200.0,
    "moving_time": 2640,
    "elapsed_time": 2700,
    "total_elevation_gain": 45.0,
    "average_speed": 3.1,
    "max_speed": 4.2,
    "average_heartrate": 152.0,
    "max_heartrate": 172.0,
    "average_cadence": 168.0,
    "suffer_score": 63.0,
}


# ---------------------------------------------------------------------------
# Row flattener
# ---------------------------------------------------------------------------


class TestFlattenRun:
    def test_maps_strava_fields_correctly(self) -> None:
        row = _flatten_run(_SAMPLE_RUN, "2024-06-01T08:00:00")
        assert row["id"] == 12345
        assert row["name"] == "Morning Run"
        assert row["sport_type"] == "Run"
        assert row["distance_meter"] == 8200.0
        assert row["moving_time_sec"] == 2640
        assert row["elapsed_time_sec"] == 2700
        assert row["average_heartrate"] == 152.0
        assert row["loaded_at"] == "2024-06-01T08:00:00"

    def test_missing_optional_fields_return_none(self) -> None:
        minimal = {"id": 1, "sport_type": "Run", "start_date": "2024-06-01T07:00:00Z"}
        row = _flatten_run(minimal, "2024-06-01T08:00:00")
        assert row["average_heartrate"] is None
        assert row["suffer_score"] is None
        assert row["average_cadence"] is None

    def test_loaded_at_preserved(self) -> None:
        row = _flatten_run(_SAMPLE_RUN, "2024-06-01T09:00:00+00:00")
        assert row["loaded_at"] == "2024-06-01T09:00:00+00:00"


# ---------------------------------------------------------------------------
# ingest_endpoint
# ---------------------------------------------------------------------------


class TestIngestEndpoint:
    def _make_mocks(self, records=None, watermark=None):
        # Use explicit sentinel so callers can pass an empty list.
        actual_records = [_SAMPLE_RUN] if records is None else records

        strava = MagicMock()
        strava.get_runs.return_value = actual_records

        bq = MagicMock()
        bq.get_watermark.return_value = watermark
        bq.insert_rows.return_value = len(actual_records)

        return strava, bq

    def test_success_returns_success_status(self) -> None:
        strava, bq = self._make_mocks()
        result = ingest_endpoint("runs", strava, bq, "whoop_raw", dry_run=False)
        assert result["status"] == "success"
        assert result["rows_fetched"] == 1
        assert result["rows_inserted"] == 1

    def test_dry_run_skips_insert(self) -> None:
        strava, bq = self._make_mocks()
        result = ingest_endpoint("runs", strava, bq, "whoop_raw", dry_run=True)
        bq.insert_rows.assert_not_called()
        assert result["rows_inserted"] == 0

    def test_exception_returns_failed_status(self) -> None:
        strava = MagicMock()
        strava.get_runs.side_effect = RuntimeError("API down")
        bq = MagicMock()
        bq.get_watermark.return_value = None

        result = ingest_endpoint("runs", strava, bq, "whoop_raw", dry_run=False)
        assert result["status"] == "failed"
        assert "API down" in result["error_msg"]

    def test_watermark_passed_to_client(self) -> None:
        from datetime import datetime, timezone
        watermark = datetime(2024, 5, 31, tzinfo=timezone.utc)
        strava, bq = self._make_mocks(watermark=watermark)
        ingest_endpoint("runs", strava, bq, "whoop_raw", dry_run=True)
        strava.get_runs.assert_called_once_with(after=watermark)

    def test_empty_records_skips_insert(self) -> None:
        strava, bq = self._make_mocks(records=[])
        ingest_endpoint("runs", strava, bq, "whoop_raw", dry_run=False)
        bq.insert_rows.assert_not_called()

    def test_endpoint_name_prefixed_with_strava(self) -> None:
        strava, bq = self._make_mocks()
        result = ingest_endpoint("runs", strava, bq, "whoop_raw", dry_run=True)
        assert result["endpoint"] == "strava_runs"


# ---------------------------------------------------------------------------
# main() — integration of config check + pipeline
# ---------------------------------------------------------------------------


class TestMain:
    def test_exits_zero_when_strava_not_configured(self) -> None:
        cfg = _make_config(strava_access_token=None)
        with patch("scripts.fetch_strava.load_config", return_value=cfg):
            result = main([])
        assert result == 0

    def test_exits_zero_on_full_success(self) -> None:
        cfg = _make_config()
        mock_strava = MagicMock()
        mock_strava.get_runs.return_value = [_SAMPLE_RUN]
        mock_bq = MagicMock()
        mock_bq.get_watermark.return_value = None
        mock_bq.insert_rows.return_value = 1

        with (
            patch("scripts.fetch_strava.load_config", return_value=cfg),
            patch("scripts.fetch_strava.StravaClient", return_value=mock_strava),
            patch("scripts.fetch_strava.BigQueryClient", return_value=mock_bq),
        ):
            result = main([])
        assert result == 0

    def test_exits_one_on_failure(self) -> None:
        cfg = _make_config()
        mock_strava = MagicMock()
        mock_strava.get_runs.side_effect = RuntimeError("explode")
        mock_bq = MagicMock()
        mock_bq.get_watermark.return_value = None

        with (
            patch("scripts.fetch_strava.load_config", return_value=cfg),
            patch("scripts.fetch_strava.StravaClient", return_value=mock_strava),
            patch("scripts.fetch_strava.BigQueryClient", return_value=mock_bq),
        ):
            result = main([])
        assert result == 1

    def test_dry_run_flag_passed_through(self) -> None:
        cfg = _make_config()
        mock_strava = MagicMock()
        mock_strava.get_runs.return_value = []
        mock_bq = MagicMock()
        mock_bq.get_watermark.return_value = None

        with (
            patch("scripts.fetch_strava.load_config", return_value=cfg),
            patch("scripts.fetch_strava.StravaClient", return_value=mock_strava),
            patch("scripts.fetch_strava.BigQueryClient", return_value=mock_bq),
        ):
            result = main(["--dry-run"])
        mock_bq.insert_rows.assert_not_called()
        assert result == 0
