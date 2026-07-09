# WHOOP Debrief — Mental Model

> Read this when you need to re-orient. It describes the full pipeline, how the
> pieces connect, and why decisions were made. Update it whenever the architecture
> changes in a meaningful way.

---

## The big picture in one sentence

Pull daily health metrics (recovery, sleep, strain, workouts) from the WHOOP API,
land raw responses in BigQuery, and transform them into clean mart tables with dbt
running nightly on GitHub Actions.

---

## Pipeline phases

```
INGEST                        TRANSFORM                    SERVE
──────                        ─────────                    ─────

WHOOP API (OAuth 2.0)         BigQuery                  (planned)
  /v1/cycle                   whoop_raw dataset
  /v1/sleep                     raw_cycles
  /v1/recovery       ──────►    raw_sleeps       ──────► dbt run
  /v1/workout                   raw_recoveries              │
  /v1/user                      raw_workouts          stg_* (views)
        │                       raw_users                   │
        ▼                     append-only             int_daily_metrics
  scripts/fetch.py                                          │
        │                                           fct_daily (incremental)
        ▼                                           dim_user (table)
  GitHub Actions                                    my_trends (table)
  cron 06:00 UTC                                          │
  daily_ingest job                               (dashboard / portfolio page)
        │
        ▼
  dbt job (needs: ingest)
    dbt seed
    dbt snapshot
    dbt run
    dbt test
```

---

## Data sources (WHOOP API v2)

| Endpoint | What it returns | Raw table |
|----------|----------------|-----------|
| `GET /v2/cycle` | Daily strain cycle (start/end, strain score, calories, avg/max HR) | `raw_cycles` |
| `GET /v2/activity/sleep` | Sleep record (stages, efficiency, respiratory rate, duration) | `raw_sleeps` |
| `GET /v2/recovery` | Recovery score (%, HRV, resting HR, SpO2, skin temp) | `raw_recoveries` |
| `GET /v2/activity/workout` | Workout (sport type, duration, strain, HR zones) | `raw_workouts` |
| `GET /v2/user/profile/basic` | User profile (name, join date) | `raw_users` |

All endpoints support `start` / `end` date params for incremental fetch.

## Data sources (Strava API v3)

| Endpoint | What it returns | Raw table |
|----------|----------------|-----------|
| `GET /v3/athlete/activities` | All activities; filtered client-side to Run/TrailRun/VirtualRun | `raw_strava_runs` |

Strava uses page-based pagination (`?after=<epoch>&page=N&per_page=50`).
Strava credentials are optional — the WHOOP pipeline runs even if `STRAVA_*` env vars are absent.

---

## dbt model lineage

```
SOURCE (WHOOP)                   SOURCE (Strava)
whoop_raw.raw_cycles             whoop_raw.raw_strava_runs
whoop_raw.raw_sleeps                     │
whoop_raw.raw_recoveries                 │
whoop_raw.raw_workouts                   │
        │                                │
        ▼  STAGING (views)               ▼  STAGING (view)
stg_raw_cycles               stg_strava_runs
stg_raw_sleeps                 pace, distance_km,
stg_raw_recoveries             speed conversions
stg_raw_workouts
        │                                │
        ▼  INTERMEDIATE (table)          │
int_daily_metrics  ◄─────────────────────┤
  cycle + recovery + sleep               │
  recovery_bucket + sleep_quality_label  │
        │                                │
        │              ◄─── int_run_recovery (table)
        │                    run + same-day WHOOP
        │                    + next-day recovery
        │                    recovery_delta derived
        │
        ├────────────────┬──────────────────────┐
        ▼                ▼                      ▼
MARTS (incremental)  DIMENSION (full)      MART (incremental)
fct_daily            dim_user              fct_runs
  grain: date          1 row/user            grain: run_id
        │             averages+peaks
        ▼
my_trends (full rebuild)
  7d/28d rolling averages
  day-over-day deltas
```

---

## Where data lives

| Store | Dataset / Table | Written by | Read by |
|-------|----------------|-----------|---------|
| BigQuery | `whoop_raw.raw_cycles` | scripts/fetch.py | dbt staging |
| BigQuery | `whoop_raw.raw_sleeps` | scripts/fetch.py | dbt staging |
| BigQuery | `whoop_raw.raw_recoveries` | scripts/fetch.py | dbt staging |
| BigQuery | `whoop_raw.raw_workouts` | scripts/fetch.py | dbt staging |
| BigQuery | `whoop_dbt.stg_*` | dbt | dbt intermediate |
| BigQuery | `whoop_dbt.int_daily_metrics` | dbt | dbt marts |
| BigQuery | `whoop_dbt.fct_daily` | dbt | serve layer |
| BigQuery | `whoop_dbt.dim_user` | dbt | serve layer |
| BigQuery | `whoop_dbt.my_trends` | dbt | serve layer |
| BigQuery | `whoop_raw.raw_strava_runs` | scripts/fetch_strava.py | dbt staging |
| BigQuery | `whoop_dbt.stg_strava_runs` | dbt | dbt intermediate |
| BigQuery | `whoop_dbt.int_run_recovery` | dbt | dbt marts |
| BigQuery | `whoop_dbt.fct_runs` | dbt | serve layer |
| BigQuery | `whoop_raw.pipeline_runs` | scripts/fetch.py, fetch_strava.py | audit log |

