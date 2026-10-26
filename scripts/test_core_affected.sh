#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CORE_DIR="$ROOT_DIR/core"
source "$SCRIPT_DIR/affected_test_common.sh"

# Dev images omit the optional PuLP solver packages. Their tests skip automatically.
# This option also skips tests whose installed runtime fails its probe, so the
# remaining suite can still run there.
skip_unavailable_solvers=false
parse_args=()
while (($# > 0)); do
  case "$1" in
    --skip-unavailable-solvers)
      skip_unavailable_solvers=true
      shift
      ;;
    --)
      parse_args+=("$@")
      break
      ;;
    *)
      parse_args+=("$1")
      shift
      ;;
  esac
done
affected_parse_args "$ROOT_DIR" "${parse_args[@]}"

test_paths=()
run_full_suite="$affected_full"
ai_changed=false
ai_eval_changed=false

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
      tests/test_ai_*.py | tests/ai_fixtures/* | tests/chat_rendering_helper.py)
        ai_changed=true
        ;;
      tests/test_*.py)
        if [[ -f "$CORE_DIR/$relative" ]]; then
          test_paths+=("$relative")
        else
          run_full_suite=true
        fi
        ;;
      nurse_scheduling/ai/* | nurse_scheduling/ai_serve.py)
        ai_changed=true
        ;;
      tests/ai_eval/* | tests/ai_test_helper.py)
        ai_changed=true
        ai_eval_changed=true
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

  if [[ "$ai_changed" == true && "$run_full_suite" == false ]]; then
    for path in "$CORE_DIR"/tests/test_ai_*.py; do
      [[ -f "$path" ]] && test_paths+=("tests/${path##*/}")
    done
    # The preference audit also imports the evaluation package.
    if [[ "$ai_eval_changed" == true && -f "$CORE_DIR/tests/test_preference_audit.py" ]]; then
      test_paths+=(tests/test_preference_audit.py)
    fi
  fi
fi

if ((${#test_paths[@]} > 0)); then
  mapfile -d '' test_paths < <(printf '%s\0' "${test_paths[@]}" | LC_ALL=C sort -zu)
fi

if [[ "$affected_list" == true ]]; then
  echo "lint: scripts/check_terminology.sh"
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

"$SCRIPT_DIR/check_terminology.sh"
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
  SKIP_UNAVAILABLE_SOLVERS="$skip_unavailable_solvers" python - "${required_solvers[@]}" <<'PY'
import importlib.util
import os
import sys

from nurse_scheduling.server.solver_options import SOLVER_RUNTIME_MODULES, solver_is_available

unavailable = [solver for solver in dict.fromkeys(sys.argv[1:]) if not solver_is_available(solver)]
missing = []
broken = []
for solver in unavailable:
    module = SOLVER_RUNTIME_MODULES.get(solver)
    if module is not None and importlib.util.find_spec(module) is None:
        missing.append(solver)
    else:
        broken.append(solver)
if missing:
    print(f"Optional solver packages not installed; their tests skip automatically: {', '.join(missing)}", file=sys.stderr)
if broken and os.environ["SKIP_UNAVAILABLE_SOLVERS"] == "true":
    print(f"Skipping tests that need unavailable solver runtimes: {', '.join(broken)}", file=sys.stderr)
elif broken:
    print(f"Optional solver runtimes failed although their packages are installed: {', '.join(broken)}", file=sys.stderr)
    if os.path.exists("/.dockerenv"):
        print("Fix the dev image installation. Pass --skip-unavailable-solvers to skip their tests.", file=sys.stderr)
    else:
        print("From core/, run: uv pip install -r requirements-optional.txt", file=sys.stderr)
    raise SystemExit(2)
PY
fi

pytest_args=(-q --tb=short --disable-warnings --maxfail=1)
if [[ "$skip_unavailable_solvers" == true ]]; then
  pytest_args+=(--skip-unavailable-solvers)
fi
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
