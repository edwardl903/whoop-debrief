#!/usr/bin/env bash
# Push WHOOP tokens from .env to GitHub Actions secrets.
# Run after `make auth` or any local fetch that refreshed tokens.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "No .env file found."
  exit 1
fi

# shellcheck disable=SC1091
source .env

for var in WHOOP_CLIENT_ID WHOOP_CLIENT_SECRET WHOOP_ACCESS_TOKEN WHOOP_REFRESH_TOKEN WHOOP_REDIRECT_URI; do
  val="${!var:-}"
  if [[ -z "$val" ]]; then
    echo "Missing $var in .env"
    exit 1
  fi
  echo "Setting secret: $var"
  gh secret set "$var" --body "$val"
done

echo "Done. Re-run the GitHub Actions workflow."
