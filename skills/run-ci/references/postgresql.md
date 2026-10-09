<!-- SPDX-License-Identifier: AGPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# PostgreSQL integration checks in the container

The tests require `AI_HISTORY_TEST_POSTGRES_URL` and a database role that can
create schemas. Without the setting, database cases skip. Each case creates and
drops a temporary schema, so migrations run against an empty schema. Use a test
database, since the migration checks also discard synthetic audit rows.

The development container already has the Python dependencies. Use `python`,
`pytest`, and `ruff` directly. PostgreSQL server binaries may still be missing.
Check `pg_config --bindir` and confirm that directory contains `initdb` and
`pg_ctl`. On the Ubuntu development images, install a missing server as root:

```sh
apt-get update
apt-get install -y --no-install-recommends postgresql
```

Use the checked-in wrapper from the repository root. It supports root execution
through the `postgres` account and non-root execution through the current account.
Each invocation creates a fresh UTF-8 cluster, disables TCP, stops its server on
exit, and keeps data and compact logs in the ignored `artifacts/` directory:

```sh
# Default history and reconnect suites.
./scripts/test_ai_postgres.sh

# An explicit test node. Selection inspection needs no PostgreSQL installation.
./scripts/test_ai_postgres.sh --list core/tests/test_ai_history.py::test_postgres_duplicates_and_reconnection
./scripts/test_ai_postgres.sh core/tests/test_ai_history.py::test_postgres_duplicates_and_reconnection

# Committed and working changes since the branch base.
./scripts/test_ai_postgres.sh --base origin/dev

# Collect focused diagnostic failures without a first-failure limit.
# Explicit commands run from core/.
./scripts/test_ai_postgres.sh --command pytest -q --tb=short tests/test_ai_history.py tests/test_ai_reconnect.py
```

The wrapper sets `AI_HISTORY_TEST_POSTGRES_URL` only for its child command and
preserves that command's exit status. It prints the log directory and the test
summary. Read `tests.log` there when more failure detail is needed. Each invocation
uses a distinct short Unix socket directory, so concurrent runs do not share a
cluster or bind a TCP port. The socket directory is removed after shutdown.

Do not reuse an old cluster with another PostgreSQL major version. If `pg_config`
points to a directory without server tools, select the matching installed version:

```sh
AI_TEST_POSTGRES_BIN=/usr/lib/postgresql/14/bin ./scripts/test_ai_postgres.sh
```

The version is an example. Check that the selected directory contains `initdb`,
`pg_ctl`, `createdb`, and `psql`. The wrapper does not install tools. Root execution
also requires `runuser` and the package's `postgres` account. Trust authentication
is limited to the private test socket with TCP disabled. This is test configuration.

Validate wrapper changes with `./scripts/test_ai_postgres_harness.sh`. It checks
UTF-8 encoding, TCP disablement, fresh-cluster isolation, failure status, and cleanup
against actual PostgreSQL servers. `./scripts/test_affected_harness.sh` checks
selection forwarding without requiring PostgreSQL.
