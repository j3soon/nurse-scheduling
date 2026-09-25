#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CORE_DIR="$ROOT_DIR/core"
source "$SCRIPT_DIR/affected_test_common.sh"
affected_parse_args "$ROOT_DIR" "$@"

test_paths=()
run_full_suite="$affected_full"
ai_changed=false

if ((${#affected_paths[@]} > 0)); then
  for path in "${affected_paths[@]}"; do
    path="${path#"$ROOT_DIR"/}"
    test_paths+=("${path#core/}")
  done
elif [[ "$run_full_suite" == false ]]; then
  mapfile -d '' changed_files < <(affected_changed_files "$ROOT_DIR" core)
  for file in "${changed_files[@]}"; do
    relative="${file#core/}"
    case "$relative" in
      tests/test_*.py)
        test_paths+=("$relative")
        ;;
      nurse_scheduling/ai/* | nurse_scheduling/ai_serve.py | tests/ai_eval/* | tests/ai_test_helper.py)
        ai_changed=true
        ;;
      nurse_scheduling/* | tests/* | requirements*.txt | pyproject.toml)
        run_full_suite=true
        ;;
      AGENTS.md | *.md | .gitignore)
        ;;
      *)
        run_full_suite=true
        ;;
    esac
  done

  if ! git -C "$ROOT_DIR" diff --no-renames --quiet --diff-filter=D "$affected_base" -- \
    core/nurse_scheduling core/tests; then
    run_full_suite=true
  fi

  if [[ "$ai_changed" == true && "$run_full_suite" == false ]]; then
    for path in "$CORE_DIR"/tests/test_ai_*.py; do
      [[ -f "$path" ]] && test_paths+=("tests/${path##*/}")
    done
  fi
fi

if ((${#test_paths[@]} > 0)); then
  mapfile -d '' test_paths < <(printf '%s\0' "${test_paths[@]}" | LC_ALL=C sort -zu)
fi

if [[ "$affected_list" == true ]]; then
  echo "lint: ruff format --check nurse_scheduling tests"
  echo "lint: ruff check nurse_scheduling tests"
  if [[ "$run_full_suite" == true ]]; then
    echo "tests: full normal core suite (CBC and cuOpt excluded)"
  elif ((${#test_paths[@]} > 0)); then
    printf 'test: %s\n' "${test_paths[@]}"
  else
    echo "tests: none"
  fi
  exit 0
fi

cd "$CORE_DIR"
ruff format --check nurse_scheduling tests
ruff check nurse_scheduling tests

required_solvers=()
if [[ "$run_full_suite" == true ]]; then
  required_solvers=(pulp/highs pulp/scip)
else
  for path in "${test_paths[@]}"; do
    case "$path" in
      tests/test_serve.py | tests/test_schedule_pulp_highs.py)
        required_solvers+=(pulp/highs)
        ;;
      tests/test_schedule_pulp_scip.py)
        required_solvers+=(pulp/scip)
        ;;
      tests | tests/test_solver_pulp_python.py)
        required_solvers+=(pulp/highs pulp/scip)
        ;;
    esac
  done
fi

if ((${#required_solvers[@]} > 0)); then
  python - "${required_solvers[@]}" <<'PY'
import sys

from nurse_scheduling.server.solver_options import solver_is_available

unavailable = [solver for solver in dict.fromkeys(sys.argv[1:]) if not solver_is_available(solver)]
if unavailable:
    print(f"Required optional solver runtimes unavailable: {', '.join(unavailable)}", file=sys.stderr)
    print("From core/, run: uv pip install -r requirements-optional.txt", file=sys.stderr)
    raise SystemExit(2)
PY
fi

pytest_args=(-q --tb=short --disable-warnings --maxfail=1)
if [[ "$run_full_suite" == true ]]; then
  echo "Broad core changes detected; running the compact normal suite."
  exec pytest "${pytest_args[@]}" \
    --ignore-glob='*pulp_cbc.py' \
    --ignore-glob='*pulp_cuopt.py' \
    --ignore=tests/test_solver_pulp_progress.py \
    tests
fi

if ((${#test_paths[@]} == 0)); then
  echo "No changed core code or tests; skipping pytest."
  exit 0
fi
exec pytest "${pytest_args[@]}" "${test_paths[@]}"
