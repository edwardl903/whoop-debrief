#!/usr/bin/env bash
# Push API tokens from .env to GitHub Actions secrets.
# Run after `make auth` / `make strava-auth`, or any local fetch that refreshed tokens.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "No .env file found."
  exit 1
fi

# shellcheck disable=SC1091
source .env

# WHOOP — required for ingest job
for var in WHOOP_CLIENT_ID WHOOP_CLIENT_SECRET WHOOP_ACCESS_TOKEN WHOOP_REFRESH_TOKEN WHOOP_REDIRECT_URI; do
  val="${!var:-}"
  if [[ -z "$val" ]]; then
    echo "Missing $var in .env"
    exit 1
  fi
  echo "Setting secret: $var"
  gh secret set "$var" --body "$val"
done

# Strava — optional; skip if not configured
if [[ -n "${STRAVA_CLIENT_ID:-}" && -n "${STRAVA_ACCESS_TOKEN:-}" ]]; then
  for var in STRAVA_CLIENT_ID STRAVA_CLIENT_SECRET STRAVA_ACCESS_TOKEN STRAVA_REFRESH_TOKEN; do
    val="${!var:-}"
    if [[ -z "$val" ]]; then
      echo "Skipping Strava: missing $var in .env"
      continue
    fi
    echo "Setting secret: $var"
    gh secret set "$var" --body "$val"
  done
fi

echo "Done. Re-run the GitHub Actions workflow."
