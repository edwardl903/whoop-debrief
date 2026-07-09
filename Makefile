.PHONY: auth strava-auth fetch fetch-strava fetch-all reset-tables route-maps dbt-run dbt-test dbt-deps dbt-seed dbt-snapshot dbt-freshness dbt-docs all lint format test

PYTHON ?= python3.13
export PYTHONPATH := .

DBT = scripts/dbt_with_env.sh

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

# dbt pipeline (--profiles-dir . picks up whoop_dbt/profiles.yml for local dev)
dbt-deps:
	cd whoop_dbt && dbt deps --profiles-dir .

dbt-run:
	$(DBT) run

dbt-test:
	$(DBT) test

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
