#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
test_root="$(mktemp -d)"
trap 'rm -rf -- "$test_root"' EXIT
missing_root="$test_root/missing"

set +e
output="$(bash "$script_dir/run-ci.sh" "$missing_root" 2>&1)"
status=$?
set -e

if [[ $status -ne 2 ]]; then
  printf 'expected exit status 2, got %d\n' "$status" >&2
  exit 1
fi

expected="error: $missing_root is not the repository root"
if [[ "$output" != "$expected" ]]; then
  printf 'unexpected error output: %s\n' "$output" >&2
  exit 1
fi

invalid_root="$test_root/invalid"
mkdir -p -- "$invalid_root"

set +e
output="$(bash "$script_dir/run-ci.sh" "$invalid_root" 2>&1)"
status=$?
set -e

if [[ $status -ne 2 ]]; then
  printf 'expected exit status 2, got %d\n' "$status" >&2
  exit 1
fi

expected="error: $invalid_root is not the repository root"
if [[ "$output" != "$expected" ]]; then
  printf 'unexpected error output: %s\n' "$output" >&2
  exit 1
fi
