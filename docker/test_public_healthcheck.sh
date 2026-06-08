#!/usr/bin/env bash

set -euo pipefail

HOST="${1:-api.nursescheduling.org}"
HTTPS_URL="https://${HOST}/health"
HTTP_URL="http://${HOST}/health"

echo "🔒 Checking HTTPS health endpoint: ${HTTPS_URL}"
https_status="$(curl -fsS -o /dev/null -w "%{http_code}" "${HTTPS_URL}")"
if [[ "${https_status}" != "200" ]]; then
    echo "❌ ERROR: expected HTTPS /health to return 200, got ${https_status}" >&2
    exit 1
fi

echo "🚫 Checking HTTP health endpoint is not served directly: ${HTTP_URL}"
http_status="$(curl -sS -o /dev/null -w "%{http_code}" --max-redirs 0 "${HTTP_URL}" || true)"
if [[ "${http_status}" == "200" ]]; then
    echo "❌ ERROR: expected HTTP /health to fail or redirect, got 200" >&2
    exit 1
fi

echo "✅ OK: HTTPS /health returned 200 and HTTP /health returned ${http_status:-no response}."
