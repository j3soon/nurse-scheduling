<!-- SPDX-License-Identifier: AGPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# PostgreSQL integration checks in the container

The tests require `AI_HISTORY_TEST_POSTGRES_URL` and a database role that can
create schemas. Without the setting, database cases skip. Each case creates and
drops a temporary schema, so migrations run against an empty schema. Use a test
database, since the migration checks also discard synthetic rows of earlier schemas.

The development container already has the Python dependencies. Use `python`,
`pytest`, and `ruff` directly. PostgreSQL server binaries may still be missing.
Check `pg_config --bindir` and confirm that directory contains `initdb` and
`pg_ctl`. On the Ubuntu development images, install a missing server as root:

```sh
apt-get update
apt-get install -y --no-install-recommends postgresql
```

Run this block from the repository root as root inside the development container.
It creates a fresh UTF-8 cluster under ignored `artifacts/`, listens only on a
Unix socket, runs the affected recovery tests, and stops the server on exit,
including test failure:

```bash
bash <<'BASH'
set -euo pipefail
postgres_bin="$(pg_config --bindir)"
test -x "$postgres_bin/initdb"
test -x "$postgres_bin/pg_ctl"
mkdir -p artifacts
postgres_root="$(mktemp -d "$PWD/artifacts/ai-postgres.XXXXXX")"
postgres_port=55432
chown postgres:postgres "$postgres_root"
runuser -u postgres -- "$postgres_bin/initdb" \
  -D "$postgres_root/data" -A trust -E UTF8 --no-locale \
  > "$postgres_root/init.log"
runuser -u postgres -- "$postgres_bin/pg_ctl" \
  -D "$postgres_root/data" -l "$postgres_root/server.log" \
  -o "-k '$postgres_root' -p $postgres_port -c listen_addresses=" -w start
trap 'runuser -u postgres -- "$postgres_bin/pg_ctl" -D "$postgres_root/data" -m fast -w stop' EXIT
"$postgres_bin/createdb" -h "$postgres_root" -p "$postgres_port" \
  -U postgres ai_history_test
export AI_HISTORY_TEST_POSTGRES_URL="postgresql://postgres@/ai_history_test?host=$postgres_root&port=$postgres_port"
"$postgres_bin/psql" "$AI_HISTORY_TEST_POSTGRES_URL" -Atc 'SHOW server_encoding'
(
  cd core
  pytest -q tests/test_ai_history.py tests/test_ai_reconnect.py
)
BASH
```

The encoding check must print `UTF8`. PostgreSQL refuses to run as root, so the
server commands use the package's `postgres` account. Trust authentication is
limited here to a private test socket with TCP disabled. This is not deployment
configuration. Keep the data and logs for diagnosis under `artifacts/`.

Do not reuse an old cluster with another PostgreSQL major version. The server
version must match the data directory's `PG_VERSION`. If `pg_config` points to a
directory without server binaries, select the installed version under
`/usr/lib/postgresql/<major>/bin/` instead. An absent package can also mean the
container's package index needs `apt-get update`.

For broader validation, replace the final pytest command with
`../scripts/test_core_affected.sh` from `core/`, or run the CI skill's script from
the repository root. Keep setup, the exported URL, and validation in the same
shell. Shell variables do not carry between independent command-tool calls.
