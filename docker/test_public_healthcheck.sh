#!/usr/bin/env bash

set -euo pipefail

HOST="${1:-api.nursescheduling.org}"
HTTPS_URL="https://${HOST}/ready"
HTTP_URL="http://${HOST}/ready"

echo "🔒 Checking HTTPS readiness endpoint: ${HTTPS_URL}"
https_status="$(curl -fsS -o /dev/null -w "%{http_code}" "${HTTPS_URL}")"
if [[ "${https_status}" != "200" ]]; then
    echo "❌ ERROR: expected HTTPS /ready to return 200, got ${https_status}" >&2
    exit 1
fi

echo "🚫 Checking HTTP readiness endpoint is not served directly: ${HTTP_URL}"
http_status="$(curl -sS -o /dev/null -w "%{http_code}" --max-redirs 0 "${HTTP_URL}" || true)"
if [[ "${http_status}" == "200" ]]; then
    echo "❌ ERROR: expected HTTP /ready to fail or redirect, got 200" >&2
    exit 1
fi

echo "✅ OK: HTTPS /ready returned 200 and HTTP /ready returned ${http_status:-no response}."
