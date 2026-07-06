# Changelog

All notable changes to whoop-analytics are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
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
