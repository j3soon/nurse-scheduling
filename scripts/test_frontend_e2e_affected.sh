#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/web-frontend"
source "$SCRIPT_DIR/affected_test_common.sh"
affected_parse_args "$ROOT_DIR" "$@"

specs=()
run_full_suite="$affected_full"
app_changed=false
if ((${#affected_paths[@]} > 0)); then
  for path in "${affected_paths[@]}"; do
    path="${path#"$ROOT_DIR"/}"
    specs+=("${path#web-frontend/}")
  done
elif [[ "$run_full_suite" == false ]]; then
  mapfile -d '' changed_files < <(affected_changed_files "$ROOT_DIR" web-frontend)
  for file in "${changed_files[@]}"; do
    relative="${file#web-frontend/}"
    case "$relative" in
      e2e/*.spec.ts)
        specs+=("$relative")
        ;;
      src/*.test.ts | src/*.test.tsx | src/test/*)
        ;;
      src/* | public/*)
        app_changed=true
        ;;
      AGENTS.md | *.md | .gitignore | eslint.config.mjs | vitest.config.ts)
        ;;
      *)
        run_full_suite=true
        ;;
    esac
  done

  if ! git -C "$ROOT_DIR" diff --no-renames --quiet --diff-filter=D "$affected_base" -- \
    web-frontend/e2e web-frontend/src web-frontend/public; then
    run_full_suite=true
  fi
fi

if ((${#specs[@]} > 0)); then
  mapfile -d '' specs < <(printf '%s\0' "${specs[@]}" | LC_ALL=C sort -zu)
fi

if [[ "$run_full_suite" == false && "$app_changed" == true ]]; then
  echo "App source or public assets changed. Browser coverage cannot be inferred from imports." >&2
  echo "Pass relevant E2E spec paths explicitly, or use --full." >&2
  exit 2
fi

if [[ "$affected_list" == true ]]; then
  echo "lint: bun run lint"
  if [[ "$run_full_suite" == true ]]; then
    echo "tests: full Playwright suite (isolated server)"
  elif ((${#specs[@]} > 0)); then
    printf 'spec: %s\n' "${specs[@]}"
  else
    echo "tests: none"
  fi
  exit 0
fi

cd "$FRONTEND_DIR"

exec 9>"/tmp/nurse-scheduling-frontend-tests.lock"
flock 9
bun install --frozen-lockfile --silent
bun run lint

if [[ "$run_full_suite" == true ]]; then
  echo "Shared E2E files changed; running the compact full browser suite."
  exec bunx playwright test --reporter=dot --quiet --max-failures=1
fi

if ((${#specs[@]} == 0)); then
  echo "No changed frontend E2E specs; skipping Playwright."
  exit 0
fi
exec bunx playwright test --reporter=dot --quiet --max-failures=1 "${specs[@]}"
