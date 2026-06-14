#!/usr/bin/env bash

set -euo pipefail

# Get the directory of this script.
# Reference: https://stackoverflow.com/q/59895
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
FRONTEND_DIR="$ROOT_DIR/web-frontend"

if ! command -v bun >/dev/null 2>&1; then
  echo "Error: 'bun' is not installed. See README.md prerequisites."
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "Error: frontend directory not found: $FRONTEND_DIR"
  exit 1
fi

cd "$FRONTEND_DIR"
exec bun run dev "$@"
