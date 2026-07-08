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

**Why "Debrief":** Athletes and analysts debrief after the fact. This pipeline runs at 06:00 UTC, reads overnight recovery and sleep, and turns raw API responses into structured data you can query. It is methodical, scheduled, and runs whether you open the app or not.

---

## The one-sentence pitch

WHOOP Debrief is an end-to-end personal health pipeline: WHOOP API (OAuth 2.0) to
BigQuery, transformed with dbt, orchestrated nightly on GitHub Actions, with a
Streamlit dashboard for trend visualization (planned).

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
  run only fetches records that are newer than what is already in BigQuery. No
  full reloads, no duplicates.
- OAuth 2.0 with automatic token refresh is built into the WHOOP API client.
  The token silently renews mid-run without crashing the pipeline.
- dbt models follow a medallion architecture: staging views (rename, cast,
  dedup), an intermediate table that joins all four data streams on date, and
  incremental fact and dimension tables for the serve layer.
- The whole thing runs on GitHub Actions on a cron at 06:00 UTC with a manual
  dispatch option and a `--dry-run` flag for safe testing.

---

## Resume bullets

Use one or two of these. Pick the ones that match the job description.

**Impact / outcome framing (use for AE/DE roles):**

- Built a production-grade health data pipeline ingesting WHOOP wearable data
  (recovery, sleep, strain, workouts) via OAuth 2.0 into BigQuery, modeled with
  dbt (staging, intermediate, incremental facts), and orchestrated nightly on
  GitHub Actions.

- Implemented incremental high-water mark loading and a pipeline audit log table
  (`pipeline_runs`) to track row counts, watermarks, and run status for every
  execution, bringing production observability to a personal project.

**Technical depth framing (use for data engineering roles):**

- Designed an append-only raw landing zone in BigQuery with automatic OAuth 2.0
  token refresh, exponential backoff retry, paginated API ingestion, and
  structured JSON logging across all pipeline steps.

- Modeled four WHOOP data streams in dbt: staging views with QUALIFY-based
  dedup, an intermediate join layer, and incremental fact tables using BigQuery
  MERGE with a `loaded_at` watermark.

**Short bullet (use when space is tight):**

- **WHOOP Debrief** — personal health pipeline: Python ingest (OAuth 2.0,
  incremental), BigQuery raw layer, dbt medallion transforms, GitHub Actions.

---

## Interview talking points

**"Walk me through the architecture."**

> WHOOP API exposes health data behind OAuth 2.0. I wrote a Python client that
> handles token refresh automatically, paginates through the API responses, and
> retries on transient errors with exponential backoff. The fetch script pulls
> only new records using a high-water mark from BigQuery, appends them to raw
> tables, and logs the run to a `pipeline_runs` audit table. dbt then runs
> downstream: staging views clean and dedup the raw data, an intermediate model
> joins recovery, sleep, and cycle data on date, and fact tables give me the
> final metrics for visualization.

**"Why BigQuery and dbt instead of something simpler?"**

> I could have written everything to a SQLite file and called it done in a day.
> But I wanted the project to demonstrate patterns I use in real work: a
> warehouse with proper dataset separation, incremental models, source freshness
> tests, and CI-driven transformation. If a recruiter or hiring manager looks at
> this, I want them to see the same decisions they would make on a real data
> team, not a toy project.

**"What would you do differently or what would you add?"**

> A few things are still on the backlog. First, a proper serve layer, a
> Streamlit dashboard or Looker Studio connection, so the pipeline has a visible
> output for portfolio purposes. Second, dbt source freshness tests on the raw
> tables so the pipeline fails loudly if WHOOP data is stale. Third, I would
> consider adding a Prefect or Dagster DAG if the project grew beyond a single
> data source, since GitHub Actions starts to get unwieldy for complex
> dependencies.

**"How do you handle failures?"**

> Every endpoint run is logged to `pipeline_runs` with a status of `success` or
> `failed` and an error message if it failed. The fetch script exits with a
> non-zero code when any endpoint fails, which causes the GitHub Actions job to
> fail and send a notification. The pipeline is also idempotent: if it fails
> mid-run and retries, the high-water mark means it will not duplicate records.

---

## Skills demonstrated

| Skill | Where |
|-------|-------|
| OAuth 2.0 with token refresh | `utils/whoop_client.py` |
| Incremental loading (high-water mark) | `scripts/fetch.py`, `utils/bq_client.py` |
| BigQuery schema design (STRUCT types, nested records) | `utils/bq_client.py` |
| dbt medallion architecture | `whoop_dbt/` |
| Pipeline observability (audit log) | `whoop_raw.pipeline_runs` |
| Structured JSON logging | `utils/logging_setup.py` |
| Exponential backoff retry | `utils/whoop_client.py` |
| GitHub Actions CI/CD (cron + manual dispatch) | `.github/workflows/pipeline.yml` |
| pytest with mocks | `tests/` |
| Type hints throughout | all Python files |

---

## Tech stack (for copy-paste into portfolio page)

Python 3.13, WHOOP API v1, BigQuery, dbt (BigQuery adapter), GitHub Actions,
ruff, pytest, google-cloud-bigquery, requests

---

## What is still planned (honest scope)

- Serve layer: Streamlit dashboard or Looker Studio connection
- dbt source freshness tests
- dbt documentation site (hosted via GitHub Pages)
- Alert if pipeline has not run in 25+ hours

---

*Last updated: 2026-07-07 — project named WHOOP Debrief*
