"""Drop and recreate all raw tables in whoop_raw.

Use when BigQuery schemas change and existing tables are stale.
This deletes all raw data — only run when you intend a full reload.

Usage:
    make reset-tables
    python3.13 scripts/reset_tables.py
    python3.13 scripts/reset_tables.py --tables raw_sleeps raw_recoveries raw_workouts
"""
from __future__ import annotations

import argparse
import sys

from utils.bq_client import BigQueryClient, _SCHEMAS
from utils.config import load_config
from utils.logging_setup import configure_logging

import logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    configure_logging()

    parser = argparse.ArgumentParser(
        description="Drop and recreate raw tables in whoop_raw."
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        choices=list(_SCHEMAS.keys()),
        help="Tables to reset. Defaults to all raw data tables (not pipeline_runs).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    args = parser.parse_args(argv)

    tables = args.tables or [t for t in _SCHEMAS if t != "pipeline_runs"]

    config = load_config()
    bq = BigQueryClient(config)
    dataset = config.bq_dataset_raw

    logger.info("Tables to reset", extra={"dataset": dataset, "tables": tables})

    if not args.yes:
        confirm = input(
            f"\nThis will DELETE and recreate {tables} in {dataset}.\n"
            "All existing rows will be lost. Type 'yes' to continue: "
        ).strip()
        if confirm.lower() != "yes":
            print("Aborted.")
            return 0

    for table_id in tables:
        full = f"{config.bq_project}.{dataset}.{table_id}"
        table_ref = bq._client.dataset(dataset).table(table_id)
        try:
            bq._client.delete_table(table_ref, not_found_ok=True)
            logger.info("Dropped table", extra={"table": full})
        except Exception as e:
            logger.error("Failed to drop table", extra={"table": full, "error": str(e)})
            return 1

        try:
            bq.ensure_table(dataset, table_id)
            logger.info("Recreated table", extra={"table": full})
        except Exception as e:
            logger.error("Failed to recreate table", extra={"table": full, "error": str(e)})
            return 1

    logger.info("Reset complete. Run `make fetch` to reload data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
