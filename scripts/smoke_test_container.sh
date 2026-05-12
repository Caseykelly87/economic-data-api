#!/usr/bin/env bash
# Containerized smoke test for the economic-data-api image.
#
# Default flow (no API_URL set):
#   1. Build the image and start the smoke compose stack (api + throwaway
#      postgres seeded with empty mart tables).
#   2. Poll /health until 200 or until a 60s timeout elapses.
#   3. Hit /health, /metrics/inflation, /anomalies?limit=1 and verify
#      response shapes.
#   4. Tear the stack down on any exit path (pass, fail, or interrupt).
#
# Override flow (API_URL=http://host:port set in the environment):
#   Skip build/up/down and run the endpoint checks against the given URL.
#   Useful for testing remote containers or a stack already running.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.smoke.yml"

API_URL="${API_URL:-http://localhost:8000}"
EXTERNAL_API=0
if [ -n "${API_URL_OVERRIDDEN:-}" ] || [ "${API_URL}" != "http://localhost:8000" ]; then
    EXTERNAL_API=1
fi

HEALTH_TIMEOUT_S=60
HEALTH_POLL_INTERVAL_S=2

PASS_COUNT=0
FAIL_COUNT=0
FAILURES=()

red()    { printf '\033[31m%s\033[0m' "$*"; }
green()  { printf '\033[32m%s\033[0m' "$*"; }
yellow() { printf '\033[33m%s\033[0m' "$*"; }

cleanup() {
    local exit_code=$?
    if [ "${EXTERNAL_API}" -eq 0 ]; then
        echo
        echo "Tearing down smoke stack..."
        docker compose -f "${COMPOSE_FILE}" down -v --remove-orphans >/dev/null 2>&1 || true
    fi
    exit "${exit_code}"
}
trap cleanup EXIT INT TERM

record_pass() {
    PASS_COUNT=$((PASS_COUNT + 1))
    echo "  $(green PASS) $1"
}

record_fail() {
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAILURES+=("$1")
    echo "  $(red FAIL) $1"
}

# ---------------------------------------------------------------------------
# Bring up the stack (skipped when running against an external URL).
# ---------------------------------------------------------------------------
if [ "${EXTERNAL_API}" -eq 0 ]; then
    echo "Building image and starting smoke stack..."
    docker compose -f "${COMPOSE_FILE}" build
    docker compose -f "${COMPOSE_FILE}" up -d

    echo "Polling ${API_URL}/health for up to ${HEALTH_TIMEOUT_S}s..."
    elapsed=0
    until curl --silent --fail --max-time 3 "${API_URL}/health" >/dev/null 2>&1; do
        if [ "${elapsed}" -ge "${HEALTH_TIMEOUT_S}" ]; then
            echo
            echo "$(red 'health never reached 200 within') ${HEALTH_TIMEOUT_S}s"
            echo "Last 50 log lines from the api container:"
            docker compose -f "${COMPOSE_FILE}" logs --tail=50 api || true
            exit 1
        fi
        sleep "${HEALTH_POLL_INTERVAL_S}"
        elapsed=$((elapsed + HEALTH_POLL_INTERVAL_S))
    done
    echo "API is healthy after ${elapsed}s."
fi

# ---------------------------------------------------------------------------
# Endpoint checks.
# ---------------------------------------------------------------------------
echo
echo "Running endpoint checks against ${API_URL}"

# /health
echo "GET /health"
HEALTH_RESP=$(curl --silent --show-error --max-time 5 -w '\n%{http_code}' "${API_URL}/health")
HEALTH_CODE="${HEALTH_RESP##*$'\n'}"
HEALTH_BODY="${HEALTH_RESP%$'\n'*}"
if [ "${HEALTH_CODE}" = "200" ]; then
    record_pass "status=200"
else
    record_fail "expected 200, got ${HEALTH_CODE} (body: ${HEALTH_BODY})"
fi
if echo "${HEALTH_BODY}" | grep -q '"status":"ok"'; then
    record_pass "body contains status=ok"
else
    record_fail "body missing status=ok (body: ${HEALTH_BODY})"
fi
if echo "${HEALTH_BODY}" | grep -q '"db":"connected"'; then
    record_pass "body contains db=connected"
else
    record_fail "body missing db=connected (body: ${HEALTH_BODY})"
fi

# /metrics/inflation — macro route, returns a JSON list (possibly empty
# against the smoke stack since the throwaway postgres has empty tables).
echo "GET /metrics/inflation"
INF_RESP=$(curl --silent --show-error --max-time 5 -w '\n%{http_code}' "${API_URL}/metrics/inflation")
INF_CODE="${INF_RESP##*$'\n'}"
INF_BODY="${INF_RESP%$'\n'*}"
if [ "${INF_CODE}" = "200" ]; then
    record_pass "status=200"
else
    record_fail "expected 200, got ${INF_CODE} (body: ${INF_BODY})"
fi
case "${INF_BODY}" in
    "["*"]")
        record_pass "body is a JSON array"
        ;;
    *)
        record_fail "body is not a JSON array (body: ${INF_BODY})"
        ;;
esac

# /anomalies — grocery route, served from bundled parquet fixtures.
# Envelope: {"total":..., "limit":..., "offset":..., "items":[...]}.
echo "GET /anomalies?limit=1"
ANO_RESP=$(curl --silent --show-error --max-time 5 -w '\n%{http_code}' "${API_URL}/anomalies?limit=1")
ANO_CODE="${ANO_RESP##*$'\n'}"
ANO_BODY="${ANO_RESP%$'\n'*}"
if [ "${ANO_CODE}" = "200" ]; then
    record_pass "status=200"
else
    record_fail "expected 200, got ${ANO_CODE} (body: ${ANO_BODY})"
fi
if echo "${ANO_BODY}" | grep -q '"items":\['; then
    record_pass "body contains items array"
else
    record_fail "body missing items array (body: ${ANO_BODY})"
fi
if echo "${ANO_BODY}" | grep -q '"total":'; then
    record_pass "body contains total"
else
    record_fail "body missing total (body: ${ANO_BODY})"
fi

# ---------------------------------------------------------------------------
# Summary.
# ---------------------------------------------------------------------------
echo
echo "Checks passed: ${PASS_COUNT}"
echo "Checks failed: ${FAIL_COUNT}"

if [ "${FAIL_COUNT}" -gt 0 ]; then
    echo
    echo "$(red 'SMOKE TEST FAILED')"
    for f in "${FAILURES[@]}"; do
        echo "  - ${f}"
    done
    exit 1
fi

echo
echo "$(green 'SMOKE TEST PASSED')"
