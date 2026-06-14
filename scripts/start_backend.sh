#!/usr/bin/env bash

set -euo pipefail

# Get the directory of this script.
# Reference: https://stackoverflow.com/q/59895
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
CORE_DIR="$ROOT_DIR/core"
BACKEND_DIR="$ROOT_DIR/core/nurse_scheduling"

if [[ -f "$CORE_DIR/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$CORE_DIR/.venv/bin/activate"
fi

if ! command -v fastapi >/dev/null 2>&1; then
  echo "Error: 'fastapi' is not installed. Run scripts/setup_env.sh first."
  exit 1
fi

if [[ ! -d "$BACKEND_DIR" ]]; then
  echo "Error: backend directory not found: $BACKEND_DIR"
  exit 1
fi

# cd "$BACKEND_DIR"
# exec fastapi dev serve.py
cd "$CORE_DIR"
exec uvicorn nurse_scheduling.serve:app --reload --no-access-log "$@"
