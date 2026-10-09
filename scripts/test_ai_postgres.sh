#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This file is mostly AI generated.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd "$script_dir/.." && pwd)"

if [[ ${1:-} == --help ]]; then
  cat <<'USAGE'
Usage: scripts/test_ai_postgres.sh [affected-test options or test paths]
       scripts/test_ai_postgres.sh --command COMMAND [ARGS...]

Without arguments, run the AI history and reconnect suites. Test selectors and
--base/--list use test_core_affected.sh. --list does not start PostgreSQL.
--command runs an explicit command from core/, for example pytest without a
first-failure limit. Logs and the fresh UTF-8 database stay under artifacts/.
Set AI_TEST_POSTGRES_BIN when server binaries are outside pg_config's directory.
USAGE
  exit 0
fi

if [[ ${1:-} == --command ]]; then
  shift
  if (($# == 0)); then
    echo '--command requires a command.' >&2
    exit 2
  fi
  test_command=("$@")
else
  default_tests=(core/tests/test_ai_history.py core/tests/test_ai_reconnect.py)
  if (($# == 0)); then
    set -- "${default_tests[@]}"
  elif (($# == 1)) && [[ $1 == --list ]]; then
    set -- --list "${default_tests[@]}"
  fi
  test_command=("$script_dir/test_core_affected.sh" "$@")
  # Check selection and arguments before allocating a database.
  selection="$("$script_dir/test_core_affected.sh" --list "$@")"
  for arg in "$@"; do
    if [[ $arg == --list ]]; then
      printf '%s\n' "$selection"
      exit 0
    fi
  done
  if [[ $selection == *'tests: none'* ]]; then
    echo 'No tests selected. Pass a test node or omit arguments for the recovery suites.' >&2
    exit 2
  fi
fi

postgres_bin="${AI_TEST_POSTGRES_BIN:-}"
if [[ -z $postgres_bin ]]; then
  if command -v pg_config > /dev/null; then
    postgres_bin="$(pg_config --bindir)"
  fi
fi
for binary in initdb pg_ctl createdb psql; do
  if [[ ! -x "$postgres_bin/$binary" ]]; then
    echo 'PostgreSQL server tools are missing. Set AI_TEST_POSTGRES_BIN to their directory.' >&2
    exit 2
  fi
done

postgres_runner=()
postgres_user="$(id -un)"
if ((EUID == 0)); then
  if ! id postgres > /dev/null 2>&1 || ! command -v runuser > /dev/null; then
    echo 'Root execution requires the postgres account and runuser.' >&2
    exit 2
  fi
  postgres_runner=(runuser -u postgres --)
  postgres_user=postgres
fi

mkdir -p "$root_dir/artifacts"
postgres_root="$(mktemp -d "$root_dir/artifacts/ai-postgres.XXXXXX")"
# A short, unique socket path supports long checkout paths and concurrent runs.
socket_root="$(mktemp -d /tmp/nursched-pg.XXXXXX)"
postgres_port=55432

cleanup() {
  local result=$?
  trap - EXIT
  if [[ -f "$postgres_root/data/postmaster.pid" ]]; then
    if ! "${postgres_runner[@]}" "$postgres_bin/pg_ctl" -D "$postgres_root/data" -m fast -w stop \
      > "$postgres_root/stop.log" 2>&1; then
      echo "PostgreSQL cleanup failed. See $postgres_root/stop.log" >&2
      if ((result == 0)); then result=1; fi
    fi
  fi
  rm -rf -- "$socket_root"
  printf 'PostgreSQL test exit: %s. Logs: %s\n' "$result" "$postgres_root"
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if ((EUID == 0)); then
  chown postgres:postgres "$postgres_root" "$socket_root"
fi
"${postgres_runner[@]}" "$postgres_bin/initdb" -D "$postgres_root/data" -A trust -E UTF8 --no-locale \
  > "$postgres_root/init.log" 2>&1
"${postgres_runner[@]}" "$postgres_bin/pg_ctl" -D "$postgres_root/data" -l "$postgres_root/server.log" \
  -o "-k $socket_root -p $postgres_port -c listen_addresses=" -w start > "$postgres_root/start.log" 2>&1
"$postgres_bin/createdb" -h "$socket_root" -p "$postgres_port" -U "$postgres_user" ai_history_test
export AI_HISTORY_TEST_POSTGRES_URL
AI_HISTORY_TEST_POSTGRES_URL="$(python - "$postgres_user" "$socket_root" "$postgres_port" <<'PY'
import sys
from urllib.parse import quote, urlencode

user, socket, port = sys.argv[1:]
print(f"postgresql://{quote(user, safe='')}@/ai_history_test?{urlencode({'host': socket, 'port': port})}")
PY
)"
encoding="$("$postgres_bin/psql" "$AI_HISTORY_TEST_POSTGRES_URL" -Atc 'SHOW server_encoding')"
if [[ $encoding != UTF8 ]]; then
  echo 'The test database must use UTF8.' >&2
  exit 2
fi
echo 'PostgreSQL test database: UTF8, Unix socket only.'
set +e
(cd "$root_dir/core" && "${test_command[@]}") > "$postgres_root/tests.log" 2>&1
test_status=$?
set -e
if ((test_status == 0)); then
  tail -n 8 "$postgres_root/tests.log"
else
  tail -n 40 "$postgres_root/tests.log"
fi
exit "$test_status"
