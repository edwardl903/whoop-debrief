# WHOOP Debrief

Personal WHOOP data engineering pipeline. Every morning at 06:00 UTC, it debriefs
your sensor: recovery, sleep, strain, and workouts from the WHOOP API, plus Strava
runs, into BigQuery, then transforms them into mart tables with dbt.

*Repo slug is `whoop-analytics`; will rename to `whoop-debrief` on GitHub when the portfolio page is ready.*

---

## Architecture

```
INGEST                         TRANSFORM                   SERVE
──────                         ─────────                   ─────

WHOOP API (OAuth 2.0)                                    (planned)
  /v2/cycle                                               dashboard or
  /v2/activity/sleep   ──────► BigQuery                   portfolio page
  /v2/recovery                 whoop_raw dataset
  /v2/activity/workout    ┌──► raw_cycles
      │                   │    raw_sleeps        ──────► dbt run
      ▼                   │    raw_recoveries              │
scripts/fetch.py ─────────┘    raw_workouts           stg_* views
                               raw_strava_runs              │
Strava API (OAuth 2.0)    ┌──► pipeline_runs         int_* tables
  /v3/athlete/activities  │                                 │
      │                   │                     ┌─────┬────┴──┐
      ▼                   │                     ▼     ▼       ▼
scripts/fetch_strava.py ──┘              fct_daily dim_user fct_runs
                                         my_trends
      │
      ▼
GitHub Actions
cron 06:00 UTC
```

**Raw-first:** WHOOP and Strava API responses land in BigQuery untransformed.
All cleaning, joining, and aggregation happens in dbt. The pipeline is fully
replayable — any metric can be rebuilt from raw tables without re-calling the API.

---

## Pipeline schedule

GitHub Actions runs at 06:00 UTC daily. Ingest fetches new data since the last
high-water mark, then the dbt job runs `dbt run → dbt test → dbt source freshness`.

Manual trigger is available from the Actions UI.

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/edwardl903/whoop-analytics
cd whoop-analytics
python3.13 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Use **Python 3.13** only. On this Mac, `python3` can resolve to 3.14 and dbt does
not support 3.14 yet.

### 2. Configure environment

```bash
cp .env.example .env
# Fill in WHOOP_CLIENT_ID, WHOOP_CLIENT_SECRET, and GCP credentials
```

### 3. WHOOP OAuth (one-time)

