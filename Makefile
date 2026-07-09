.PHONY: install auth strava-auth fetch fetch-strava fetch-all reset-tables route-maps export-runs dbt-run dbt-test dbt-deps dbt-seed dbt-snapshot dbt-freshness dbt-docs all lint format test

# Always python3.13 — dbt does not support 3.14. Install deps with `make install`
# (not plain `pip install` in a 3.14 venv, or Makefile targets won't see them).
PYTHON ?= python3.13
export PYTHONPATH := .

DBT = scripts/dbt_with_env.sh

# Install all Python deps into the same interpreter Makefile uses
install:
	$(PYTHON) -m pip install -r requirements.txt

# OAuth flow — run once per service to get tokens
auth:
	$(PYTHON) scripts/auth.py --service whoop

strava-auth:
	$(PYTHON) scripts/auth.py --service strava

# Fetch new data from WHOOP API (pass ARGS="--dry-run" to skip BigQuery writes)
fetch:
	$(PYTHON) scripts/fetch.py $(ARGS)

# Fetch new Strava runs (skips gracefully if STRAVA_* credentials not set)
fetch-strava:
	$(PYTHON) scripts/fetch_strava.py $(ARGS)

# Fetch both sources
fetch-all: fetch fetch-strava

# Drop and recreate all raw tables (use when schemas change)
reset-tables:
	$(PYTHON) scripts/reset_tables.py

# Decode Strava GPS polylines and render HTML route maps into output/maps/
# Pass ARGS="--limit 10" to render only the N most recent runs.
route-maps:
	$(PYTHON) scripts/generate_route_maps.py $(ARGS)

# Export int_run_recovery → data/runs.json for the portfolio static serve layer
export-runs:
	$(PYTHON) scripts/export_runs_json.py

# dbt pipeline (--profiles-dir . picks up whoop_dbt/profiles.yml for local dev)
dbt-deps:
	cd whoop_dbt && dbt deps --profiles-dir .

dbt-run:
	$(DBT) run $(ARGS)

dbt-test:
	$(DBT) test $(ARGS)

dbt-seed:
	$(DBT) seed

dbt-snapshot:
	$(DBT) snapshot

dbt-freshness:
	$(DBT) source freshness

dbt-docs:
	$(DBT) docs generate && $(DBT) docs serve

# Full nightly pipeline
all: fetch dbt-seed dbt-snapshot dbt-run dbt-test

# Code quality
lint:
	ruff check .

format:
	ruff format .

test:
	pytest tests/ -v
