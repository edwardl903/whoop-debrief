"""Export int_run_recovery to data/runs.json for the portfolio serve layer.

Queries BigQuery (whoop_dbt.int_run_recovery), serialises every column needed
by the portfolio gallery, and writes data/runs.json.  The file is committed
back to the repo by GitHub Actions so the portfolio can fetch it via jsDelivr
without a backend:

  https://cdn.jsdelivr.net/gh/edwardl903/whoop-analytics@main/data/runs.json

Usage:
    python scripts/export_runs_json.py
    make export-runs
"""
from __future__ import annotations

import json
import logging
import pathlib
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from utils.bq_client import BigQueryClient
from utils.config import load_config
from utils.logging_setup import configure_logging

logger = logging.getLogger(__name__)

_OUT = pathlib.Path("data/runs.json")

_QUERY = """\
SELECT
    CAST(run_id AS STRING)          AS run_id,
    run_name,
    sport_type,
    CAST(run_date AS STRING)        AS run_date,
    CAST(run_start AS STRING)       AS run_start,

    distance_km,
    moving_time_min,
    pace_min_per_km,
    avg_speed_kmh,
    total_elevation_gain_meter,
    run_avg_hr,
    run_max_hr,
    average_cadence,
    suffer_score,
    summary_polyline,

    same_day_strain,
    same_day_avg_hr,
    same_day_recovery,
    same_day_recovery_bucket,
    same_day_hrv,

    next_day_recovery,
    next_day_recovery_bucket,
    next_day_hrv,
    next_day_resting_hr,
    next_day_sleep_performance,
    next_day_sleep_hours,
    next_day_sleep_quality,

    recovery_delta,
    CAST(loaded_at AS STRING)       AS loaded_at

FROM `{project}.{dataset}.int_run_recovery`
ORDER BY run_date DESC
"""


def _json_default(obj: Any) -> Any:
    """Serialise types that json.dumps doesn't handle by default."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


def _fetch_runs(bq: BigQueryClient) -> list[dict[str, Any]]:
    project = bq._config.bq_project
    dataset = bq._config.bq_dataset_dbt
    query = _QUERY.format(project=project, dataset=dataset)
    rows = list(bq._client.query(query).result())
    return [dict(row) for row in rows]


def main() -> int:
    configure_logging()
    config = load_config()
    bq = BigQueryClient(config)

    logger.info("Fetching runs from BigQuery")
    runs = _fetch_runs(bq)
    logger.info("Fetched rows", extra={"count": len(runs)})

    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": len(runs),
        "runs": runs,
    }

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(payload, default=_json_default, indent=2))
    logger.info("Wrote JSON", extra={"path": str(_OUT), "runs": len(runs)})
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
