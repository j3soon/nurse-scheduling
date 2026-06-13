#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
FRONTEND_DIR="$ROOT_DIR/web-frontend"

related_files=()
run_full_suite=false
if (($# > 0)); then
  for file in "$@"; do
    file="${file#"$ROOT_DIR"/}"
    related_files+=("${file#web-frontend/}")
  done
else
  mapfile -d '' related_files < <(
    {
      git -C "$ROOT_DIR" diff --name-only --diff-filter=ACDMRTUXB -z HEAD -- web-frontend/src
      git -C "$ROOT_DIR" ls-files --others --exclude-standard -z -- web-frontend/src
    } | sed -z 's#^web-frontend/##' | sort -zu
  )

  if ! git -C "$ROOT_DIR" diff --quiet HEAD -- \
    web-frontend/package.json \
    web-frontend/bun.lock \
    web-frontend/vitest.config.ts \
    web-frontend/src/test/setup.ts; then
    run_full_suite=true
  fi

  if ((${#related_files[@]} == 0)) && [[ "$run_full_suite" == false ]]; then
    echo "No changed frontend source or shared test-config files; skipping Vitest."
    exit 0
  fi
fi

cd "$FRONTEND_DIR"

# Prevent concurrent repair/test runs from mutating the same node_modules tree.
exec 9>"/tmp/nurse-scheduling-frontend-tests.lock"
flock 9

# Bind-mounted node_modules can be incomplete after rebuilding or switching hosts.
bun install --frozen-lockfile --silent

vitest_args=(--reporter=dot --silent=passed-only --bail=1 --passWithNoTests)
if [[ "$run_full_suite" == false ]] && git -C "$ROOT_DIR" diff --quiet --diff-filter=D HEAD -- web-frontend/src; then
  exec bunx vitest related "${vitest_args[@]}" "${related_files[@]}"
fi

echo "Shared test-config or deleted source files detected; running the compact full unit/component suite."
exec bunx vitest run "${vitest_args[@]}"