---

## Environment variables

| Var | Used by | Notes |
|-----|---------|-------|
| `WHOOP_CLIENT_ID` | scripts/auth.py, utils/whoop_client.py | WHOOP app credentials |
| `WHOOP_CLIENT_SECRET` | scripts/auth.py, utils/whoop_client.py | WHOOP app credentials |
| `WHOOP_ACCESS_TOKEN` | utils/whoop_client.py | Written after OAuth; rotate via refresh |
| `WHOOP_REFRESH_TOKEN` | utils/whoop_client.py | Used to get new access token |
| `STRAVA_CLIENT_ID` | scripts/auth.py, utils/strava_client.py | Optional; Strava app credentials |
| `STRAVA_CLIENT_SECRET` | scripts/auth.py, utils/strava_client.py | Optional |
| `STRAVA_ACCESS_TOKEN` | utils/strava_client.py | Written by `make strava-auth` |
| `STRAVA_REFRESH_TOKEN` | utils/strava_client.py | Static; does not rotate |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | utils/bq_client.py | Full SA JSON (GitHub Actions) |
| `GOOGLE_APPLICATION_CREDENTIALS` | utils/bq_client.py | Path to SA file (local dev) |
| `BQ_PROJECT` | utils/bq_client.py, utils/config.py | GCP project ID |
| `BQ_DATASET_RAW` | utils/config.py | Default: `whoop_raw` |
| `BQ_DATASET_DBT` | utils/config.py | Default: `whoop_dbt` |
| `BQ_LOCATION` | utils/bq_client.py | Default: `us-central1` |

---

## GCP resources

| Resource | Value |
|----------|-------|
| Project | [FILL IN after setup] |
| Region | `us-central1` (must match ChessLytics to reuse service account) |
| Dataset (raw) | `whoop_raw` |
| Dataset (dbt) | `whoop_dbt` |
| Service account | `gcp/service_account.json` (gitignored) |

---

## Key conventions (do not break)

1. Raw tables are **append-only** — never UPDATE/DELETE from `whoop_raw.*`
2. All WHOOP API calls through `utils/whoop_client.py` — handles token refresh automatically
3. All BigQuery calls through `utils/bq_client.py` — never inline client construction
4. Python 3.13 only
5. BigQuery region always `us-central1` — using `US` multi-region causes dataset-not-found errors
6. dbt models write to `whoop_dbt`; raw ingest writes to `whoop_raw`
7. Incremental fetch: always use `MAX(uploaded_at)` from BigQuery as the high-water mark, not wall clock time
8. No credentials in code — env vars only

---

## Open items / known debt

| Issue | Priority | Notes |
|-------|----------|-------|
| GCP project ID not configured | High | Fill in after first GCP setup |
| Serve layer undefined | Low | Decide: portfolio page, personal dashboard, or API |
| dbt docs site | Low | `make dbt-docs` generates locally; GitHub Pages hosting not yet wired |

### Resolved

| Issue | Resolved | Notes |
|-------|----------|-------|
| Strava integration not built | 2026-07-09 | utils/strava_client.py, fetch_strava.py, stg_strava_runs, int_run_recovery, fct_runs |
| dbt staging models not written | 2026-07-09 | All 4 stg_* models + int_daily_metrics + fct_daily + dim_user + my_trends |
| dbt source freshness tests | 2026-07-09 | warn_after 25h / error_after 49h in sources.yml |
| OAuth token refresh not implemented | 2026-07-07 | Implemented in utils/whoop_client.py — auto-refreshes on 401 |
| Incremental fetch logic not implemented | 2026-07-07 | MAX(watermark_col) from BigQuery in utils/bq_client.get_watermark() |

---

## How to update this file

- **Pipeline change** (new endpoint, new table, new dbt model): update the system map and "where data lives" table
- **New env var**: add to the environment variables table
- **Debt resolved**: remove from open items, add to CHANGELOG.md
- **New feature / serve layer**: add routes or consumers to the system map

---

*Last updated: 2026-07-09 — Strava integration added*
