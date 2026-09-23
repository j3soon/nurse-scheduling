#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
environment_file="${AI_ENV_FILE:-${repository_root}/docker/.env}"

if [[ -f "${environment_file}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${environment_file}"
  set +a
fi

if [[ -z "${E2B_API_KEY:-}" ]]; then
  echo "Error: E2B_API_KEY is required. Set it in ${environment_file} or the environment." >&2
  exit 1
fi

if [[ -x "${repository_root}/core/.venv/bin/python" ]]; then
  python_command="${repository_root}/core/.venv/bin/python"
else
  python_command="python"
fi

cd "${repository_root}/core"
exec "${python_command}" -m tests.ai_eval.read_batch_benchmark "$@"
