#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="${REPO_ROOT}/core"
AI_ENV_FILE="${AI_ENV_FILE:-${REPO_ROOT}/.env.ai}"

if [[ -f "${AI_ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${AI_ENV_FILE}"
  set +a
fi

if [[ -x "${CORE_DIR}/.venv/bin/python" && -f "${CORE_DIR}/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${CORE_DIR}/.venv/bin/activate"
fi

if ! command -v uvicorn >/dev/null 2>&1; then
  echo "Error: 'uvicorn' is not installed. Rebuild docker/Dockerfile or run scripts/setup_env.sh." >&2
  exit 1
fi

if [[ -z "${AI_PROVIDER_API_KEY:-}" && -t 0 ]]; then
  read -rsp "AI provider API key: " AI_PROVIDER_API_KEY
  echo
fi
if [[ -z "${AI_PROVIDER_API_KEY:-}" ]]; then
  echo "AI_PROVIDER_API_KEY is required." >&2
  exit 1
fi
if [[ -z "${AI_PROVIDER_BASE_URL:-}" ]]; then
  echo "AI_PROVIDER_BASE_URL is required." >&2
  exit 1
fi

export AI_PROVIDER_API_KEY
export AI_PROVIDER_BASE_URL
export AI_PROVIDER_MODEL="${AI_PROVIDER_MODEL:-local-model}"
export AI_BACKEND_PORT="${AI_BACKEND_PORT:-8001}"
export AI_COOKIE_SECURE="${AI_COOKIE_SECURE:-0}"

cd "${CORE_DIR}"
exec uvicorn nurse_scheduling.ai_serve:app \
  --reload \
  --host 0.0.0.0 \
  --port "${AI_BACKEND_PORT}" \
  --no-access-log \
  "$@"
