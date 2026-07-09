#!/usr/bin/env bash
# Load .env and resolve relative GCP key paths before running dbt.
# dbt reads env_var() from the shell, not .env, and runs from whoop_dbt/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

if [ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && [[ "${GOOGLE_APPLICATION_CREDENTIALS}" != /* ]]; then
    export GOOGLE_APPLICATION_CREDENTIALS="${ROOT}/${GOOGLE_APPLICATION_CREDENTIALS}"
fi

cd whoop_dbt
exec dbt "$@" --profiles-dir .
