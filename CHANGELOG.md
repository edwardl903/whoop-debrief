# Changelog

All notable changes to whoop-analytics are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

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
