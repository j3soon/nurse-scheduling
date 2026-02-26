#!/usr/bin/env bash

set -euo pipefail

# Get the directory of this script.
# Reference: https://stackoverflow.com/q/59895
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
CORE_DIR="$ROOT_DIR/core"
FRONTEND_DIR="$ROOT_DIR/web-frontend"
DOCS_DIR="$ROOT_DIR/docs"

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: 'uv' is not installed. See README.md prerequisites."
  exit 1
fi

if ! command -v bun >/dev/null 2>&1; then
  echo "Error: 'bun' is not installed. See README.md prerequisites."
  exit 1
fi

setup_python_project() {
  local project_dir="$1"
  local req_file="$project_dir/requirements.txt"

  if [[ ! -d "$project_dir" ]]; then
    echo "Error: project directory not found: $project_dir"
    exit 1
  fi

  if [[ ! -f "$req_file" ]]; then
    echo "Error: requirements file not found: $req_file"
    exit 1
  fi

  (
    cd "$project_dir"

    echo "Creating virtual environment in $project_dir/.venv ..."
    uv venv --python 3.12

    echo "Activating virtual environment ..."
    # shellcheck disable=SC1091
    source .venv/bin/activate

    echo "Installing dependencies from $req_file ..."
    uv pip install -r requirements.txt
  )
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
setup_python_project "$CORE_DIR"

echo
echo "==> Setting up docs"
setup_python_project "$DOCS_DIR"

echo
echo "Done."
echo "Activate core venv later with: source core/.venv/bin/activate"
echo "Activate docs venv later with: source docs/.venv/bin/activate"
