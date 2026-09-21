#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/web-frontend"
source "$SCRIPT_DIR/affected_test_common.sh"
affected_parse_args "$ROOT_DIR" "$@"

related_files=()
run_full_suite="$affected_full"
if ((${#affected_paths[@]} > 0)); then
  for file in "${affected_paths[@]}"; do
    file="${file#"$ROOT_DIR"/}"
    related_files+=("${file#web-frontend/}")
  done
elif [[ "$run_full_suite" == false ]]; then
  mapfile -d '' changed_files < <(affected_changed_files "$ROOT_DIR" web-frontend)
  for file in "${changed_files[@]}"; do
    relative="${file#web-frontend/}"
    case "$relative" in
      src/test/setup.ts | src/app/globals.css)
        run_full_suite=true
        ;;
      src/*)
        related_files+=("$relative")
        ;;
      e2e/* | AGENTS.md | *.md | .gitignore | eslint.config.mjs)
        ;;
      *)
        run_full_suite=true
        ;;
    esac
  done

  if ! git -C "$ROOT_DIR" diff --no-renames --quiet --diff-filter=D "$affected_base" -- \
    web-frontend/src; then
    run_full_suite=true
  fi
fi

if ((${#related_files[@]} > 0)); then
  mapfile -d '' related_files < <(printf '%s\0' "${related_files[@]}" | LC_ALL=C sort -zu)
fi

if [[ "$affected_list" == true ]]; then
  echo "lint: bun run lint"
  if [[ "$run_full_suite" == true ]]; then
    echo "tests: full Vitest suite"
  elif ((${#related_files[@]} > 0)); then
    printf 'related: %s\n' "${related_files[@]}"
  else
    echo "tests: none"
  fi
  exit 0
fi

cd "$FRONTEND_DIR"

# Prevent concurrent repair/test runs from mutating the same node_modules tree.
exec 9>"/tmp/nurse-scheduling-frontend-tests.lock"
flock 9

# Bind-mounted node_modules can be incomplete after rebuilding or switching hosts.
bun install --frozen-lockfile --silent
bun run lint

vitest_args=(--reporter=dot --silent=passed-only --bail=1)
if [[ "$run_full_suite" == true ]]; then
  echo "Shared frontend changes detected; running the compact full unit/component suite."
  exec bunx vitest run "${vitest_args[@]}"
fi

if ((${#related_files[@]} == 0)); then
  echo "No changed frontend source or shared test files; skipping Vitest."
  exit 0
fi

# Vitest related exits 0 when it finds no tests, so check its structured report.
report_file="$(mktemp)"
trap 'rm -f -- "$report_file"' EXIT
set +e
bunx vitest related --run "${vitest_args[@]}" --reporter=json \
  "--outputFile.json=$report_file" "${related_files[@]}"
vitest_status=$?
set -e
if ((vitest_status != 0)); then
  exit "$vitest_status"
fi
if ! node -e '
  const report = JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"));
  process.exit(report.numPassedTests > 0 ? 0 : 1);
' "$report_file"; then
  echo "No related Vitest tests passed. Pass test paths explicitly or use --full." >&2
  exit 2
fi
