# Portfolio Story — WHOOP Debrief

> Reference this file when writing resume bullets, cover letters, portfolio copy,
> or answering "tell me about a project" in an interview. Keep it updated as the
> project evolves.

---

## Project identity

| Field | Value |
|-------|-------|
| **Name** | WHOOP Debrief |
| **Tagline** | What did your body learn last night? |
| **GitHub repo** | `whoop-analytics` today; rename to `whoop-debrief` when ready |
| **Privacy policy** | https://www.edward-lai.com/whoop-debrief/privacy |
| **OAuth redirect (local)** | `http://localhost:8080/callback` |
| **dbt docs site** | https://edwardl903.github.io/whoop-analytics/ |

**Why "Debrief":** Athletes and analysts debrief after the fact. This pipeline runs
at 06:00 UTC, reads overnight recovery and sleep, and turns raw API responses into
structured data you can query. It is methodical, scheduled, and runs whether you
open the app or not.

---

## The one-sentence pitch

WHOOP Debrief is an end-to-end personal health pipeline: WHOOP API and Strava
(OAuth 2.0) to BigQuery, transformed with dbt, orchestrated nightly on GitHub
Actions, with route map visualization from GPS polylines and a serve layer
in progress.

---

## The full narrative

I wear a WHOOP band and generate recovery, sleep, strain, and workout data every
day. The official app shows you charts, but it does not let you run your own
queries or build your own views. I wanted to own my data and answer questions
the app cannot answer, so I built a pipeline to pull it all into BigQuery and
model it with dbt.

The project is a production-grade personal pipeline, not a Jupyter notebook side
project. I applied the same patterns I use on real data team work:

- Raw data lands in an append-only BigQuery dataset (`whoop_raw`). Nothing is
  ever updated or deleted there. That makes reruns safe and audit trails clear.
- A `pipeline_runs` table logs every execution with start/end timestamps, row
  counts, watermark bounds, and error messages. If something breaks at 6 AM,
  I can see exactly what failed and why.
- Incremental loading uses `MAX(end)` as the high-water mark, so each nightly
  run only fetches records newer than what is already in BigQuery. No full
  reloads, no duplicates.
- OAuth 2.0 with automatic token refresh is built into the WHOOP API client.
  The token silently renews mid-run without crashing the pipeline.
- I added Strava integration using the same patterns: OAuth 2.0, page-based
  pagination, incremental watermark, BigQuery schema design. Strava runs are
  joined back to WHOOP daily metrics in dbt to answer questions like "did my
  recovery drop the morning after a long run?"
- GPS route shapes (`summary_polyline`) are stored in the raw and mart layers.
  A local script decodes them and renders interactive HTML maps with folium.
- dbt models follow a medallion architecture: staging views (rename, cast,
  dedup), intermediate tables that join data streams, and incremental fact and
  dimension tables for the serve layer.
- The whole thing runs on GitHub Actions on a cron at 06:00 UTC. dbt docs are
  auto-deployed to GitHub Pages on every push to main.

---

## Resume bullets

Use one or two of these. Pick the ones that match the job description.

**Impact / outcome framing (use for AE/DE roles):**

- Built an end-to-end personal health pipeline ingesting WHOOP wearable data and
  Strava runs via OAuth 2.0 into BigQuery, modeled with dbt (staging, intermediate,
  incremental facts), and orchestrated nightly on GitHub Actions.

- Implemented incremental high-water mark loading and a pipeline audit log table
  (`pipeline_runs`) to track row counts, watermarks, and run status for every
  execution, bringing production observability to a personal project.

**Technical depth framing (use for data engineering roles):**

- Designed an append-only raw landing zone in BigQuery with automatic OAuth 2.0
  token refresh, exponential backoff retry, paginated API ingestion (WHOOP + Strava),
  and structured JSON logging across all pipeline steps.

