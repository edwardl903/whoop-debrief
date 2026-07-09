"""BigQuery client for whoop-analytics.

All BigQuery interactions in the pipeline go through this module.
Never construct a bigquery.Client inline in scripts or models.

Responsibilities:
- Build the authenticated client (file-based creds or JSON string for Actions)
- Ensure datasets and tables exist with correct schemas
- Append rows to raw landing tables
- Query the high-water mark for incremental loading
- Log pipeline run metadata to whoop_raw.pipeline_runs
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from google.cloud import bigquery
from google.oauth2 import service_account

from utils.config import Config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BigQuery schema definitions for all raw tables.
# These mirror the WHOOP API v1 response shapes exactly.
# Nested fields use RECORD (STRUCT) mode to preserve the API structure.
# ---------------------------------------------------------------------------

_SCHEMAS: dict[str, list[bigquery.SchemaField]] = {
    "raw_cycles": [
        bigquery.SchemaField("id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("user_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("start", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("end", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("timezone_offset", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("score_state", "STRING", mode="NULLABLE"),
        bigquery.SchemaField(
            "score",
            "RECORD",
            mode="NULLABLE",
            fields=[
                bigquery.SchemaField("strain", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("kilojoule", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("average_heart_rate", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("max_heart_rate", "INTEGER", mode="NULLABLE"),
            ],
        ),
        bigquery.SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
    ],
    "raw_sleeps": [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("cycle_id", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("v1_id", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("user_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("start", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("end", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("timezone_offset", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("nap", "BOOL", mode="NULLABLE"),
        bigquery.SchemaField("score_state", "STRING", mode="NULLABLE"),
        bigquery.SchemaField(
            "score",
            "RECORD",
            mode="NULLABLE",
            fields=[
                bigquery.SchemaField(
                    "stage_summary",
                    "RECORD",
                    mode="NULLABLE",
                    fields=[
                        bigquery.SchemaField("total_in_bed_time_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("total_awake_time_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("total_no_data_time_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("total_light_sleep_time_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("total_slow_wave_sleep_time_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("total_rem_sleep_time_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("sleep_cycle_count", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("disturbance_count", "INTEGER", mode="NULLABLE"),
                    ],
                ),
                bigquery.SchemaField(
                    "sleep_needed",
                    "RECORD",
                    mode="NULLABLE",
                    fields=[
                        bigquery.SchemaField("baseline_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("need_from_sleep_debt_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("need_from_recent_strain_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("need_from_recent_nap_milli", "INTEGER", mode="NULLABLE"),
                    ],
                ),
                bigquery.SchemaField("respiratory_rate", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("sleep_performance_percentage", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("sleep_consistency_percentage", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("sleep_efficiency_percentage", "FLOAT64", mode="NULLABLE"),
            ],
        ),
        bigquery.SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
    ],
    "raw_recoveries": [
        bigquery.SchemaField("cycle_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("sleep_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("user_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("created_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("score_state", "STRING", mode="NULLABLE"),
        bigquery.SchemaField(
            "score",
            "RECORD",
            mode="NULLABLE",
            fields=[
                bigquery.SchemaField("user_calibrating", "BOOL", mode="NULLABLE"),
                bigquery.SchemaField("recovery_score", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("resting_heart_rate", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("hrv_rmssd_milli", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("spo2_percentage", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("skin_temp_celsius", "FLOAT64", mode="NULLABLE"),
            ],
        ),
        bigquery.SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
    ],
    "raw_workouts": [
        bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("v1_id", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("user_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("start", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("end", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("timezone_offset", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sport_id", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("sport_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("score_state", "STRING", mode="NULLABLE"),
        bigquery.SchemaField(
            "score",
            "RECORD",
            mode="NULLABLE",
            fields=[
                bigquery.SchemaField("strain", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("average_heart_rate", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("max_heart_rate", "INTEGER", mode="NULLABLE"),
                bigquery.SchemaField("kilojoule", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("percent_recorded", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("distance_meter", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("altitude_gain_meter", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField("altitude_change_meter", "FLOAT64", mode="NULLABLE"),
                bigquery.SchemaField(
                    "zone_duration",
                    "RECORD",
                    mode="NULLABLE",
                    fields=[
                        bigquery.SchemaField("zone_zero_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("zone_one_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("zone_two_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("zone_three_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("zone_four_milli", "INTEGER", mode="NULLABLE"),
                        bigquery.SchemaField("zone_five_milli", "INTEGER", mode="NULLABLE"),
                    ],
                ),
            ],
        ),
        bigquery.SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
    ],
    "raw_users": [
        bigquery.SchemaField("user_id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("email", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("first_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("last_name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
    ],
    # Strava API returns flat JSON (no nested STRUCTs needed).
    "raw_strava_runs": [
        bigquery.SchemaField("id", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sport_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("start_date", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("distance_meter", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("moving_time_sec", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("elapsed_time_sec", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("total_elevation_gain_meter", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("average_speed_ms", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("max_speed_ms", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("average_heartrate", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("max_heartrate", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("average_cadence", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("suffer_score", "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("summary_polyline", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("loaded_at", "TIMESTAMP", mode="REQUIRED"),
    ],
    "pipeline_runs": [
        bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("endpoint", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("started_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("ended_at", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("rows_fetched", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("rows_inserted", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("watermark_start", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("watermark_end", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("error_msg", "STRING", mode="NULLABLE"),
    ],
}


class BigQueryClient:
    """BigQuery wrapper for whoop-analytics. One instance per pipeline run."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._client = self._build_client()

    # ------------------------------------------------------------------ setup

    def _build_client(self) -> bigquery.Client:
        if self._config.google_credentials_json:
            creds_info = json.loads(self._config.google_credentials_json)
            creds = service_account.Credentials.from_service_account_info(
                creds_info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            return bigquery.Client(
                project=self._config.bq_project,
                credentials=creds,
                location=self._config.bq_location,
            )
        # Falls back to ADC (Application Default Credentials) for local dev
        # when GOOGLE_APPLICATION_CREDENTIALS points to the SA file.
        return bigquery.Client(
            project=self._config.bq_project,
            location=self._config.bq_location,
        )

    # ------------------------------------------------------ schema management

    def ensure_dataset(self, dataset_id: str) -> None:
        """Create dataset if it does not exist. Idempotent."""
        ref = bigquery.DatasetReference(self._config.bq_project, dataset_id)
        dataset = bigquery.Dataset(ref)
        dataset.location = self._config.bq_location
        self._client.create_dataset(dataset, exists_ok=True)
        logger.debug("Dataset ready", extra={"dataset": dataset_id})

    def ensure_table(self, dataset_id: str, table_id: str) -> None:
        """Create table with its schema if it does not exist. Idempotent."""
        schema = _SCHEMAS[table_id]
        ref = self._client.dataset(dataset_id).table(table_id)
        table = bigquery.Table(ref, schema=schema)
        self._client.create_table(table, exists_ok=True)
        logger.debug("Table ready", extra={"table": f"{dataset_id}.{table_id}"})

    # ---------------------------------------------------- incremental loading

    def get_watermark(
        self,
        dataset_id: str,
        table_id: str,
        column: str = "end",
    ) -> datetime | None:
        """Return MAX(column) from the table, or None if the table is empty.

        Used as the high-water mark for incremental fetch. The pipeline only
        requests records newer than this timestamp from the WHOOP API.
        """
        full_table = (
            f"`{self._config.bq_project}.{dataset_id}.{table_id}`"
        )
        query = f"SELECT MAX(`{column}`) AS watermark FROM {full_table}"
        rows = list(self._client.query(query).result())
        val = rows[0]["watermark"] if rows else None
        if val is None:
            return None
        if isinstance(val, datetime) and val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val

    # ----------------------------------------------------------------- writes

    def insert_rows(
        self,
        dataset_id: str,
        table_id: str,
        rows: list[dict[str, Any]],
    ) -> int:
        """Append rows to a table using the streaming insert API. Returns count inserted.

        Retries on NotFound errors, which can occur for ~30s after a table is
        created or recreated due to BigQuery streaming buffer propagation delay.
        """
        import time
        from google.api_core.exceptions import NotFound

        if not rows:
            logger.debug("No rows to insert", extra={"table": table_id})
            return 0

        ref = self._client.dataset(dataset_id).table(table_id)
        full = f"{dataset_id}.{table_id}"
        max_attempts = 6
        backoff = 5  # seconds between retries

        for attempt in range(1, max_attempts + 1):
            try:
                errors = self._client.insert_rows_json(ref, rows)
                if errors:
                    raise RuntimeError(
                        f"BigQuery streaming insert errors for {full}: {errors}"
                    )
                logger.info(
                    "Rows inserted",
                    extra={"table": full, "count": len(rows)},
                )
                return len(rows)
            except NotFound:
                if attempt == max_attempts:
                    raise
                wait = backoff * attempt
                logger.warning(
                    "Table not yet available after creation; retrying",
                    extra={"table": full, "attempt": attempt, "wait_sec": wait},
                )
                time.sleep(wait)

    def log_pipeline_run(self, run: dict[str, Any]) -> None:
        """Append a single run record to the pipeline_runs audit table."""
        self.insert_rows(self._config.bq_dataset_raw, "pipeline_runs", [run])
        logger.debug("Pipeline run logged", extra={"run_id": run.get("run_id")})
