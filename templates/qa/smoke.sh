#!/usr/bin/env bash
# Post-deploy smoke: health endpoint + one critical read. Exits non-zero on the first
# failure so the deploy pipeline can halt or roll back.
#   BASE_URL=https://app.example.com SMOKE_PATH=/api/v1/albums bash smoke.sh
set -euo pipefail
: "${BASE_URL:?set BASE_URL}"
HEALTH_PATH="${HEALTH_PATH:-/health}"
SMOKE_PATH="${SMOKE_PATH:?set SMOKE_PATH to one critical read endpoint}"
TIMEOUT="${TIMEOUT:-10}"

code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" "$BASE_URL$HEALTH_PATH")
[ "$code" = "200" ] || { echo "smoke: health $HEALTH_PATH returned $code" >&2; exit 1; }

body=$(curl -sS --fail --max-time "$TIMEOUT" ${SMOKE_AUTH_HEADER:+-H "$SMOKE_AUTH_HEADER"} "$BASE_URL$SMOKE_PATH")
[ -n "$body" ] || { echo "smoke: $SMOKE_PATH returned an empty body" >&2; exit 1; }
echo "smoke: ok ($BASE_URL)"
