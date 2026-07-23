"""Main ingest script: WHOOP API -> BigQuery (whoop_raw).

Runs nightly via GitHub Actions at 06:00 UTC. Can also be triggered manually
with --dry-run to validate without writing.

What this script does per endpoint:
  1. Query BigQuery for the high-water mark (MAX of the end or updated_at column)
  2. Fetch all WHOOP records newer than the watermark (incremental load)
  3. Flatten nested API response fields into BigQuery-compatible row dicts
  4. Append rows to the raw table (append-only; dedup happens in dbt staging)
  5. Log the run result to whoop_raw.pipeline_runs

Exit code: 0 on full success, 1 if any endpoint fails.

Usage:
    python3.13 scripts/fetch.py
    python3.13 scripts/fetch.py --dry-run
    python3.13 scripts/fetch.py --endpoint cycles
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from utils.bq_client import BigQueryClient
from utils.config import load_config
from utils.logging_setup import configure_logging
from utils.whoop_client import WhoopClient

logger = logging.getLogger(__name__)

# Maps CLI endpoint name -> (WhoopClient method, raw table, watermark column).
# The watermark column is what we MAX() in BigQuery to find the last loaded record.
_ENDPOINTS: dict[str, tuple[str, str, str]] = {
    "cycles": ("get_cycles", "raw_cycles", "end"),
    "sleeps": ("get_sleeps", "raw_sleeps", "end"),
    "recoveries": ("get_recoveries", "raw_recoveries", "updated_at"),
    "workouts": ("get_workouts", "raw_workouts", "end"),
}

# All BigQuery tables managed by this script (raw data + audit log).
# raw_users is not in _ENDPOINTS (single call, no watermark) but still needs ensure_table.
_ALL_TABLES = [table for _, table, _ in _ENDPOINTS.values()] + ["pipeline_runs", "raw_users"]


# ---------------------------------------------------------------------------
# Row flatteners: map raw WHOOP API dicts into BigQuery-schema-compatible dicts
# ---------------------------------------------------------------------------

def _flatten_cycle(r: dict[str, Any], loaded_at: str) -> dict[str, Any]:
    score = r.get("score") or {}
    return {
        "id": r.get("id"),
        "user_id": r.get("user_id"),
        "start": r.get("start"),
        "end": r.get("end"),
        "timezone_offset": r.get("timezone_offset"),
        "score_state": r.get("score_state"),
        "score": {
            "strain": score.get("strain"),
            "kilojoule": score.get("kilojoule"),
            "average_heart_rate": score.get("average_heart_rate"),
            "max_heart_rate": score.get("max_heart_rate"),
        } if score else None,
        "loaded_at": loaded_at,
    }


def _flatten_sleep(r: dict[str, Any], loaded_at: str) -> dict[str, Any]:
    score = r.get("score") or {}
    stage = score.get("stage_summary") or {}
    needed = score.get("sleep_needed") or {}
    return {
        "id": r.get("id"),
        "cycle_id": r.get("cycle_id"),
        "v1_id": r.get("v1_id"),
        "user_id": r.get("user_id"),
        "start": r.get("start"),
        "end": r.get("end"),
        "timezone_offset": r.get("timezone_offset"),
        "nap": r.get("nap"),
        "score_state": r.get("score_state"),
        "score": {
            "stage_summary": {
                "total_in_bed_time_milli": stage.get("total_in_bed_time_milli"),
                "total_awake_time_milli": stage.get("total_awake_time_milli"),
                "total_no_data_time_milli": stage.get("total_no_data_time_milli"),
                "total_light_sleep_time_milli": stage.get("total_light_sleep_time_milli"),
                "total_slow_wave_sleep_time_milli": stage.get("total_slow_wave_sleep_time_milli"),
                "total_rem_sleep_time_milli": stage.get("total_rem_sleep_time_milli"),
                "sleep_cycle_count": stage.get("sleep_cycle_count"),
                "disturbance_count": stage.get("disturbance_count"),
            },
            "sleep_needed": {
                "baseline_milli": needed.get("baseline_milli"),
                "need_from_sleep_debt_milli": needed.get("need_from_sleep_debt_milli"),
                "need_from_recent_strain_milli": needed.get("need_from_recent_strain_milli"),
                "need_from_recent_nap_milli": needed.get("need_from_recent_nap_milli"),
            },
            "respiratory_rate": score.get("respiratory_rate"),
            "sleep_performance_percentage": score.get("sleep_performance_percentage"),
            "sleep_consistency_percentage": score.get("sleep_consistency_percentage"),
            "sleep_efficiency_percentage": score.get("sleep_efficiency_percentage"),
        } if score else None,
        "loaded_at": loaded_at,
    }


def _flatten_recovery(r: dict[str, Any], loaded_at: str) -> dict[str, Any]:
    score = r.get("score") or {}
    return {
        "cycle_id": r.get("cycle_id"),
        "sleep_id": r.get("sleep_id"),
        "user_id": r.get("user_id"),
        "created_at": r.get("created_at"),
        "updated_at": r.get("updated_at"),
        "score_state": r.get("score_state"),
        "score": {
            "user_calibrating": score.get("user_calibrating"),
            "recovery_score": score.get("recovery_score"),
            "resting_heart_rate": score.get("resting_heart_rate"),
            "hrv_rmssd_milli": score.get("hrv_rmssd_milli"),
            "spo2_percentage": score.get("spo2_percentage"),
            "skin_temp_celsius": score.get("skin_temp_celsius"),
        } if score else None,
        "loaded_at": loaded_at,
    }


def _flatten_workout(r: dict[str, Any], loaded_at: str) -> dict[str, Any]:
    score = r.get("score") or {}
    zones = score.get("zone_durations") or score.get("zone_duration") or {}
    return {
        "id": r.get("id"),
        "v1_id": r.get("v1_id"),
        "user_id": r.get("user_id"),
        "start": r.get("start"),
        "end": r.get("end"),
        "timezone_offset": r.get("timezone_offset"),
        "sport_id": r.get("sport_id"),
        "sport_name": r.get("sport_name"),
        "score_state": r.get("score_state"),
        "score": {
            "strain": score.get("strain"),
            "average_heart_rate": score.get("average_heart_rate"),
            "max_heart_rate": score.get("max_heart_rate"),
            "kilojoule": score.get("kilojoule"),
            "percent_recorded": score.get("percent_recorded"),
            "distance_meter": score.get("distance_meter"),
            "altitude_gain_meter": score.get("altitude_gain_meter"),
            "altitude_change_meter": score.get("altitude_change_meter"),
            "zone_duration": {
                "zone_zero_milli": zones.get("zone_zero_milli"),
                "zone_one_milli": zones.get("zone_one_milli"),
                "zone_two_milli": zones.get("zone_two_milli"),
                "zone_three_milli": zones.get("zone_three_milli"),
                "zone_four_milli": zones.get("zone_four_milli"),
                "zone_five_milli": zones.get("zone_five_milli"),
            } if zones else None,
        } if score else None,
        "loaded_at": loaded_at,
    }


_FLATTENERS = {
    "cycles": _flatten_cycle,
    "sleeps": _flatten_sleep,
    "recoveries": _flatten_recovery,
    "workouts": _flatten_workout,
}


# ---------------------------------------------------------------------------
# Core ingest logic
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def ingest_user_profile(
    whoop: WhoopClient,
    bq: BigQueryClient,
    dataset_raw: str,
    dry_run: bool,
) -> None:
    """Fetch the user's basic profile and append one snapshot row to raw_users.

    Profile rarely changes, but we insert on every run so the staging model
    can always dedup to the freshest snapshot. No watermark needed.
    """
    profile = whoop.get_user_profile()
    loaded_at = _utcnow().isoformat()
    row: dict[str, Any] = {
        "user_id": profile.get("user_id"),
        "email": profile.get("email"),
        "first_name": profile.get("first_name"),
        "last_name": profile.get("last_name"),
        "loaded_at": loaded_at,
    }
    if dry_run:
        logger.info(
            "Dry run: skipping raw_users insert",
            extra={"user_id": row["user_id"]},
        )
    else:
        bq.insert_rows(dataset_raw, "raw_users", [row])
        logger.info("User profile inserted", extra={"user_id": row["user_id"]})


def ingest_endpoint(
    endpoint: str,
    whoop: WhoopClient,
    bq: BigQueryClient,
    dataset_raw: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Fetch one WHOOP endpoint and append new records to BigQuery.

    Returns a pipeline_runs row dict regardless of success or failure.
    The caller is responsible for writing that row to BigQuery.
    """
    method_name, table, watermark_col = _ENDPOINTS[endpoint]
    run_id = str(uuid.uuid4())
    started_at = _utcnow()
    watermark: datetime | None = None

    try:
        watermark = bq.get_watermark(dataset_raw, table, watermark_col)
        logger.info(
            "Ingesting endpoint",
            extra={
                "endpoint": endpoint,
                "table": table,
                "watermark": watermark.isoformat() if watermark else "full_load",
                "dry_run": dry_run,
            },
        )

        fetch_fn = getattr(whoop, method_name)
        records: list[dict[str, Any]] = fetch_fn(start=watermark)
        logger.info(
            "Records fetched from API",
            extra={"endpoint": endpoint, "count": len(records)},
        )

        loaded_at = _utcnow().isoformat()
        flattener = _FLATTENERS[endpoint]
        rows = [flattener(rec, loaded_at) for rec in records]

        inserted = 0
        if dry_run:
            logger.info(
                "Dry run: skipping BigQuery insert",
                extra={"endpoint": endpoint, "rows_would_insert": len(rows)},
            )
        elif rows:
            inserted = bq.insert_rows(dataset_raw, table, rows)

        return {
            "run_id": run_id,
            "endpoint": endpoint,
            "started_at": started_at.isoformat(),
            "ended_at": _utcnow().isoformat(),
            "rows_fetched": len(records),
            "rows_inserted": inserted,
            "watermark_start": watermark.isoformat() if watermark else None,
            "watermark_end": loaded_at,
            "status": "success",
            "error_msg": None,
        }

    except Exception:
        logger.exception(
            "Endpoint ingest failed",
            extra={"endpoint": endpoint, "run_id": run_id},
        )
        return {
            "run_id": run_id,
            "endpoint": endpoint,
            "started_at": started_at.isoformat(),
            "ended_at": _utcnow().isoformat(),
            "rows_fetched": 0,
            "rows_inserted": 0,
            "watermark_start": watermark.isoformat() if watermark else None,
            "watermark_end": None,
            "status": "failed",
            "error_msg": str(sys.exc_info()[1]),
        }


