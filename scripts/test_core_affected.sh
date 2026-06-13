#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
CORE_DIR="$ROOT_DIR/core"

test_paths=()
run_full_suite=false

if (($# > 0)); then
  for path in "$@"; do
    path="${path#"$ROOT_DIR"/}"
    test_paths+=("${path#core/}")
  done
else
  mapfile -d '' changed_files < <(
    {
      git -C "$ROOT_DIR" diff --name-only --diff-filter=ACDMRTUXB -z HEAD -- core/nurse_scheduling core/tests
      git -C "$ROOT_DIR" ls-files --others --exclude-standard -z -- core/nurse_scheduling core/tests
    } | sort -zu
  )

  if ((${#changed_files[@]} == 0)); then
    echo "No changed core source or test files; skipping pytest."
    exit 0
  fi

  for file in "${changed_files[@]}"; do
    relative="${file#core/}"
    case "$relative" in
      tests/test_*.py)
        test_paths+=("$relative")
        ;;
      nurse_scheduling/*.py)
        run_full_suite=true
        ;;
      *)
        run_full_suite=true
        ;;
    esac
  done

  if ! git -C "$ROOT_DIR" diff --quiet --diff-filter=D HEAD -- core/nurse_scheduling core/tests; then
    run_full_suite=true
  fi
fi

cd "$CORE_DIR"

pytest_args=(-q --tb=short --disable-warnings --maxfail=1)
if [[ "$run_full_suite" == true ]]; then
  echo "Broad core changes detected; running the compact normal suite."
  exec pytest "${pytest_args[@]}"
fi

mapfile -t test_paths < <(printf '%s\n' "${test_paths[@]}" | sort -u)
exec pytest "${pytest_args[@]}" "${test_paths[@]}"
