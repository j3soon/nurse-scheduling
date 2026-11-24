#!/usr/bin/env bash

set -euo pipefail

# Get the directory of this script.
# Reference: https://stackoverflow.com/q/59895
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
CORE_DIR="$ROOT_DIR/core"
FRONTEND_DIR="$ROOT_DIR/web-frontend"
DOCS_DIR="$ROOT_DIR/docs"

if [[ -f /.dockerenv ]]; then
  # The container mounts the host checkout, so a venv here would replace the host's.
  echo "Error: dev containers preinstall the core packages in /opt/venv, which is on PATH."
  echo "Run python, pytest, ruff, and ty directly. Do not run this script."
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: 'uv' is not installed. See README.md prerequisites."
  exit 1
fi

if ! command -v bun >/dev/null 2>&1; then
  echo "Error: 'bun' is not installed. See README.md prerequisites."
  exit 1
fi

sync_uv_project() {
  local project_dir="$1"
  shift

  if [[ ! -f "$project_dir/uv.lock" ]]; then
    echo "Error: uv lock file not found: $project_dir/uv.lock"
    exit 1
  fi

  echo "Syncing the locked environment in $project_dir/.venv ..."
  (cd "$project_dir" && uv sync --locked --python 3.14 "$@")
}

echo
echo "==> Setting up web frontend"
if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "Error: project directory not found: $FRONTEND_DIR"
  exit 1
fi
cd "$FRONTEND_DIR"
echo "Installing frontend dependencies in $FRONTEND_DIR ..."
bun install

echo
echo "==> Setting up core"
# Development installs the optional solvers and the default dev group.
# Deployment images install only the runtime set with `--no-dev`.
sync_uv_project "$CORE_DIR" --all-extras

echo
echo "==> Setting up docs"
sync_uv_project "$DOCS_DIR"

echo
echo "Done."
echo "Activate core venv later with: source core/.venv/bin/activate"
echo "Activate docs venv later with: source docs/.venv/bin/activate"
