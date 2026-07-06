# whoop-analytics

Personal WHOOP data engineering pipeline. Ingests daily recovery, sleep, strain, and workout data from the WHOOP API, lands raw responses in BigQuery, and transforms them into mart tables with dbt. Runs nightly via GitHub Actions.

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

Register an app at [developer.whoop.com](https://developer.whoop.com/), get client credentials, then:

```bash
make auth
# Opens browser for OAuth consent; writes tokens to .env
```

### 4. GCP credentials

Either drop your service account JSON at `gcp/service_account.json`, or set
`GOOGLE_APPLICATION_CREDENTIALS_JSON` in `.env` as a single-line JSON string.

### 5. Run the pipeline

```bash
make all        # fetch → load → dbt seed → dbt snapshot → dbt run → dbt test
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

- [ ] OAuth token refresh logic in `scripts/auth.py`
- [ ] Incremental fetch (high-water mark per endpoint from BigQuery)
- [ ] dbt staging models for all four raw tables
- [ ] `int_daily_metrics` joining cycle + recovery + sleep
- [ ] `fct_daily` incremental mart
- [ ] Serve layer (dashboard, portfolio page, or personal API)
