#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
fixture_root="$(mktemp -d)"
trap 'rm -rf -- "$fixture_root"' EXIT

assert_line() {
  if ! rg -Fxq -- "$2" <<< "$1"; then
    printf 'Missing selection line: %s\n%s\n' "$2" "$1" >&2
    exit 1
  fi
}

assert_no_line() {
  if rg -Fxq -- "$2" <<< "$1"; then
    printf 'Unexpected selection line: %s\n%s\n' "$2" "$1" >&2
    exit 1
  fi
}

write_fixture() {
  mkdir -p -- "$(dirname "$fixture_root/$1")"
  printf 'baseline\n' > "$fixture_root/$1"
}

mkdir -p -- "$fixture_root/scripts"
cp -- "$script_dir/affected_test_common.sh" "$script_dir/test_core_affected.sh" \
  "$script_dir/test_frontend_affected.sh" "$script_dir/test_frontend_e2e_affected.sh" \
  "$fixture_root/scripts/"
for path in \
  core/nurse_scheduling/ai/pi/read.py \
  core/nurse_scheduling/ai/prompts/sandbox-system.md \
  core/tests/test_ai_basic.py \
  core/tests/test_ai_provider.py \
  core/tests/test_scheduler.py \
  web-frontend/src/app/page.tsx \
  web-frontend/src/app/page.test.tsx \
  web-frontend/e2e/page.spec.ts \
  web-frontend/e2e/helpers.ts \
  web-frontend/vitest.config.ts; do
  write_fixture "$path"
done

git -C "$fixture_root" init -q
git -C "$fixture_root" config user.name "$(git -C "$repo_root" config user.name)"
git -C "$fixture_root" config user.email "$(git -C "$repo_root" config user.email)"
git -C "$fixture_root" add .
git -C "$fixture_root" commit -qm 'test: seed affected-test fixture'

output="$("$fixture_root/scripts/test_core_affected.sh" --list)"
assert_line "$output" 'tests: none'
output="$("$fixture_root/scripts/test_frontend_affected.sh" --list)"
assert_line "$output" 'tests: none'
output="$("$fixture_root/scripts/test_frontend_e2e_affected.sh" --list)"
assert_line "$output" 'tests: none'

printf 'change\n' >> "$fixture_root/core/nurse_scheduling/ai/pi/read.py"
output="$("$fixture_root/scripts/test_core_affected.sh" --list)"
assert_line "$output" 'test: tests/test_ai_basic.py'
assert_line "$output" 'test: tests/test_ai_provider.py'
assert_no_line "$output" 'test: tests/test_scheduler.py'

write_fixture core/nurse_scheduling/ai/pi/read.py
printf 'change\n' >> "$fixture_root/core/nurse_scheduling/ai/prompts/sandbox-system.md"
output="$("$fixture_root/scripts/test_core_affected.sh" --list)"
assert_line "$output" 'test: tests/test_ai_basic.py'
assert_line "$output" 'test: tests/test_ai_provider.py'
assert_no_line "$output" 'test: tests/test_scheduler.py'
write_fixture core/nurse_scheduling/ai/prompts/sandbox-system.md

printf 'change\n' >> "$fixture_root/core/nurse_scheduling/ai/pi/read.py"

git -C "$fixture_root" add core/nurse_scheduling/ai/pi/read.py
git -C "$fixture_root" commit -qm 'test: change AI fixture'
output="$("$fixture_root/scripts/test_core_affected.sh" --list)"
assert_line "$output" 'tests: none'
output="$("$fixture_root/scripts/test_core_affected.sh" --list --base HEAD^)"
assert_line "$output" 'test: tests/test_ai_basic.py'

write_fixture core/requirements.txt
output="$("$fixture_root/scripts/test_core_affected.sh" --list)"
assert_line "$output" 'tests: full normal core suite (CBC and cuOpt excluded)'
rm -- "$fixture_root/core/requirements.txt"

rm -- "$fixture_root/core/tests/test_ai_provider.py"
output="$("$fixture_root/scripts/test_core_affected.sh" --list)"
assert_line "$output" 'tests: full normal core suite (CBC and cuOpt excluded)'
write_fixture core/tests/test_ai_provider.py

printf 'change\n' >> "$fixture_root/web-frontend/src/app/page.tsx"
output="$("$fixture_root/scripts/test_frontend_affected.sh" --list)"
assert_line "$output" 'related: src/app/page.tsx'
set +e
output="$("$fixture_root/scripts/test_frontend_e2e_affected.sh" --list 2>&1)"
status=$?
set -e
if [[ $status -ne 2 ]]; then
  printf 'Expected E2E source-change selection to fail with 2, got %d\n' "$status" >&2
  exit 1
fi
assert_line "$output" 'Pass relevant E2E spec paths explicitly, or use --full.'
write_fixture web-frontend/src/app/page.tsx

rm -- "$fixture_root/web-frontend/src/app/page.tsx"
output="$("$fixture_root/scripts/test_frontend_affected.sh" --list)"
assert_line "$output" 'tests: full Vitest suite'
output="$("$fixture_root/scripts/test_frontend_e2e_affected.sh" --list)"
assert_line "$output" 'tests: full Playwright suite (isolated server)'
write_fixture web-frontend/src/app/page.tsx

printf 'change\n' >> "$fixture_root/web-frontend/vitest.config.ts"
output="$("$fixture_root/scripts/test_frontend_affected.sh" --list)"
assert_line "$output" 'tests: full Vitest suite'
write_fixture web-frontend/vitest.config.ts

