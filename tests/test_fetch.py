"""Unit tests for scripts/fetch.py.

Tests cover row flatteners, ingest_endpoint orchestration, and CLI behavior.
All external I/O (WHOOP API, BigQuery) is mocked.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from scripts.fetch import (
    _flatten_cycle,
    _flatten_recovery,
    _flatten_sleep,
    _flatten_workout,
    ingest_endpoint,
    main,
)


_LOADED_AT = "2024-06-01T06:00:00+00:00"


# ---------------------------------------------------------------------------
# Row flatteners
# ---------------------------------------------------------------------------


class TestFlattenCycle:
    def test_full_record(self) -> None:
        record = {
            "id": 100,
            "user_id": 42,
            "start": "2024-06-01T00:00:00Z",
            "end": "2024-06-01T23:59:00Z",
            "timezone_offset": "-05:00",
            "score_state": "SCORED",
            "score": {
                "strain": 14.5,
                "kilojoule": 8500.0,
                "average_heart_rate": 62,
                "max_heart_rate": 175,
            },
        }
        row = _flatten_cycle(record, _LOADED_AT)
        assert row["id"] == 100
        assert row["score"]["strain"] == 14.5
        assert row["loaded_at"] == _LOADED_AT

    def test_missing_score_produces_none(self) -> None:
        record = {"id": 1, "user_id": 1}
        row = _flatten_cycle(record, _LOADED_AT)
        assert row["score"] is None

    def test_partial_score_fields(self) -> None:
        record = {"id": 1, "user_id": 1, "score": {"strain": 10.0}}
        row = _flatten_cycle(record, _LOADED_AT)
        assert row["score"]["strain"] == 10.0
        assert row["score"]["kilojoule"] is None


class TestFlattenSleep:
    def test_full_record(self) -> None:
        record = {
            "id": 200,
            "user_id": 42,
            "nap": False,
            "score_state": "SCORED",
            "score": {
                "stage_summary": {
                    "total_in_bed_time_milli": 28800000,
                    "total_awake_time_milli": 1200000,
                    "total_no_data_time_milli": 0,
                    "total_light_sleep_time_milli": 9000000,
                    "total_slow_wave_sleep_time_milli": 7200000,
                    "total_rem_sleep_time_milli": 5400000,
                    "sleep_cycle_count": 4,
                    "disturbance_count": 2,
                },
                "sleep_needed": {
                    "baseline_milli": 25200000,
                    "need_from_sleep_debt_milli": 1800000,
                    "need_from_recent_strain_milli": 900000,
                    "need_from_recent_nap_milli": 0,
                },
                "respiratory_rate": 15.2,
                "sleep_performance_percentage": 85.0,
                "sleep_consistency_percentage": 72.0,
                "sleep_efficiency_percentage": 91.0,
            },
        }
        row = _flatten_sleep(record, _LOADED_AT)
        assert row["id"] == 200
        assert row["score"]["respiratory_rate"] == 15.2
        assert row["score"]["stage_summary"]["sleep_cycle_count"] == 4
        assert row["loaded_at"] == _LOADED_AT

    def test_no_score_produces_none(self) -> None:
        row = _flatten_sleep({"id": 1, "user_id": 1}, _LOADED_AT)
        assert row["score"] is None


class TestFlattenRecovery:
    def test_full_record(self) -> None:
        record = {
            "cycle_id": 300,
            "sleep_id": 200,
            "user_id": 42,
            "created_at": "2024-06-01T07:00:00Z",
            "updated_at": "2024-06-01T07:05:00Z",
            "score_state": "SCORED",
            "score": {
                "user_calibrating": False,
                "recovery_score": 78.0,
                "resting_heart_rate": 52.0,
                "hrv_rmssd_milli": 62.5,
                "spo2_percentage": 98.0,
                "skin_temp_celsius": 34.1,
            },
        }
        row = _flatten_recovery(record, _LOADED_AT)
        assert row["cycle_id"] == 300
        assert row["score"]["recovery_score"] == 78.0
        assert row["loaded_at"] == _LOADED_AT

    def test_calibrating_user(self) -> None:
        record = {
            "cycle_id": 1,
            "user_id": 1,
            "score": {"user_calibrating": True, "recovery_score": None},
        }
        row = _flatten_recovery(record, _LOADED_AT)
        assert row["score"]["user_calibrating"] is True


class TestFlattenWorkout:
    def test_full_record(self) -> None:
        record = {
            "id": 400,
            "user_id": 42,
            "sport_id": 0,
            "score_state": "SCORED",
            "score": {
                "strain": 12.3,
                "average_heart_rate": 148,
                "max_heart_rate": 182,
                "kilojoule": 2800.0,
                "percent_recorded": 100.0,
                "distance_meter": 5000.0,
                "altitude_gain_meter": 50.0,
                "altitude_change_meter": 10.0,
                "zone_duration": {
                    "zone_zero_milli": 60000,
                    "zone_one_milli": 120000,
                    "zone_two_milli": 300000,
                    "zone_three_milli": 600000,
                    "zone_four_milli": 900000,
                    "zone_five_milli": 120000,
                },
            },
        }
        row = _flatten_workout(record, _LOADED_AT)
        assert row["id"] == 400
        assert row["score"]["strain"] == 12.3
        assert row["score"]["zone_duration"]["zone_five_milli"] == 120000

    def test_no_zones_in_score(self) -> None:
        record = {"id": 1, "user_id": 1, "score": {"strain": 5.0}}
        row = _flatten_workout(record, _LOADED_AT)
        assert row["score"]["zone_duration"] is None


# ---------------------------------------------------------------------------
# ingest_endpoint
# ---------------------------------------------------------------------------


class TestIngestEndpoint:
    def _make_mocks(
        self, records: list[dict], watermark: datetime | None = None
    ) -> tuple[MagicMock, MagicMock]:
        whoop = MagicMock()
        whoop.get_cycles.return_value = records

        bq = MagicMock()
        bq.get_watermark.return_value = watermark
        bq.insert_rows.return_value = len(records)

        return whoop, bq

    def test_success_returns_success_status(self) -> None:
        records = [{"id": 1, "user_id": 1, "score_state": "SCORED"}]
        whoop, bq = self._make_mocks(records)
        result = ingest_endpoint("cycles", whoop, bq, "whoop_raw", dry_run=False)
        assert result["status"] == "success"
        assert result["rows_fetched"] == 1
        assert result["rows_inserted"] == 1

    def test_dry_run_skips_insert(self) -> None:
        records = [{"id": 1, "user_id": 1}]
        whoop, bq = self._make_mocks(records)
        result = ingest_endpoint("cycles", whoop, bq, "whoop_raw", dry_run=True)
        bq.insert_rows.assert_not_called()
        assert result["rows_inserted"] == 0

    def test_watermark_passed_to_api(self) -> None:
        watermark = datetime(2024, 5, 1, tzinfo=timezone.utc)
        whoop, bq = self._make_mocks([], watermark=watermark)
        ingest_endpoint("cycles", whoop, bq, "whoop_raw", dry_run=False)
        whoop.get_cycles.assert_called_once_with(start=watermark)

    def test_full_load_when_no_watermark(self) -> None:
        whoop, bq = self._make_mocks([], watermark=None)
        ingest_endpoint("cycles", whoop, bq, "whoop_raw", dry_run=False)
        whoop.get_cycles.assert_called_once_with(start=None)

    def test_failed_fetch_returns_failed_status(self) -> None:
        whoop = MagicMock()
        whoop.get_cycles.side_effect = RuntimeError("API down")
        bq = MagicMock()
        bq.get_watermark.return_value = None

        result = ingest_endpoint("cycles", whoop, bq, "whoop_raw", dry_run=False)
        assert result["status"] == "failed"
        assert "API down" in result["error_msg"]
        assert result["rows_inserted"] == 0

    def test_run_id_is_uuid_string(self) -> None:
        whoop, bq = self._make_mocks([])
        result = ingest_endpoint("cycles", whoop, bq, "whoop_raw", dry_run=False)
        import uuid
        uuid.UUID(result["run_id"])  # raises ValueError if not valid UUID

    def test_no_rows_skips_insert(self) -> None:
        whoop, bq = self._make_mocks([])
        result = ingest_endpoint("cycles", whoop, bq, "whoop_raw", dry_run=False)
        bq.insert_rows.assert_not_called()
        assert result["rows_inserted"] == 0


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def _patch_pipeline(self, endpoint_statuses: list[str]) -> tuple:
        results = [
            {
                "run_id": f"run-{i}",
                "endpoint": "cycles",
                "started_at": "2024-01-01T06:00:00Z",
                "ended_at": "2024-01-01T06:01:00Z",
                "rows_fetched": 0,
                "rows_inserted": 0,
                "watermark_start": None,
                "watermark_end": None,
                "status": status,
                "error_msg": "err" if status == "failed" else None,
            }
            for i, status in enumerate(endpoint_statuses)
        ]
        return results

    def test_returns_0_on_full_success(self) -> None:
        with (
            patch("scripts.fetch.load_config"),
            patch("scripts.fetch.WhoopClient"),
            patch("scripts.fetch.BigQueryClient"),
            patch("scripts.fetch.ingest_endpoint") as mock_ingest,
        ):
            mock_ingest.side_effect = [
                {**r, "status": "success"}
                for r in self._patch_pipeline(["success"] * 4)
            ]
            exit_code = main([])
        assert exit_code == 0

    def test_returns_1_on_any_failure(self) -> None:
        results = self._patch_pipeline(["success", "failed", "success", "success"])
        with (
            patch("scripts.fetch.load_config"),
            patch("scripts.fetch.WhoopClient"),
            patch("scripts.fetch.BigQueryClient"),
            patch("scripts.fetch.ingest_endpoint", side_effect=results),
        ):
            exit_code = main([])
        assert exit_code == 1

    def test_dry_run_flag_passed_to_ingest(self) -> None:
        success = self._patch_pipeline(["success"] * 4)
        with (
            patch("scripts.fetch.load_config"),
            patch("scripts.fetch.WhoopClient"),
            patch("scripts.fetch.BigQueryClient"),
            patch("scripts.fetch.ingest_endpoint", side_effect=success) as mock_ingest,
        ):
            main(["--dry-run"])
        for call_args in mock_ingest.call_args_list:
            assert call_args.kwargs.get("dry_run") or call_args[1].get("dry_run") or call_args[0][4]

    def test_single_endpoint_flag(self) -> None:
        result = self._patch_pipeline(["success"])
        with (
            patch("scripts.fetch.load_config"),
            patch("scripts.fetch.WhoopClient"),
            patch("scripts.fetch.BigQueryClient"),
            patch("scripts.fetch.ingest_endpoint", side_effect=result) as mock_ingest,
        ):
            main(["--endpoint", "cycles"])
        assert mock_ingest.call_count == 1
        assert mock_ingest.call_args[0][0] == "cycles"
