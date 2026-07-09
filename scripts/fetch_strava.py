"""Strava ingest script: Strava API -> BigQuery (whoop_raw.raw_strava_runs).

Runs after fetch.py in the GitHub Actions ingest job, or independently via
`make fetch-strava`. Skips gracefully if Strava credentials are not configured.

What this script does:
  1. Check config.strava_configured; exit 0 with a log message if not set.
  2. Query BigQuery for the high-water mark (MAX(start_date) in raw_strava_runs).
  3. Fetch all runs from Strava API since that watermark (incremental load).
  4. Flatten API response fields into BigQuery-compatible row dicts.
  5. Append rows to raw_strava_runs (append-only; dedup happens in dbt staging).
  6. Log the run result to whoop_raw.pipeline_runs.

Exit code: 0 on full success or when Strava is unconfigured, 1 on failure.

Usage:
    python3.13 scripts/fetch_strava.py
    python3.13 scripts/fetch_strava.py --dry-run
    make fetch-strava
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
from utils.strava_client import StravaClient

logger = logging.getLogger(__name__)

_ENDPOINTS: dict[str, tuple[str, str, str]] = {
    "runs": ("get_runs", "raw_strava_runs", "start_date"),
}

_ALL_TABLES = [table for _, table, _ in _ENDPOINTS.values()]


# ---------------------------------------------------------------------------
# Row flattener
# ---------------------------------------------------------------------------

def _flatten_run(r: dict[str, Any], loaded_at: str) -> dict[str, Any]:
    """Map a raw Strava activity dict to a raw_strava_runs row.

    Strava returns all fields at the top level (no nested STRUCTs needed).
    Only runs are passed here; sport_type filtering happens in StravaClient.
    """
    return {
        "id": r.get("id"),
        "name": r.get("name"),
        "sport_type": r.get("sport_type"),
        "start_date": r.get("start_date"),
        "distance_meter": r.get("distance"),
        "moving_time_sec": r.get("moving_time"),
        "elapsed_time_sec": r.get("elapsed_time"),
        "total_elevation_gain_meter": r.get("total_elevation_gain"),
        "average_speed_ms": r.get("average_speed"),
        "max_speed_ms": r.get("max_speed"),
        "average_heartrate": r.get("average_heartrate"),
        "max_heartrate": r.get("max_heartrate"),
        "average_cadence": r.get("average_cadence"),
        "suffer_score": r.get("suffer_score"),
        "summary_polyline": (r.get("map") or {}).get("summary_polyline"),
        "loaded_at": loaded_at,
    }


_FLATTENERS = {
    "runs": _flatten_run,
}


# ---------------------------------------------------------------------------
# Core ingest logic
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def ingest_endpoint(
    endpoint: str,
    strava: StravaClient,
    bq: BigQueryClient,
    dataset_raw: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Fetch one Strava endpoint and append new records to BigQuery.

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
            "Ingesting Strava endpoint",
            extra={
                "endpoint": endpoint,
                "table": table,
                "watermark": watermark.isoformat() if watermark else "full_load",
                "dry_run": dry_run,
            },
        )

        fetch_fn = getattr(strava, method_name)
        records: list[dict[str, Any]] = fetch_fn(after=watermark)
        logger.info(
            "Records fetched from Strava API",
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
            "endpoint": f"strava_{endpoint}",
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
            "Strava endpoint ingest failed",
            extra={"endpoint": endpoint, "run_id": run_id},
        )
        return {
            "run_id": run_id,
            "endpoint": f"strava_{endpoint}",
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
        description="Fetch Strava runs and append to BigQuery (whoop_raw)."
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

    if not config.strava_configured:
        logger.info(
            "Strava credentials not configured; skipping Strava ingest. "
            "Set STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_ACCESS_TOKEN, "
            "and STRAVA_REFRESH_TOKEN to enable."
        )
        return 0

    strava = StravaClient(config)
    bq = BigQueryClient(config)

    bq.ensure_dataset(config.bq_dataset_raw)
    for table_name in _ALL_TABLES:
        bq.ensure_table(config.bq_dataset_raw, table_name)

    endpoints_to_run = [args.endpoint] if args.endpoint else list(_ENDPOINTS.keys())

    results: list[dict[str, Any]] = []
    for ep in endpoints_to_run:
        result = ingest_endpoint(ep, strava, bq, config.bq_dataset_raw, args.dry_run)
        results.append(result)
        if not args.dry_run:
            bq.log_pipeline_run(result)

    failed = [r for r in results if r["status"] == "failed"]
    if failed:
        logger.error(
            "Strava pipeline finished with failures",
            extra={"failed": [r["endpoint"] for r in failed]},
        )
        return 1

    logger.info(
        "Strava pipeline finished successfully",
        extra={
            "endpoints": [r["endpoint"] for r in results],
            "total_inserted": sum(r["rows_inserted"] for r in results),
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
