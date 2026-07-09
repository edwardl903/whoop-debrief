# Cursor AI Workflow — WHOOP Debrief

Read this before making any change. Update it after every session.

---

## Rules (must follow every prompt)

### Before touching any file
1. Read this file first.
2. Read `docs/mental-model.md` for the full pipeline picture.
3. Read the actual file(s) being edited before editing them.
4. For SQL or dbt, check existing models before adding duplicate logic.

### While editing
- Python 3.13 only.
- All BigQuery calls go through the shared client in `utils/bq_client.py`, never inline.
- All WHOOP API calls go through `utils/whoop_client.py` (handles token refresh).
- Raw tables are append-only. Never UPDATE or DELETE from `whoop_raw.*`.
- dbt layer conventions: `stg_*` = view (clean only), `int_*` = table/view (business logic), `fct_*` = incremental mart.
- No hardcoded credentials, project IDs, or dataset names. Use env vars or `utils/config.py`.
- No em dashes in comments or docs.
- No `!important` in any CSS if a serve layer gets built.

### After editing
- Run `make lint` (ruff) and `make test` (pytest) to confirm zero errors.
- Update the **Recent Changes** section of this file with a one-line summary.
- Append an entry to `CHANGELOG.md`.
- If the pipeline architecture changed, update `docs/mental-model.md`.

### Committing
Write detailed commit messages:
1. What changed (specific files and components)
2. Why (the prompt intent)
3. Any notable trade-offs

Example:
```
feat(ingest): add incremental fetch with BigQuery high-water mark

Edward wanted the daily pipeline to skip re-fetching data already
in BigQuery. Added get_max_end_time() in utils/bq_client.py and
wired it into scripts/fetch.py so each endpoint only pulls since
the last uploaded_at.

Files: scripts/fetch.py, utils/bq_client.py
```

---

## Project State (keep current)

| Item | Current value |
|------|---------------|
| Warehouse | BigQuery (`whoop_raw` = raw, `whoop_dbt` = dbt marts) |
| GCP project | [FILL IN after setup] |
| dbt project | `whoop_dbt/` |
| Pipeline schedule | GitHub Actions, 06:00 UTC daily |
| Auth | WHOOP OAuth 2.0; tokens in `.env` (gitignored) |
| Python version | 3.13 |
| Status | WHOOP + Strava ingest complete — dbt models implemented |

---

## Pre-Edit Checklist

```
[ ] Read cursor-workflow.md
[ ] Read docs/mental-model.md
[ ] Read the actual files being changed
[ ] Check existing utils before adding new helpers
[ ] Run make lint + make test after
[ ] Update Recent Changes log
[ ] Append entry to CHANGELOG.md
[ ] Update docs/mental-model.md if pipeline changed
```

---

## Recent Changes

| Date | Change |
|------|--------|
| 2026-07-09 | Strava integration: utils/strava_client.py, scripts/fetch_strava.py, stg_strava_runs, int_run_recovery, fct_runs; 81 tests pass |
| 2026-07-09 | dbt layer complete: 4 staging models, int_daily_metrics, fct_daily (incremental), dim_user, my_trends + full schema.yml tests + sources.yml freshness |
| 2026-07-07 | Migrated WHOOP client to API v2 (v1 paths 404 for sleep/recovery/workout); fixed `_ALL_TABLES` KeyError |
| 2026-07-07 | Project named **WHOOP Debrief**; README, portfolio-story, docs updated |
| 2026-07-07 | Ingest layer implemented: utils/config.py, utils/logging_setup.py, utils/whoop_client.py, utils/bq_client.py, scripts/auth.py, scripts/fetch.py, tests/ (51 tests, 0 failures). docs/portfolio-story.md added. |
| 2026-07-05 | Initial scaffold: folder structure, .gitignore, .env.example, requirements.txt, Makefile, README, GitHub Actions workflow, docs, Cursor rules |
