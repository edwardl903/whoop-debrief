"""Generate HTML route maps from Strava GPS data stored in BigQuery.

Reads fct_runs from whoop_dbt, decodes the summary_polyline column using the
Google Polyline Algorithm, and renders each route as an interactive Leaflet map
via folium. Output files are written to output/maps/.

Usage:
    python3.13 scripts/generate_route_maps.py
    python3.13 scripts/generate_route_maps.py --limit 10
    python3.13 scripts/generate_route_maps.py --out output/maps
    make route-maps

Requirements:
    pip install folium polyline   (included in requirements.txt)
"""
from __future__ import annotations

import argparse
import logging
import pathlib
from typing import Any

import folium
import polyline as polyline_lib

from utils.bq_client import BigQueryClient
from utils.config import load_config
from utils.logging_setup import configure_logging

logger = logging.getLogger(__name__)

_DEFAULT_OUT = pathlib.Path("output/maps")

# Tile layer for the map — OpenStreetMap (no API key needed)
_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
_TILE_ATTR = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
)


def _decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """Decode a Google Polyline string to a list of (lat, lng) tuples."""
    return polyline_lib.decode(encoded)


def _build_map(run: dict[str, Any]) -> folium.Map:
    """Build a folium map for a single run."""
    coords = _decode_polyline(run["summary_polyline"])

    # Centre the map on the midpoint of the route
    mid = coords[len(coords) // 2]
    m = folium.Map(location=mid, zoom_start=14, tiles=None)
    folium.TileLayer(_TILE_URL, attr=_TILE_ATTR, name="OpenStreetMap").add_to(m)

    # Route line
    folium.PolyLine(
        coords,
        color="#fc4c02",  # Strava orange
        weight=4,
        opacity=0.85,
    ).add_to(m)

    # Start marker (green) and end marker (red)
    folium.Marker(
        coords[0],
        popup="Start",
        icon=folium.Icon(color="green", icon="play"),
    ).add_to(m)
    folium.Marker(
        coords[-1],
        popup="Finish",
        icon=folium.Icon(color="red", icon="stop"),
    ).add_to(m)

    # Fit the map to the route bounds
    m.fit_bounds([[min(c[0] for c in coords), min(c[1] for c in coords)],
                  [max(c[0] for c in coords), max(c[1] for c in coords)]])

    # Popup tooltip with key stats
    pace = run.get("pace_min_per_km")
    pace_str = f"{pace:.2f} min/km" if pace else "n/a"
    dist = run.get("distance_km") or 0
    tooltip = (
        f"<b>{run.get('run_name', 'Run')}</b><br>"
        f"{run.get('run_date')}<br>"
        f"{dist:.2f} km | {pace_str}<br>"
        f"Recovery delta: {run.get('recovery_delta', 'n/a')}"
    )
    folium.map.Marker(mid, popup=folium.Popup(tooltip, max_width=200)).add_to(m)

    return m


def _fetch_runs(bq: BigQueryClient, limit: int | None) -> list[dict[str, Any]]:
    """Query fct_runs for runs that have a non-null summary_polyline."""
    dataset = bq._config.bq_dataset_dbt
    project = bq._config.bq_project
    limit_clause = f"LIMIT {limit}" if limit else ""

    query = f"""
        SELECT
            run_id,
            run_name,
            run_date,
            distance_km,
            pace_min_per_km,
            same_day_recovery,
            next_day_recovery,
            recovery_delta,
            summary_polyline
        FROM `{project}.{dataset}.fct_runs`
        WHERE summary_polyline IS NOT NULL
          AND summary_polyline != ''
        ORDER BY run_date DESC
        {limit_clause}
    """
    rows = list(bq._client.query(query).result())
    return [dict(row) for row in rows]


def main(argv: list[str] | None = None) -> int:
    configure_logging()

    parser = argparse.ArgumentParser(
        description="Generate HTML route maps from Strava runs in BigQuery."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Render only the N most recent runs (default: all).",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=_DEFAULT_OUT,
        metavar="DIR",
        help=f"Output directory for HTML files (default: {_DEFAULT_OUT}).",
    )
    args = parser.parse_args(argv)

    config = load_config()
    bq = BigQueryClient(config)

    runs = _fetch_runs(bq, args.limit)
    if not runs:
        logger.info("No runs with GPS data found in fct_runs. Nothing to render.")
        return 0

    logger.info("Fetched runs with polylines", extra={"count": len(runs)})

    out_dir: pathlib.Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    skipped = 0
    for run in runs:
        encoded = run.get("summary_polyline", "")
        if not encoded:
            skipped += 1
            continue

        try:
            m = _build_map(run)
        except Exception as exc:
            logger.warning(
                "Failed to render map",
                extra={"run_id": run["run_id"], "error": str(exc)},
            )
            skipped += 1
            continue

        run_date = str(run.get("run_date", "unknown"))
        run_id = run["run_id"]
        filename = out_dir / f"{run_date}_{run_id}.html"
        m.save(str(filename))
        generated += 1
        logger.info("Saved map", extra={"file": str(filename)})

    logger.info(
        "Route map generation complete",
        extra={"generated": generated, "skipped": skipped, "out_dir": str(out_dir)},
    )
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
