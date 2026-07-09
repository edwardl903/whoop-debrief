# Changelog

All notable changes to whoop-analytics are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added (2026-07-09 — Strava integration)

- `utils/strava_client.py` — Strava API v3 client: OAuth 2.0 Bearer auth, page-based pagination (`page` + `per_page`), exponential backoff retry, token refresh on 401; `get_runs(after)` filters to Run/TrailRun/VirtualRun client-side; `TokenRefreshError` and `StravaAPIError` for typed error handling
- `scripts/fetch_strava.py` — mirrors `fetch.py` structure: `_flatten_run`, `ingest_endpoint`, `main` with `--dry-run` / `--endpoint`; exits 0 gracefully when `config.strava_configured == False`
- `whoop_dbt/models/staging/stg_strava_runs.sql` — casts, renames, computes `distance_km`, `moving_time_min`, `pace_min_per_km` (via `SAFE_DIVIDE`), `avg_speed_kmh`; dedups by `run_id`
- `whoop_dbt/models/intermediate/int_run_recovery.sql` — joins each run to `int_daily_metrics` twice: same-day (strain context) and next-day (`date_add(run_date, interval 1 day)` for recovery impact); derives `recovery_delta` = next_day_recovery minus same_day_recovery
- `whoop_dbt/models/marts/fct_runs.sql` — incremental merge on `run_id`, 7-day rescan window; all run metrics plus WHOOP context columns
- `tests/test_strava_client.py`, `tests/test_fetch_strava.py` — 29 unit tests: pagination, sport-type filter, token refresh, dry-run, unconfigured-skip behavior; all 81 total tests pass
- `scripts/auth.py` — refactored to support `--service whoop` (default) and `--service strava`; common `_run_oauth_flow` helper eliminates duplication
- `Makefile` — added `strava-auth`, `fetch-strava`, `fetch-all` targets
- `.env.example` — added `STRAVA_*` vars with setup notes
- `.github/workflows/pipeline.yml` — added "Run Strava fetch" step to ingest job; passes `STRAVA_*` secrets; step is a no-op when secrets are absent

### Added (2026-07-09 — dbt layer)

- `whoop_dbt/dbt_project.yml` — project config with per-layer materialization (staging: view, intermediate: table, marts: table)
- `whoop_dbt/packages.yml` — dbt-labs/dbt_utils dependency
- `whoop_dbt/profiles.yml` — local dev profile using `env_var('BQ_PROJECT')` and service account keyfile; CI still generates its own profile in pipeline.yml
- `whoop_dbt/models/staging/sources.yml` — `whoop_raw` source declaration with `loaded_at_field` and freshness thresholds (warn 25h, error 49h)
- `whoop_dbt/models/staging/stg_raw_cycles.sql` — casts, renames, unpacks score STRUCT, dedups by cycle_id
- `whoop_dbt/models/staging/stg_raw_sleeps.sql` — ms durations → hours, stage summary unpacked, dedups by sleep UUID
- `whoop_dbt/models/staging/stg_raw_recoveries.sql` — score STRUCT unpacked, dedups by cycle_id
- `whoop_dbt/models/staging/stg_raw_workouts.sql` — zone durations ms → minutes, score STRUCT unpacked, dedups by workout UUID
- `whoop_dbt/models/staging/schema.yml` — not_null + unique tests on all staging PKs
- `whoop_dbt/models/intermediate/int_daily_metrics.sql` — joins cycles + recoveries + primary sleep (non-nap) on cycle_id; derives recovery_bucket (peak/optimal/poor) and sleep_quality_label (excellent/good/fair/poor)
- `whoop_dbt/models/intermediate/schema.yml` — not_null + unique tests on cycle_id
- `whoop_dbt/models/marts/fct_daily.sql` — incremental merge on cycle_id; re-scans last 7 days to catch WHOOP rescores
- `whoop_dbt/models/marts/dim_user.sql` — full rebuild; lifetime averages + peaks per user
- `whoop_dbt/models/marts/my_trends.sql` — full rebuild; 7-day and 28-day rolling averages for recovery, strain, sleep, HRV; day-over-day deltas for trend indicators
- `whoop_dbt/models/marts/schema.yml` — not_null + unique tests on all mart PKs
- `Makefile` — added `dbt-deps`, `dbt-freshness`, `dbt-docs` targets; all dbt targets now pass `--profiles-dir .` for local dev

### Changed (2026-07-07)

- Project named **WHOOP Debrief** (tagline: "What did your body learn last night?"); branding updated in README, portfolio-story, docs, and Cursor rules. GitHub repo slug remains `whoop-analytics` until renamed.

### Added (2026-07-07 — ingest layer)

- `utils/config.py` — frozen `Config` dataclass loaded from env vars; validates all required vars on startup with a clear error message
- `utils/logging_setup.py` — `configure_logging()` that emits structured JSON logs (timestamp, level, logger, message, extras); all pipeline modules use `logging.getLogger(__name__)`, no `print()` calls
- `utils/whoop_client.py` — `WhoopClient` with OAuth 2.0 Bearer auth, automatic access token refresh on 401, cursor-based pagination, and urllib3 exponential backoff retry (429/5xx); `TokenRefreshError` and `WhoopAPIError` for typed error handling
- `utils/bq_client.py` — `BigQueryClient` with BigQuery STRUCT schemas for all raw tables (`raw_cycles`, `raw_sleeps`, `raw_recoveries`, `raw_workouts`, `raw_users`, `pipeline_runs`); `ensure_dataset()`, `ensure_table()`, `get_watermark()`, `insert_rows()`, `log_pipeline_run()`
- `scripts/auth.py` — one-time OAuth 2.0 authorization code flow; opens browser, listens on localhost callback, exchanges code for tokens, writes to `.env` with `set_key()`
- `scripts/fetch.py` — main ingest entrypoint; for each endpoint: gets high-water mark from BigQuery, fetches since watermark, flattens nested WHOOP API response, appends to raw table, logs to `pipeline_runs`; `--dry-run` and `--endpoint` flags; exits 1 if any endpoint fails
- `tests/test_whoop_client.py`, `tests/test_bq_client.py`, `tests/test_fetch.py` — 51 unit tests covering pagination, token refresh, API errors, watermark queries, insert behavior, row flatteners, and CLI behavior; all external I/O mocked
- `docs/portfolio-story.md` — portfolio narrative, resume bullets, interview talking points, and skills demonstrated table for job applications

### Added (initial scaffold)
- Initial scaffold: `scripts/`, `utils/`, `tests/`, `notebooks/`, `data/`, `whoop_dbt/` folder structure
- `.gitignore` covering secrets, data files, Python artifacts, dbt targets
- `.env.example` with all required vars (WHOOP OAuth, BigQuery, GCP)
- `requirements.txt` (pandas, google-cloud-bigquery, dbt-bigquery, requests-oauthlib, ruff, pytest)
- `Makefile` with `auth`, `fetch`, `load`, `dbt-run`, `dbt-test`, `all`, `lint`, `format`, `test` targets
- `README.md` with architecture diagram, setup instructions, data model table, and backlog
- `.github/workflows/pipeline.yml` — Daily WHOOP Pipeline (06:00 UTC cron, ingest job + dbt job with `needs: ingest`, manual `workflow_dispatch` with dry-run flag)
- `docs/cursor-workflow.md` — required pre-edit reading, project state table, Recent Changes log
- `docs/mental-model.md` — full pipeline map, dbt lineage, data sources, env var reference, GCP resources, key conventions, open items
- `.cursor/rules/whoop-cursor.mdc` — always-on AI rules for this repo (stack, hard rules, dbt conventions, post-edit checklist)
