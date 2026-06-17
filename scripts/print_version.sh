#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."

git -c "safe.directory=$ROOT_DIR" -C "$ROOT_DIR" describe --tags --always --dirty
