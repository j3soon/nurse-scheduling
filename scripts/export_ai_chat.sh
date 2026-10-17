#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This file is mostly AI generated.

set -euo pipefail
if (($# != 2)) || [[ ${1:-} == --help ]]; then
  echo 'Usage: ./scripts/export_ai_chat.sh SESSION_ID OUTPUT.zip'
  echo 'Use AI_HISTORY_POSTGRES_URL for native PostgreSQL, or AI_ENV_FILE for Docker Compose.'
  [[ ${1:-} == --help ]] && exit 0
  exit 2
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
case $2 in
  *.zip) ;;
  *) echo 'Choose a .zip output path.' >&2; exit 2 ;;
esac
if [[ -n ${AI_HISTORY_POSTGRES_URL:-} ]]; then
  PYTHONPATH="$repo_root/core${PYTHONPATH:+:$PYTHONPATH}" python -m nurse_scheduling.ai.export_chat "$1" "$2"
else
  output_dir="$(dirname "$2")"
  mkdir -p "$output_dir"
  temporary="$(mktemp "$output_dir/.chat-export.XXXXXX")"
  trap 'rm -f -- "$temporary"' EXIT
  docker compose --env-file "${AI_ENV_FILE:-$repo_root/docker/.env}" \
    -f "$repo_root/docker/compose.backend.yml" exec -T ai \
    python -m nurse_scheduling.ai.export_chat "$1" - > "$temporary"
  mv -f -- "$temporary" "$2"
fi
printf 'Exported %s\n' "$2"
