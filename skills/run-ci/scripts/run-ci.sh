#!/usr/bin/env bash
set -euo pipefail

requested_root="${1:-$PWD}"
if ! repo_root="$(cd -- "$requested_root" 2>/dev/null && pwd)"; then
  printf 'error: %s is not the repository root\n' "$requested_root" >&2
  exit 2
fi

if [[ ! -d "$repo_root/core" || ! -d "$repo_root/web-frontend" ]]; then
  printf 'error: %s is not the repository root\n' "$repo_root" >&2
  exit 2
fi

set -x

(
  cd "$repo_root/core"
  ruff format --check nurse_scheduling tests
  ruff check nurse_scheduling tests
  pytest \
    -q --tb=short --disable-warnings --maxfail=1 \
    --cov=nurse_scheduling \
    --ignore-glob='*pulp_cbc.py' \
    --ignore-glob='*pulp_cuopt.py' \
    --ignore=tests/test_solver_pulp_progress.py \
    tests
)

(
  cd "$repo_root/web-frontend"
  bun run lint
  bun run build
  bun run test:coverage
  bun run test:e2e:coverage
  bun run coverage:e2e:report
)
