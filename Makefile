.PHONY: auth fetch load dbt-run dbt-test all lint format test

# OAuth flow — run once to get tokens
auth:
	python scripts/auth.py

# Fetch new data from WHOOP API
fetch:
	python scripts/fetch.py

# Load raw data to BigQuery
load:
	python scripts/load.py

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
all: fetch load dbt-seed dbt-snapshot dbt-run dbt-test

# Code quality
lint:
	ruff check .

format:
	ruff format .

test:
	pytest tests/ -v
