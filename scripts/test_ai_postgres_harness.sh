#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Johnson Sun
# This test is mostly AI generated.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd "$script_dir/.." && pwd)"
mkdir -p "$root_dir/artifacts"
evidence="$(mktemp -d "$root_dir/artifacts/postgres-harness.XXXXXX")"
export POSTGRES_HARNESS_EVIDENCE="$evidence"

"$script_dir/test_ai_postgres.sh" --command python - <<'PY'
import os
from pathlib import Path

import psycopg

with psycopg.connect(os.environ['AI_HISTORY_TEST_POSTGRES_URL']) as connection:
    assert connection.execute('SHOW server_encoding').fetchone() == ('UTF8',)
    assert connection.execute('SHOW listen_addresses').fetchone() == ('',)
    data_dir = connection.execute('SHOW data_directory').fetchone()[0]
    socket_dir = connection.execute('SHOW unix_socket_directories').fetchone()[0]
    connection.execute('CREATE TABLE wrapper_probe (value integer)')
Path(os.environ['POSTGRES_HARNESS_EVIDENCE'], 'success').write_text(data_dir + '\n' + socket_dir + '\n')
PY

set +e
"$script_dir/test_ai_postgres.sh" --command python - <<'PY'
import os
from pathlib import Path

import psycopg

with psycopg.connect(os.environ['AI_HISTORY_TEST_POSTGRES_URL']) as connection:
    assert connection.execute("SELECT to_regclass('wrapper_probe')").fetchone() == (None,)
    data_dir = connection.execute('SHOW data_directory').fetchone()[0]
    socket_dir = connection.execute('SHOW unix_socket_directories').fetchone()[0]
Path(os.environ['POSTGRES_HARNESS_EVIDENCE'], 'failure').write_text(data_dir + '\n' + socket_dir + '\n')
raise SystemExit(17)
PY
status=$?
set -e
if ((status != 17)); then
  printf 'Expected command exit 17, got %s\n' "$status" >&2
  exit 1
fi

# A failed startup command can still leave a running server. Cleanup must find it.
postgres_bin="${AI_TEST_POSTGRES_BIN:-$(pg_config --bindir)}"
export POSTGRES_HARNESS_REAL_BIN="$postgres_bin"
mkdir "$evidence/bin"
chmod 755 "$evidence" "$evidence/bin"
for binary in initdb createdb psql; do
  ln -s "$postgres_bin/$binary" "$evidence/bin/$binary"
done
cat > "$evidence/bin/pg_ctl" <<'SH'
#!/usr/bin/env bash
"$POSTGRES_HARNESS_REAL_BIN/pg_ctl" "$@"
result=$?
if ((result == 0)) && [[ ${*: -1} == start ]]; then exit 23; fi
exit "$result"
SH
chmod +x "$evidence/bin/pg_ctl"
set +e
output="$(AI_TEST_POSTGRES_BIN="$evidence/bin" "$script_dir/test_ai_postgres.sh" --command true)"
status=$?
set -e
if ((status != 23)); then
  printf 'Expected startup exit 23, got %s\n' "$status" >&2
  exit 1
fi
startup_root="${output##*Logs: }"
test -f "$startup_root/stop.log"
test ! -f "$startup_root/data/postmaster.pid"

python - <<'PY'
import os
from pathlib import Path

root = Path(os.environ['POSTGRES_HARNESS_EVIDENCE'])
success = (root / 'success').read_text().splitlines()
failure = (root / 'failure').read_text().splitlines()
assert success[0] != failure[0] and success[1] != failure[1]
for data_dir, socket_dir in (success, failure):
    assert not Path(data_dir, 'postmaster.pid').exists(), data_dir
    assert not Path(socket_dir).exists(), socket_dir
print('PostgreSQL wrapper checks passed: encoding, isolation, command/startup failure status, and cleanup.')
PY