Register an app at [developer.whoop.com](https://developer.whoop.com/) with:

| Field | Value |
|-------|-------|
| Privacy Policy | https://www.edward-lai.com/whoop-debrief/privacy |
| Redirect URL | `http://localhost:8080/callback` (must match `WHOOP_REDIRECT_URI` in `.env`) |
| Scopes | `offline`, `read:recovery`, `read:cycles`, `read:sleep`, `read:workout`, `read:profile` |

Copy Client ID and Client Secret into `.env`, then:

```bash
make auth
# Opens browser for OAuth consent; writes tokens to .env
```

### 4. Strava OAuth (optional)

Register an app at [strava.com/settings/api](https://www.strava.com/settings/api) with
**Authorization Callback Domain** set to `localhost`. Copy Client ID and Secret into `.env`, then:

```bash
make strava-auth
# Opens browser for OAuth consent; writes tokens to .env
```

If Strava credentials are absent, the Strava fetch step skips gracefully.

### 5. GCP credentials

Either drop your service account JSON at `gcp/service_account.json`, or set
`GOOGLE_APPLICATION_CREDENTIALS_JSON` in `.env` as a single-line JSON string.

Set `BQ_PROJECT` in `.env` to your GCP project ID (or it is read from the service
account JSON automatically).

### 6. GitHub Actions secrets and variables

Repo → **Settings → Secrets and variables → Actions**

**Repository secrets** (sensitive):

| Secret | Value |
|--------|-------|
| `WHOOP_CLIENT_ID` | WHOOP developer dashboard |
| `WHOOP_CLIENT_SECRET` | WHOOP developer dashboard |
| `WHOOP_REDIRECT_URI` | `http://localhost:8080/callback` |
| `WHOOP_ACCESS_TOKEN` | From `.env` after `make auth` |
| `WHOOP_REFRESH_TOKEN` | From `.env` after `make auth` |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Full service account JSON (one line) |
| `STRAVA_CLIENT_ID` | Strava API settings (optional) |
| `STRAVA_CLIENT_SECRET` | Strava API settings (optional) |
| `STRAVA_ACCESS_TOKEN` | From `.env` after `make strava-auth` (optional) |
| `STRAVA_REFRESH_TOKEN` | From `.env` after `make strava-auth` (optional) |

**Repository variables** (not secret):

| Variable | Value |
|----------|-------|
| `BQ_PROJECT` | Your GCP project ID, e.g. `my-whoop-project-123` |

**Token rotation:** WHOOP invalidates the old refresh token after every refresh.
If you run `make fetch` locally, sync tokens to GitHub before the next scheduled run:

```bash
chmod +x scripts/sync_github_secrets.sh
./scripts/sync_github_secrets.sh
```

### 7. Run the pipeline

```bash
make all           # fetch + fetch-strava + dbt run + dbt test
make fetch         # WHOOP ingest only
make fetch-strava  # Strava ingest only
make dbt-run       # transform only
make route-maps    # decode GPS polylines, render HTML maps to output/maps/
```

---

## Data model

| Table | Layer | Grain | Notes |
|-------|-------|-------|-------|
| `raw_cycles` | raw | one row per daily cycle | append-only |
| `raw_sleeps` | raw | one row per sleep record | append-only |
| `raw_recoveries` | raw | one row per recovery score | append-only |
| `raw_workouts` | raw | one row per workout | append-only |
| `raw_strava_runs` | raw | one row per Strava run | append-only; includes GPS polyline |
| `pipeline_runs` | raw | one row per endpoint run | audit log |
| `stg_raw_cycles` | staging (view) | cycle | cast, rename, dedup |
| `stg_raw_sleeps` | staging (view) | sleep | cast, rename, dedup |
| `stg_raw_recoveries` | staging (view) | recovery | cast, rename, dedup |
| `stg_raw_workouts` | staging (view) | workout | cast, rename, dedup |
| `stg_strava_runs` | staging (view) | run | derived pace, distance, speed |
| `int_daily_metrics` | intermediate | date | cycle + recovery + sleep joined |
| `int_run_recovery` | intermediate | run | Strava run + same-day/next-day WHOOP |
| `fct_daily` | mart (incremental) | date | full daily fact, all metrics |
| `fct_runs` | mart (incremental) | run | run metrics + WHOOP context + GPS polyline |
| `dim_user` | mart (table) | user | lifetime stats, joined date, peak scores |
| `my_trends` | mart (table) | date | pre-aggregated for serve layer |

---

## Stack

| Layer | Tool |
|-------|------|
| Source | WHOOP API v2 (OAuth 2.0), Strava API v3 (OAuth 2.0) |
| Ingest | Python 3.13, requests, requests-oauthlib |
| Warehouse | Google BigQuery (`whoop_raw` raw, `whoop_dbt` marts) |
| Transform | dbt 1.11 (BigQuery adapter) |
| Orchestration | GitHub Actions (cron 06:00 UTC) |
| Quality | dbt tests + source freshness, pytest, ruff |
| Docs | dbt docs → GitHub Pages (auto-deployed on push to main) |

---

## What's next

- [x] OAuth token refresh in `utils/whoop_client.py`
- [x] Incremental fetch (high-water mark per endpoint)
- [x] dbt staging models for all raw tables
- [x] `int_daily_metrics` joining cycle + recovery + sleep
- [x] `fct_daily` incremental mart
- [x] Strava integration (ingest + dbt)
- [x] `summary_polyline` stored and surfaced through `fct_runs`
- [x] GPS route maps via `make route-maps` (folium + polyline)
- [x] dbt docs hosted on GitHub Pages
- [x] `dbt source freshness` in CI
- [ ] Serve layer (deciding between Streamlit and a custom dashboard)
- [ ] Rename repo to `whoop-debrief` + portfolio page link