- Modeled six data streams in dbt: staging views with QUALIFY-based dedup,
  intermediate join layers (WHOOP + Strava), and incremental fact tables using
  BigQuery MERGE with a loaded_at watermark. Stored GPS route polylines through
  to the mart layer for downstream visualization.

**Short bullet (use when space is tight):**

- **WHOOP Debrief** — personal health pipeline: Python ingest (OAuth 2.0,
  incremental), BigQuery raw layer, dbt medallion transforms, Strava GPS routes,
  GitHub Actions.

---

## Interview talking points

**"Walk me through the architecture."**

> WHOOP and Strava both use OAuth 2.0. I wrote Python clients that handle token
> refresh automatically, paginate through API responses, and retry on transient
> errors with exponential backoff. The fetch scripts pull only new records using
> a high-water mark from BigQuery, append them to raw tables, and log every run
> to a `pipeline_runs` audit table. dbt runs downstream: staging views clean and
> dedup the raw data, intermediate models join WHOOP and Strava data together,
> and incremental fact tables give me the final metrics for visualization. GPS
> polylines from Strava flow all the way through to the mart layer so they are
> queryable and renderable.

**"Why BigQuery and dbt instead of something simpler?"**

> I could have written everything to a SQLite file and called it done in a day.
> But I wanted the project to demonstrate patterns I use in real work: a warehouse
> with proper dataset separation, incremental models, source freshness tests, and
> CI-driven transformation. If a recruiter or hiring manager looks at this, I want
> them to see the same decisions they would make on a real data team, not a toy
> project.

**"What would you do differently or what would you add?"**

> The main thing left is the serve layer. I ruled out Looker Studio since it does
> not help me build skills I want to develop professionally. I am deciding between
> a Streamlit app and something custom. The data is all clean and ready in
> `fct_daily`, `fct_runs`, and `my_trends` — the serve layer is just a consumer.
> Everything else, including dbt source freshness checks, GPS route maps, and
> auto-deployed dbt docs, is already in place.

**"How do you handle failures?"**

> Every endpoint run is logged to `pipeline_runs` with a status of `success` or
> `failed` and an error message if it failed. The fetch script exits with a non-zero
> code when any endpoint fails, which causes the GitHub Actions job to fail and
> sends a notification. The pipeline is idempotent: if it fails mid-run and
> retries, the high-water mark prevents duplicates. The Strava step has
> `continue-on-error: true` so a Strava token issue cannot block the WHOOP data.

---

## Skills demonstrated

| Skill | Where |
|-------|-------|
| OAuth 2.0 with token refresh | `utils/whoop_client.py`, `utils/strava_client.py` |
| Incremental loading (high-water mark) | `scripts/fetch.py`, `scripts/fetch_strava.py` |
| BigQuery schema design (STRUCT types) | `utils/bq_client.py` |
| dbt medallion architecture | `whoop_dbt/` |
| Pipeline observability (audit log) | `whoop_raw.pipeline_runs` |
| Structured JSON logging | `utils/logging_setup.py` |
| Exponential backoff retry | `utils/whoop_client.py`, `utils/strava_client.py` |
| GitHub Actions CI/CD (cron + manual dispatch) | `.github/workflows/pipeline.yml` |
| dbt source freshness tests | `whoop_dbt/models/staging/sources.yml` |
| dbt docs auto-deploy (GitHub Pages) | `.github/workflows/dbt-docs.yml` |
| GPS polyline decode + map rendering | `scripts/generate_route_maps.py` |
| pytest with mocks | `tests/` |
| Type hints throughout | all Python files |

---

## Tech stack (for copy-paste into portfolio page)

Python 3.13, WHOOP API v2, Strava API v3, BigQuery, dbt 1.11 (BigQuery adapter),
GitHub Actions, folium, polyline, ruff, pytest, google-cloud-bigquery, requests

---

## What is still in progress

- Serve layer: deciding between Streamlit and a custom dashboard (Looker Studio
  ruled out)
- Repo rename: `whoop-analytics` → `whoop-debrief` when portfolio page is ready

---

*Last updated: 2026-07-09*
