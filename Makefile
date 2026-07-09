.PHONY: auth fetch reset-tables dbt-run dbt-test all lint format test

PYTHON ?= python3.13
export PYTHONPATH := .

DBT = scripts/dbt_with_env.sh

# OAuth flow — run once to get tokens
auth:
	$(PYTHON) scripts/auth.py

# Fetch new data from WHOOP API (pass ARGS="--dry-run" to skip BigQuery writes)
fetch:
	$(PYTHON) scripts/fetch.py $(ARGS)

# Drop and recreate all raw tables (use when schemas change)
reset-tables:
	$(PYTHON) scripts/reset_tables.py

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