printf 'change\n' >> "$fixture_root/web-frontend/e2e/helpers.ts"
output="$("$fixture_root/scripts/test_frontend_e2e_affected.sh" --list)"
assert_line "$output" 'tests: full Playwright suite (isolated server)'
write_fixture web-frontend/e2e/helpers.ts

printf 'change\n' >> "$fixture_root/web-frontend/e2e/page.spec.ts"
output="$("$fixture_root/scripts/test_frontend_e2e_affected.sh" --list)"
assert_line "$output" 'spec: e2e/page.spec.ts'
output="$("$fixture_root/scripts/test_frontend_affected.sh" --list)"
assert_line "$output" 'tests: none'
rm -- "$fixture_root/web-frontend/e2e/page.spec.ts"
output="$("$fixture_root/scripts/test_frontend_e2e_affected.sh" --list)"
assert_line "$output" 'tests: full Playwright suite (isolated server)'
write_fixture web-frontend/e2e/page.spec.ts

write_fixture web-frontend/public/example.yaml
output="$("$fixture_root/scripts/test_frontend_affected.sh" --list)"
assert_line "$output" 'tests: full Vitest suite'
rm -- "$fixture_root/web-frontend/public/example.yaml"

write_fixture 'web-frontend/src/utils/spaced file.ts'
output="$("$fixture_root/scripts/test_frontend_affected.sh" --list)"
assert_line "$output" 'related: src/utils/spaced file.ts'
rm -- "$fixture_root/web-frontend/src/utils/spaced file.ts"

output="$("$fixture_root/scripts/test_core_affected.sh" --list \
  "$fixture_root/core/tests/test_scheduler.py")"
assert_line "$output" 'test: tests/test_scheduler.py'
output="$("$fixture_root/scripts/test_frontend_e2e_affected.sh" --list --full)"
assert_line "$output" 'tests: full Playwright suite (isolated server)'

set +e
output="$("$fixture_root/scripts/test_core_affected.sh" --list --base missing-ref 2>&1)"
status=$?
set -e
if [[ $status -ne 2 ]]; then
  printf 'Expected invalid Git base to fail with 2, got %d\n' "$status" >&2
  exit 1
fi
assert_line "$output" 'Unknown Git base: missing-ref'

mkdir -p -- "$fixture_root/bin"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "mock ruff: %s\n" "$*"' \
  > "$fixture_root/bin/ruff"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "mock pytest: %s\n" "$*"' \
  > "$fixture_root/bin/pytest"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "mock bun: %s\n" "$*"' \
  > "$fixture_root/bin/bun"
printf '%s\n' \
  '#!/usr/bin/env bash' \
  'for arg in "$@"; do' \
  '  case "$arg" in' \
  '    --outputFile.json=*) printf "{\"numTotalTests\":0}\n" > "${arg#--outputFile.json=}" ;;' \
  '  esac' \
  'done' \
  'echo "No test files found, exiting with code 0"' \
  > "$fixture_root/bin/bunx"
chmod +x "$fixture_root/bin/ruff" "$fixture_root/bin/pytest" \
  "$fixture_root/bin/bun" "$fixture_root/bin/bunx"

output="$(PATH="$fixture_root/bin:$PATH" "$fixture_root/scripts/test_core_affected.sh" \
  core/tests/test_scheduler.py)"
assert_line "$output" 'mock ruff: format --check nurse_scheduling tests'
assert_line "$output" 'mock ruff: check nurse_scheduling tests'
assert_line "$output" 'mock pytest: -q --tb=short --disable-warnings --maxfail=1 tests/test_scheduler.py'
output="$(PATH="$fixture_root/bin:$PATH" "$fixture_root/scripts/test_core_affected.sh" --full)"
assert_line "$output" 'mock pytest: -q --tb=short --disable-warnings --maxfail=1 --ignore-glob=*pulp_cbc.py --ignore-glob=*pulp_cuopt.py --ignore=tests/test_solver_pulp_progress.py tests'

set +e
output="$(PATH="$fixture_root/bin:$PATH" "$fixture_root/scripts/test_frontend_affected.sh" \
  web-frontend/src/app/page.tsx 2>&1)"
status=$?
set -e
if [[ $status -ne 2 ]]; then
  printf 'Expected zero related tests to fail with 2, got %d\n' "$status" >&2
  exit 1
fi
assert_line "$output" 'mock bun: run lint'
assert_line "$output" 'No related Vitest tests found. Pass test paths explicitly or use --full.'

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'printf "mock bunx: %s; reuse=%s\n" "$*" "${E2E_REUSE_EXISTING_SERVER:-unset}"' \
  > "$fixture_root/bin/bunx"
output="$(PATH="$fixture_root/bin:$PATH" "$fixture_root/scripts/test_frontend_e2e_affected.sh" \
  web-frontend/e2e/page.spec.ts)"
assert_line "$output" 'mock bun: run lint'
assert_line "$output" 'mock bunx: playwright test --reporter=dot --quiet --max-failures=1 e2e/page.spec.ts; reuse=unset'

printf 'change\n' >> "$fixture_root/web-frontend/src/app/page.tsx"
git -C "$fixture_root" add web-frontend/src/app/page.tsx
git -C "$fixture_root" commit -qm 'test: change frontend fixture'
output="$("$fixture_root/scripts/test_frontend_affected.sh" --list)"
assert_line "$output" 'tests: none'
output="$("$fixture_root/scripts/test_frontend_affected.sh" --list --base HEAD^)"
assert_line "$output" 'related: src/app/page.tsx'

echo 'Affected-test selection checks passed.'
