#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
FRONTEND_DIR="$ROOT_DIR/web-frontend"

specs=()
run_full_suite=false
if (($# > 0)); then
  for path in "$@"; do
    path="${path#"$ROOT_DIR"/}"
    specs+=("${path#web-frontend/}")
  done
else
  mapfile -d '' specs < <(
    {
      git -C "$ROOT_DIR" diff --name-only --diff-filter=ACDMRTUXB -z HEAD -- 'web-frontend/e2e/*.spec.ts'
      git -C "$ROOT_DIR" ls-files --others --exclude-standard -z -- 'web-frontend/e2e/*.spec.ts'
    } | sed -z 's#^web-frontend/##' | sort -zu
  )

  if ! git -C "$ROOT_DIR" diff --quiet HEAD -- \
    web-frontend/e2e/helpers.ts \
    web-frontend/e2e/test.ts \
    web-frontend/playwright.config.ts; then
    run_full_suite=true
  fi
  if ! git -C "$ROOT_DIR" diff --quiet --diff-filter=D HEAD -- 'web-frontend/e2e/*.spec.ts'; then
    run_full_suite=true
  fi

  if ((${#specs[@]} == 0)) && [[ "$run_full_suite" == false ]]; then
    echo "No changed frontend E2E specs or shared E2E files; skipping Playwright."
    exit 0
  fi
fi

cd "$FRONTEND_DIR"

exec 9>"/tmp/nurse-scheduling-frontend-tests.lock"
flock 9
bun install --frozen-lockfile --silent

if [[ "$run_full_suite" == true ]]; then
  echo "Shared E2E files changed; running the compact full browser suite."
  exec bunx playwright test --reporter=dot --quiet --max-failures=1
fi

exec bunx playwright test --reporter=dot --quiet --max-failures=1 "${specs[@]}"
