#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This file is mostly AI generated.

set -euo pipefail
if (($# != 2)) || [[ ${1:-} == --help ]]; then
  echo 'Usage: ./scripts/export_ai_chat.sh SESSION_ID OUTPUT.html|OUTPUT.md'
  echo 'Use AI_HISTORY_POSTGRES_URL for native PostgreSQL, or AI_ENV_FILE for Docker Compose.'
  [[ ${1:-} == --help ]] && exit 0
  exit 2
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
command -v bun >/dev/null || { echo 'Bun is required. Run the repository setup first.' >&2; exit 1; }
[[ -d "$repo_root/web-frontend/node_modules/react-dom" ]] || {
  echo 'Install the locked frontend dependencies: cd web-frontend && bun install --frozen-lockfile' >&2
  exit 1
}
case $2 in
  *.html|*.md) ;;
  *) echo 'Choose an .html or .md output path.' >&2; exit 2 ;;
esac
read_snapshot() {
  if [[ -n ${AI_HISTORY_POSTGRES_URL:-} ]]; then
    PYTHONPATH="$repo_root/core${PYTHONPATH:+:$PYTHONPATH}" python -m nurse_scheduling.ai.export_snapshot "$1"
  else
    docker compose --env-file "${AI_ENV_FILE:-$repo_root/docker/.env}" \
      -f "$repo_root/docker/compose.backend.yml" exec -T ai \
      python -m nurse_scheduling.ai.export_snapshot "$1"
  fi
}
read_snapshot "$1" | bun "$repo_root/web-frontend/scripts/export-ai-chat.ts" "$2"
