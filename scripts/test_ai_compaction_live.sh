#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This file is mostly AI generated.

set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(git -C "$script_dir" rev-parse --show-toplevel)"
env_file="${AI_ENV_FILE:-$root_dir/docker/.env}"
if [[ ! -f "$env_file" && -z ${AI_ENV_FILE:-} ]]; then
  env_file="$root_dir/docker/.env.staging"
fi
if [[ ! -f "$env_file" ]]; then
  echo 'Set AI_ENV_FILE to an existing provider and E2B environment file.' >&2
  exit 2
fi
set -a
# shellcheck disable=SC1090
source "$env_file"
set +a
export RUN_AI_COMPACTION_INTEGRATION=1
cd "$root_dir/core"
exec pytest -q --tb=short -s tests/test_ai_compaction_live.py "$@"
