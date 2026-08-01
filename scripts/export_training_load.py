"""Export training load data (CTL/ATL/TSB + weekly summary) to JSON.

Queries two BigQuery views and writes two files consumed by the portfolio:

  data/training_load.json  -- daily CTL/ATL/TSB from int_training_load
  data/weekly_summary.json -- weekly aggregate from fct_weekly_training_summary

Both files are committed back to the repo by GitHub Actions so the portfolio
can fetch them via jsDelivr without a backend:

  https://cdn.jsdelivr.net/gh/edwardl903/whoop-analytics@main/data/training_load.json

Usage:
    python scripts/export_training_load.py
    make export-training-load
"""
from __future__ import annotations

import json
import logging
import pathlib
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from utils.bq_client import BigQueryClient
from utils.config import load_bq_only_config
from utils.logging_setup import configure_logging

logger = logging.getLogger(__name__)

_DAILY_OUT  = pathlib.Path("data/training_load.json")
_WEEKLY_OUT = pathlib.Path("data/weekly_summary.json")

_DAILY_QUERY = """\
SELECT
    CAST(cycle_date AS STRING)  AS cycle_date,
    CAST(user_id    AS STRING)  AS user_id,
    daily_tss,
    strain_score,
    recovery_score,
    hrv_rmssd_milli,
    resting_heart_rate,
    ctl,
    atl,
    tsb,
    form_label,
    fitness_phase,
    ctl_7d_delta,
    training_monotony_7d
FROM `{project}.{dataset}.int_training_load`
ORDER BY cycle_date ASC
"""

_WEEKLY_QUERY = """\
SELECT
    CAST(week_start AS STRING)  AS week_start,
    CAST(week_end   AS STRING)  AS week_end,
    CAST(user_id    AS STRING)  AS user_id,
    tracked_days,
    total_weekly_tss,
    avg_daily_tss,
    week_end_ctl,
    week_end_atl,
    week_end_tsb,
    week_end_form,
    fitness_phase,
    avg_recovery,
    avg_hrv_rmssd,
    avg_rhr,
    avg_monotony,
    hard_days,
    easy_or_rest_days,
    run_count,
    total_distance_km,
    total_run_minutes,
    avg_pace_min_per_km,
    avg_run_hr,
    ctl_wow_delta,
    tss_wow_delta,
    distance_wow_delta_km,
    load_spike_flag
FROM `{project}.{dataset}.fct_weekly_training_summary`
ORDER BY week_start ASC
"""


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


def _run_query(bq: BigQueryClient, query: str) -> list[dict[str, Any]]:
    rows = list(bq._client.query(query).result())
    return [dict(row) for row in rows]


def main() -> int:
    configure_logging()
    config = load_bq_only_config()
    bq = BigQueryClient(config)
    project = bq._config.bq_project
    dataset = bq._config.bq_dataset_dbt
    now = datetime.now(timezone.utc).isoformat()

    # Daily CTL/ATL/TSB
    logger.info("Fetching daily training load from BigQuery")
    daily = _run_query(bq, _DAILY_QUERY.format(project=project, dataset=dataset))
    logger.info("Fetched daily rows", extra={"count": len(daily)})

    daily_payload: dict[str, Any] = {
        "generated_at": now,
        "row_count": len(daily),
        "description": (
            "Daily CTL/ATL/TSB training load metrics. "
            "CTL = 42-day EWMA fitness. ATL = 7-day EWMA fatigue. "
            "TSB = CTL - ATL (form). TSS derived from WHOOP strain (0-21) "
            "normalized to 0-100."
        ),
        "rows": daily,
    }

    _DAILY_OUT.parent.mkdir(parents=True, exist_ok=True)
    _DAILY_OUT.write_text(json.dumps(daily_payload, default=_json_default, indent=2))
    logger.info("Wrote daily training load", extra={"path": str(_DAILY_OUT)})

    # Weekly summary
    logger.info("Fetching weekly training summary from BigQuery")
    weekly = _run_query(bq, _WEEKLY_QUERY.format(project=project, dataset=dataset))
    logger.info("Fetched weekly rows", extra={"count": len(weekly)})

    weekly_payload: dict[str, Any] = {
        "generated_at": now,
        "row_count": len(weekly),
        "description": (
            "Weekly training summary: CTL/ATL/TSB end-of-week snapshots, "
            "run volume, recovery, and week-over-week deltas."
        ),
        "rows": weekly,
    }

    _WEEKLY_OUT.write_text(json.dumps(weekly_payload, default=_json_default, indent=2))
    logger.info("Wrote weekly summary", extra={"path": str(_WEEKLY_OUT)})

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
