"""Centralized configuration loaded from environment variables.

All modules import from here. No module reads os.environ directly.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_REQUIRED = [
    "WHOOP_CLIENT_ID",
    "WHOOP_CLIENT_SECRET",
    "WHOOP_ACCESS_TOKEN",
    "WHOOP_REFRESH_TOKEN",
]


@dataclass(frozen=True)
class Config:
    # WHOOP OAuth 2.0
    whoop_client_id: str
    whoop_client_secret: str
    # Only needed for the initial browser OAuth flow (scripts/auth.py), not for fetch.
    whoop_redirect_uri: str | None
    whoop_access_token: str
    whoop_refresh_token: str

    # BigQuery
    bq_project: str
    bq_dataset_raw: str
    bq_dataset_dbt: str
    bq_location: str

    # GCP auth: one of these must be set.
    # google_credentials_json: full SA JSON as a string (GitHub Actions secret).
    # google_credentials_path: path to SA JSON file (local dev).
    google_credentials_json: str | None
    google_credentials_path: str | None


def _resolve_bq_project(creds_json: str | None) -> str | None:
    """BQ_PROJECT env var, or project_id from service account JSON."""
    project = os.getenv("BQ_PROJECT")
    if project:
        return project
    if creds_json:
        return json.loads(creds_json).get("project_id")
    return None


def load_config() -> Config:
    """Load and validate config from environment. Raises EnvironmentError on missing vars."""
    missing = [k for k in _REQUIRED if not os.getenv(k)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")

    creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_json and not creds_path:
        raise EnvironmentError(
            "Must set GOOGLE_APPLICATION_CREDENTIALS_JSON (Actions) "
            "or GOOGLE_APPLICATION_CREDENTIALS (local path)"
        )

    bq_project = _resolve_bq_project(creds_json)
    if not bq_project and creds_path:
        try:
            with open(creds_path, encoding="utf-8") as f:
                bq_project = json.load(f).get("project_id")
        except OSError:
            pass
    if not bq_project:
        raise EnvironmentError(
            "Missing BQ_PROJECT. Set the env var or include project_id in your "
            "service account JSON."
        )

    return Config(
        whoop_client_id=os.environ["WHOOP_CLIENT_ID"],
        whoop_client_secret=os.environ["WHOOP_CLIENT_SECRET"],
        whoop_redirect_uri=os.getenv("WHOOP_REDIRECT_URI"),
        whoop_access_token=os.environ["WHOOP_ACCESS_TOKEN"],
        whoop_refresh_token=os.environ["WHOOP_REFRESH_TOKEN"],
        bq_project=bq_project,
        bq_dataset_raw=os.getenv("BQ_DATASET_RAW", "whoop_raw"),
        bq_dataset_dbt=os.getenv("BQ_DATASET_DBT", "whoop_dbt"),
        bq_location=os.getenv("BQ_LOCATION", "us-central1"),
        google_credentials_json=creds_json,
        google_credentials_path=creds_path,
    )
