# Changelog

All notable changes to WHOOP Debrief are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

---

## [0.4.0] — 2026-07-09 — Route maps, dbt docs on Pages, CI tightening

### Added

- `scripts/generate_route_maps.py` — decodes `summary_polyline` (Google Polyline
  Algorithm) from `fct_runs`, renders one interactive HTML map per run using folium,
  saves to `output/maps/`. Run with `make route-maps` or `make route-maps ARGS="--limit 10"`.
- `requirements.txt` — added `polyline` and `folium` for route map generation.
- `.github/workflows/dbt-docs.yml` — new workflow that runs `dbt docs generate`
  and deploys the static site to GitHub Pages on every push to main. Deploys to
  `https://edwardl903.github.io/whoop-analytics/`.
- `Makefile` — added `route-maps` target.
- `.gitignore` — added `output/` so generated map HTML files are not committed.

### Changed

- `whoop_dbt/models/intermediate/int_run_recovery.sql` — added `r.summary_polyline`
  to the SELECT; polyline now flows automatically into `fct_runs` via `select *`.
- `whoop_dbt/models/intermediate/schema.yml` — documented `summary_polyline` and
  `suffer_score` columns on `int_run_recovery`.
- `whoop_dbt/models/marts/schema.yml` — documented `summary_polyline` and
  `suffer_score` on `fct_runs`.
- `.github/workflows/pipeline.yml` — added `dbt source freshness` step after
  `dbt test` (`continue-on-error: true`); added `sources.json` to uploaded artifacts.
- `docs/mental-model.md` — full refresh: fixed API version references, updated
  pipeline diagram, updated open/resolved items table, added route maps and dbt
  docs to "where data lives".
- `docs/portfolio-story.md` — updated pitch, bullets, and talking points to
  reflect Strava integration, GPS routes, dbt docs, and serve layer status.
- `README.md` — updated architecture diagram, data model table (added Strava
  tables), setup instructions (added Strava OAuth section), "What's next" checklist.
- `.cursor/rules/no-auto-git.mdc` — added project-level rule: never auto-commit
  or auto-push without explicit request.

---

## [0.3.0] — 2026-07-09 — Strava integration

### Added

- `utils/strava_client.py` — Strava API v3 client: OAuth 2.0, page-based pagination,
  exponential backoff retry, token refresh on 401; `get_runs(after)` filters to
  Run/TrailRun/VirtualRun; `TokenRefreshError` and `StravaAPIError`
- `scripts/fetch_strava.py` — mirrors `fetch.py` structure; exits 0 gracefully
  when `config.strava_configured == False`
- `whoop_dbt/models/staging/stg_strava_runs.sql` — casts, renames, computes
  `distance_km`, `moving_time_min`, `pace_min_per_km` (via `SAFE_DIVIDE`),
  `avg_speed_kmh`; dedups by `run_id`; passes through `summary_polyline`
- `whoop_dbt/models/intermediate/int_run_recovery.sql` — joins each run to
  `int_daily_metrics` twice: same-day and next-day; derives `recovery_delta`
- `whoop_dbt/models/marts/fct_runs.sql` — incremental merge on `run_id`, 7-day
  rescan window
- `tests/test_strava_client.py`, `tests/test_fetch_strava.py` — 29 unit tests
- `scripts/auth.py` — refactored to support `--service whoop` and `--service strava`
- `Makefile` — added `strava-auth`, `fetch-strava`, `fetch-all` targets
- `.env.example` — added `STRAVA_*` vars

### Changed

- `utils/bq_client.py` — added `raw_strava_runs` schema including `summary_polyline`
- `utils/config.py` — added optional `strava_*` fields and `strava_configured` property
- `.github/workflows/pipeline.yml` — added Strava fetch step with `continue-on-error: true`

---

## [0.2.0] — 2026-07-09 — dbt layer

### Added

- `whoop_dbt/dbt_project.yml` — project config with per-layer materialization
- `whoop_dbt/packages.yml` — dbt-labs/dbt_utils dependency
- `whoop_dbt/profiles.yml` — local dev profile
- `whoop_dbt/models/staging/sources.yml` — `whoop_raw` source with freshness
  thresholds (warn 25h, error 49h)
- `whoop_dbt/models/staging/stg_raw_cycles.sql` — cast, rename, dedup
- `whoop_dbt/models/staging/stg_raw_sleeps.sql` — ms → hours, dedup
- `whoop_dbt/models/staging/stg_raw_recoveries.sql` — unpack STRUCT, dedup
- `whoop_dbt/models/staging/stg_raw_workouts.sql` — zone durations ms → minutes, dedup
- `whoop_dbt/models/intermediate/int_daily_metrics.sql` — joins cycle + recovery + sleep;
  derives `recovery_bucket` and `sleep_quality_label`
- `whoop_dbt/models/marts/fct_daily.sql` — incremental merge on `cycle_id`
- `whoop_dbt/models/marts/dim_user.sql` — full rebuild; lifetime averages + peaks
- `whoop_dbt/models/marts/my_trends.sql` — 7d/28d rolling averages, day-over-day deltas
- Full `schema.yml` files with `not_null` + `unique` tests on all PKs

---

## [0.1.0] — 2026-07-07 — Ingest layer

### Added

- `utils/config.py` — frozen `Config` dataclass, validates all required env vars
- `utils/logging_setup.py` — structured JSON logging; no `print()` calls anywhere
- `utils/whoop_client.py` — `WhoopClient` with OAuth 2.0, token refresh on 401,
  cursor-based pagination, exponential backoff retry
- `utils/bq_client.py` — `BigQueryClient` with raw table schemas, `get_watermark()`,
  `insert_rows()`, `log_pipeline_run()`
- `scripts/auth.py` — one-time OAuth 2.0 authorization code flow
- `scripts/fetch.py` — incremental ingest for all four WHOOP endpoints
- `tests/` — 51 unit tests, all I/O mocked
- `docs/portfolio-story.md`

### Changed

- Project named **WHOOP Debrief**; tagline: "What did your body learn last night?"
- WHOOP API migrated to v2 endpoints

---

## [0.0.1] — 2026-07-05 — Initial scaffold

### Added

- Folder structure, `.gitignore`, `.env.example`, `requirements.txt`, `Makefile`,
  `README.md`, GitHub Actions workflow, `docs/`, Cursor rules
