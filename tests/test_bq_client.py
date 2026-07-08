"""Unit tests for BigQueryClient.

BigQuery SDK calls are mocked so no GCP credentials are needed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from utils.bq_client import BigQueryClient
from utils.config import Config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg() -> Config:
    return Config(
        whoop_client_id="cid",
        whoop_client_secret="csec",
        whoop_redirect_uri="http://localhost:8080/callback",
        whoop_access_token="tok",
        whoop_refresh_token="ref",
        bq_project="my_project",
        bq_dataset_raw="whoop_raw",
        bq_dataset_dbt="whoop_dbt",
        bq_location="us-central1",
        google_credentials_json=None,
        google_credentials_path="/tmp/sa.json",
    )


@pytest.fixture
def bq(cfg: Config) -> BigQueryClient:
    with patch("utils.bq_client.bigquery.Client"):
        client = BigQueryClient(cfg)
    return client


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


class TestClientConstruction:
    def test_builds_with_json_credentials(self, cfg: Config) -> None:
        sa_json = '{"type": "service_account", "project_id": "proj"}'
        cfg_with_json = Config(
            **{**cfg.__dict__, "google_credentials_json": sa_json}
        )
        with (
            patch("utils.bq_client.service_account.Credentials.from_service_account_info") as mock_creds,
            patch("utils.bq_client.bigquery.Client"),
        ):
            BigQueryClient(cfg_with_json)
        mock_creds.assert_called_once()

    def test_builds_with_adc_when_no_json(self, cfg: Config) -> None:
        with patch("utils.bq_client.bigquery.Client") as mock_client:
            BigQueryClient(cfg)
        mock_client.assert_called_once_with(
            project="my_project", location="us-central1"
        )


# ---------------------------------------------------------------------------
# Dataset and table management
# ---------------------------------------------------------------------------


class TestSchemaManagement:
    def test_ensure_dataset_calls_create_dataset(self, bq: BigQueryClient) -> None:
        bq._client.create_dataset = MagicMock()
        bq.ensure_dataset("whoop_raw")
        bq._client.create_dataset.assert_called_once()
        _, kwargs = bq._client.create_dataset.call_args
        assert kwargs.get("exists_ok") is True

    def test_ensure_table_calls_create_table(self, bq: BigQueryClient) -> None:
        bq._client.dataset = MagicMock(return_value=MagicMock())
        bq._client.create_table = MagicMock()
        bq.ensure_table("whoop_raw", "raw_cycles")
        bq._client.create_table.assert_called_once()
        _, kwargs = bq._client.create_table.call_args
        assert kwargs.get("exists_ok") is True

    def test_ensure_table_raises_for_unknown_table(self, bq: BigQueryClient) -> None:
        with pytest.raises(KeyError):
            bq.ensure_table("whoop_raw", "nonexistent_table")


# ---------------------------------------------------------------------------
# Watermark query
# ---------------------------------------------------------------------------


class TestGetWatermark:
    def test_returns_none_when_table_empty(self, bq: BigQueryClient) -> None:
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, k: None
        bq._client.query = MagicMock(
            return_value=MagicMock(result=MagicMock(return_value=[mock_row]))
        )
        result = bq.get_watermark("whoop_raw", "raw_cycles")
        assert result is None

    def test_returns_utc_datetime(self, bq: BigQueryClient) -> None:
        ts = datetime(2024, 6, 1, 6, 0, 0, tzinfo=timezone.utc)
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, k: ts
        bq._client.query = MagicMock(
            return_value=MagicMock(result=MagicMock(return_value=[mock_row]))
        )
        result = bq.get_watermark("whoop_raw", "raw_cycles")
        assert result == ts
        assert result.tzinfo is not None

    def test_naive_datetime_gets_utc_attached(self, bq: BigQueryClient) -> None:
        naive = datetime(2024, 6, 1, 6, 0, 0)
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, k: naive
        bq._client.query = MagicMock(
            return_value=MagicMock(result=MagicMock(return_value=[mock_row]))
        )
        result = bq.get_watermark("whoop_raw", "raw_cycles")
        assert result is not None
        assert result.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Row inserts
# ---------------------------------------------------------------------------


class TestInsertRows:
    def test_empty_list_skips_insert_and_returns_zero(self, bq: BigQueryClient) -> None:
        bq._client.insert_rows_json = MagicMock()
        result = bq.insert_rows("whoop_raw", "raw_cycles", [])
        bq._client.insert_rows_json.assert_not_called()
        assert result == 0

    def test_returns_row_count_on_success(self, bq: BigQueryClient) -> None:
        bq._client.dataset = MagicMock(return_value=MagicMock())
        bq._client.insert_rows_json = MagicMock(return_value=[])
        rows = [{"id": 1, "loaded_at": "2024-01-01T00:00:00Z"}]
        result = bq.insert_rows("whoop_raw", "raw_cycles", rows)
        assert result == 1

    def test_raises_on_insert_errors(self, bq: BigQueryClient) -> None:
        bq._client.dataset = MagicMock(return_value=MagicMock())
        bq._client.insert_rows_json = MagicMock(
            return_value=[{"index": 0, "errors": [{"reason": "invalid"}]}]
        )
        with pytest.raises(RuntimeError, match="BigQuery streaming insert errors"):
            bq.insert_rows("whoop_raw", "raw_cycles", [{"id": 1}])


# ---------------------------------------------------------------------------
# Pipeline run logging
# ---------------------------------------------------------------------------


class TestLogPipelineRun:
    def test_writes_single_row_to_pipeline_runs(self, bq: BigQueryClient) -> None:
        bq._client.dataset = MagicMock(return_value=MagicMock())
        bq._client.insert_rows_json = MagicMock(return_value=[])

        run = {
            "run_id": "abc-123",
            "endpoint": "cycles",
            "started_at": "2024-01-01T06:00:00Z",
            "ended_at": "2024-01-01T06:01:00Z",
            "rows_fetched": 5,
            "rows_inserted": 5,
            "watermark_start": None,
            "watermark_end": "2024-01-01T06:01:00Z",
            "status": "success",
            "error_msg": None,
        }
        bq.log_pipeline_run(run)
        bq._client.insert_rows_json.assert_called_once()
        _, inserted_rows = bq._client.insert_rows_json.call_args[0]
        assert inserted_rows == [run]
