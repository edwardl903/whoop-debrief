# WHOOP Debrief

Personal WHOOP data engineering pipeline. Every morning at 06:00 UTC, it debriefs your sensor: recovery, sleep, strain, and workouts from the WHOOP API into BigQuery, then transforms them into mart tables with dbt.

*Repo: `whoop-analytics` (rename to `whoop-debrief` on GitHub when ready)*

---

## Architecture

```
INGEST                        TRANSFORM                    SERVE
──────                        ─────────                    ─────

WHOOP API          ┌────────► BigQuery                  (planned)
(OAuth 2.0)        │          whoop_raw dataset
      │            │          raw_cycles         ──────► dbt run
      ▼            │          raw_sleeps                    │
scripts/fetch.py ──┘          raw_recoveries         stg_* views
      │                       raw_workouts               │
      ▼                                             int_* tables
GitHub Actions                                         │
cron 06:00 UTC                                   ┌─────┼──────┐
                                                 ▼     ▼      ▼
                                           fct_*  dim_*  mart tables
                                                             │
                                                      (dashboard / API)
```

**Raw-first:** WHOOP API responses land in BigQuery untransformed. All cleaning,
joining, and aggregation happens in dbt. This makes the pipeline replayable -- any
metric can be rebuilt from raw tables without re-calling the API.

---

## Pipeline schedule

GitHub Actions runs at 06:00 UTC daily. Ingest job fetches new data since the
last high-water mark, then the dbt job runs `dbt seed → dbt snapshot → dbt run → dbt test`.

Manual trigger available from the Actions UI.

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/edwardl903/whoop-analytics
cd whoop-analytics
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

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

### 4. GCP credentials

Either drop your service account JSON at `gcp/service_account.json`, or set
`GOOGLE_APPLICATION_CREDENTIALS_JSON` in `.env` as a single-line JSON string.

Set `BQ_PROJECT` in `.env` to your GCP project ID (or it is read from the service account JSON).

### 5. GitHub Actions secrets and variables

Repo → **Settings → Secrets and variables → Actions**

**Repository secrets** (sensitive):

| Secret | Value |
|--------|-------|
| `WHOOP_CLIENT_ID` | WHOOP developer dashboard |
| `WHOOP_CLIENT_SECRET` | WHOOP developer dashboard |
| `WHOOP_ACCESS_TOKEN` | From `.env` after `make auth` |
| `WHOOP_REFRESH_TOKEN` | From `.env` after `make auth` |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Full service account JSON |

`WHOOP_REDIRECT_URI` is required for token refresh in Actions:

| Secret | Value |
|--------|-------|
| `WHOOP_REDIRECT_URI` | `http://localhost:8080/callback` (must match WHOOP dashboard) |

**Token rotation trap:** WHOOP invalidates the old refresh token after every refresh. If you run `make fetch` locally, sync tokens to GitHub before the next scheduled run:

```bash
chmod +x scripts/sync_github_secrets.sh
./scripts/sync_github_secrets.sh
```

**Repository variables** (not secret — used by the dbt job):

| Variable | Value |
|----------|-------|
| `BQ_PROJECT` | Your GCP project ID, e.g. `my-whoop-project-123` |

The ingest job can also read `project_id` from the service account JSON if `BQ_PROJECT` is unset, but the dbt job still needs the variable.

### 6. Run the pipeline

```bash
make all        # fetch → dbt seed → dbt snapshot → dbt run → dbt test
make fetch      # ingest only
make dbt-run    # transform only
```

---

## Data model

| Table | Layer | Grain | Notes |
|-------|-------|-------|-------|
| `raw_cycles` | raw | one row per daily cycle | append-only |
| `raw_sleeps` | raw | one row per sleep record | append-only |
| `raw_recoveries` | raw | one row per recovery score | append-only |
| `raw_workouts` | raw | one row per workout | append-only |
| `stg_raw_cycles` | staging (view) | cycle | cast, rename, dedup |
| `stg_raw_sleeps` | staging (view) | sleep | cast, rename, dedup |
| `stg_raw_recoveries` | staging (view) | recovery | cast, rename, dedup |
| `stg_raw_workouts` | staging (view) | workout | cast, rename, dedup |
| `int_daily_metrics` | intermediate | date | join cycle + recovery + sleep |
| `fct_daily` | mart (incremental) | date | full daily fact, all metrics |
| `dim_user` | mart (table) | user | current stats, joined date, peak scores |
| `my_trends` | mart (table) | date | pre-aggregated for serve layer |

---

## Stack

| Layer | Tool |
|-------|------|
| Source | WHOOP API (OAuth 2.0) |
| Ingest | Python 3.13, requests, requests-oauthlib |
| Warehouse | Google BigQuery (dataset: `whoop_raw`) |
| Transform | dbt (BigQuery adapter, dataset: `whoop_dbt`) |
| Orchestration | GitHub Actions (cron 06:00 UTC) |
| Quality | dbt tests, pytest, ruff |

---

## What's next

- [x] OAuth token refresh in `utils/whoop_client.py`
- [x] Incremental fetch (high-water mark per endpoint from BigQuery)
- [ ] dbt staging models for all four raw tables
- [ ] `int_daily_metrics` joining cycle + recovery + sleep
- [ ] `fct_daily` incremental mart
- [ ] Serve layer (dashboard, portfolio page, or personal API)