def main(argv: list[str] | None = None) -> int:
    configure_logging()

    parser = argparse.ArgumentParser(
        description="Fetch WHOOP data and append to BigQuery (whoop_raw)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch from the API but do not write to BigQuery.",
    )
    parser.add_argument(
        "--endpoint",
        choices=list(_ENDPOINTS.keys()),
        help="Run a single endpoint only. Defaults to all endpoints.",
    )
    args = parser.parse_args(argv)

    config = load_config()
    whoop = WhoopClient(config)
    bq = BigQueryClient(config)

    # Ensure all raw tables exist before any fetch begins
    bq.ensure_dataset(config.bq_dataset_raw)
    for table_name in _ALL_TABLES:
        bq.ensure_table(config.bq_dataset_raw, table_name)

    # User profile: always fetch on a full run (not filterable by --endpoint).
    # Runs before the incremental endpoints so the user row exists in BigQuery
    # before dbt staging references it.
    if not args.endpoint:
        try:
            ingest_user_profile(whoop, bq, config.bq_dataset_raw, args.dry_run)
        except Exception:
            logger.exception("User profile ingest failed; continuing with other endpoints")

    endpoints_to_run = [args.endpoint] if args.endpoint else list(_ENDPOINTS.keys())

    results: list[dict[str, Any]] = []
    for ep in endpoints_to_run:
        result = ingest_endpoint(ep, whoop, bq, config.bq_dataset_raw, args.dry_run)
        results.append(result)
        if not args.dry_run:
            bq.log_pipeline_run(result)

    failed = [r for r in results if r["status"] == "failed"]

    # Write rotated tokens to a file so the CI step can push them back to
    # GitHub Secrets. This must happen before we return so the file exists
    # even when some endpoints fail after a successful refresh.
    if whoop.tokens_refreshed:
        import os
        tokens_out = os.environ.get("WHOOP_TOKENS_OUT", "/tmp/whoop_tokens.env")
        with open(tokens_out, "w") as fh:
            fh.write(f"WHOOP_ACCESS_TOKEN={whoop.access_token}\n")
            fh.write(f"WHOOP_REFRESH_TOKEN={whoop.refresh_token}\n")
        logger.info(
            "Wrote rotated tokens to file for secret rotation",
            extra={"path": tokens_out},
        )

    if failed:
        logger.error(
            "Pipeline finished with failures",
            extra={"failed": [r["endpoint"] for r in failed]},
        )
        return 1

    logger.info(
        "Pipeline finished successfully",
        extra={
            "endpoints": [r["endpoint"] for r in results],
            "total_inserted": sum(r["rows_inserted"] for r in results),
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
