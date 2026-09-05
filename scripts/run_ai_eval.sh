#!/usr/bin/env bash
set -euo pipefail

# Evaluate the experimental AI assistant against its cases. This is evaluation,
# not the solver performance benchmark in scripts/run_performance_benchmark.sh.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="${REPO_ROOT}/core"
AI_ENV_FILE="${AI_ENV_FILE:-${REPO_ROOT}/docker/.env}"

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

for required in AI_PROVIDER_BASE_URL AI_PROVIDER_API_KEY; do
  if [[ -z "${!required:-}" ]]; then
    echo "Error: ${required} is required. Set it in ${AI_ENV_FILE} or the environment." >&2
    echo "Copy docker/.env.example to docker/.env and fill in the AI provider values." >&2
    exit 1
  fi
done

cd "${CORE_DIR}"
exec python -m tests.ai_eval.runner "$@"
