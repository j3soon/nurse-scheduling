#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This file is mostly AI generated.

set -euo pipefail
repo_root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
if [[ ${1:-} != --help && ${1:-} != -h ]]; then
  environment_file="${AI_ENV_FILE:-$repo_root/docker/.env}"
  if [[ -z ${AI_ENV_FILE:-} && ! -f "$environment_file" && -f "$repo_root/docker/.env.staging" ]]; then
    environment_file="$repo_root/docker/.env.staging"
  fi
  if [[ -f "$environment_file" ]]; then
    printf 'Using environment file: %s\n' "$environment_file" >&2
    set -a
    # shellcheck disable=SC1090
    source "$environment_file"
    set +a
  elif [[ -n ${AI_ENV_FILE:-} ]]; then
    printf 'Environment file not found: %s\n' "$environment_file" >&2
    exit 2
  fi
fi
if [[ ! -f /.dockerenv && -x "$repo_root/core/.venv/bin/python" ]]; then
  python_command="$repo_root/core/.venv/bin/python"
else
  python_command=python
fi
PYTHONPATH="$repo_root/core${PYTHONPATH:+:$PYTHONPATH}" \
  exec "$python_command" -m nurse_scheduling.ai.litellm_concurrency "$@"
