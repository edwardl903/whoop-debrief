.PHONY: auth fetch reset-tables dbt-run dbt-test all lint format test

PYTHON ?= python
export PYTHONPATH := .

# OAuth flow — run once to get tokens
auth:
	$(PYTHON) scripts/auth.py

# Fetch new data from WHOOP API (pass ARGS="--dry-run" to skip BigQuery writes)
fetch:
	$(PYTHON) scripts/fetch.py $(ARGS)

# Drop and recreate all raw tables (use when schemas change)
reset-tables:
	$(PYTHON) scripts/reset_tables.py

# dbt pipeline
dbt-run:
	cd whoop_dbt && dbt run

dbt-test:
	cd whoop_dbt && dbt test

dbt-seed:
	cd whoop_dbt && dbt seed

dbt-snapshot:
	cd whoop_dbt && dbt snapshot

# Full nightly pipeline
all: fetch dbt-seed dbt-snapshot dbt-run dbt-test

# Code quality
lint:
	ruff check .

format:
	ruff format .

test:
	pytest tests/ -v
