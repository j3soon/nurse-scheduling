#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This file is mostly AI generated.

set -euo pipefail
if [[ ${1:-} == --help ]]; then
  cat <<'USAGE'
Usage: ./scripts/recent_ai_prompts.sh [--sessions N] [--prompts N] [--chars N]
Show recent saved user prompts in reverse chronological order.
Defaults: 15 sessions, 5 prompts per session, 300 characters per preview.
Use AI_HISTORY_POSTGRES_URL for native PostgreSQL, or AI_ENV_FILE for Docker Compose.
Docker Compose prefers docker/.env and falls back to docker/.env.staging when it is missing.
The selected environment file is printed to stderr.
AI_COMPOSE_FILE selects another Compose variant. The database is read-only.
USAGE
  exit 0
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
if [[ -n ${AI_HISTORY_POSTGRES_URL:-} ]]; then
  PYTHONPATH="$repo_root/core${PYTHONPATH:+:$PYTHONPATH}" python -m nurse_scheduling.ai.recent_prompts "$@"
else
  environment_file="${AI_ENV_FILE:-$repo_root/docker/.env}"
  if [[ -z ${AI_ENV_FILE:-} && ! -f "$environment_file" && -f "$repo_root/docker/.env.staging" ]]; then
    environment_file="$repo_root/docker/.env.staging"
    printf 'Notice: docker/.env is missing. Falling back to %s.\n' "$environment_file" >&2
  else
    printf 'Using Docker Compose environment file: %s\n' "$environment_file" >&2
  fi
  if [[ ! -f "$environment_file" ]]; then
    printf 'Environment file not found: %s. Set AI_ENV_FILE or provide docker/.env or docker/.env.staging.\n' \
      "$environment_file" >&2
    exit 2
  fi
  docker compose --env-file "$environment_file" \
    -f "${AI_COMPOSE_FILE:-$repo_root/docker/compose.backend.yml}" exec -T ai \
    python -m nurse_scheduling.ai.recent_prompts "$@"
fi
