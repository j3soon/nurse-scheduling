<!-- SPDX-License-Identifier: AGPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Validate AI refactor slices

Validate each coherent slice before committing. Start with deterministic checks
that cover its changed interfaces, then run the applicable broader checks below.
Tooling or documentation changes do not require browser or live evaluations.
The module's `AGENTS.md` remains the authority for required checks.

Run these examples from the repository root. Replace the example paths and
`origin/dev` with the affected tests and the series base. Use `--list` once when
selection is uncertain. After committing, use `--base REF` so selection includes
the committed changes rather than only the working diff.

## 1. Diagnose with focused deterministic tests

Run the regression and a contrasting control. For contract changes, cover both
the producer and consumer. For persistence changes, include restart or migration
checks against PostgreSQL.

```sh
./scripts/test_core_affected.sh core/tests/test_ai_lifecycle.py
./scripts/test_ai_postgres.sh core/tests/test_ai_history.py::test_postgres_duplicates_and_reconnection
(cd web-frontend && bun run test:affected -- src/app/experimental-ai/aiClient.test.ts)
```

The affected wrappers stop on the first failure. If integration failures appear,
collect the related deterministic failures once without that limit:

```sh
./scripts/test_ai_postgres.sh --command pytest -q --tb=short tests/test_ai_history.py tests/test_ai_reconnect.py
(cd web-frontend && bunx vitest run src/app/experimental-ai/aiClient.test.ts src/app/experimental-ai/sessionEventRouter.test.ts --reporter=dot)
```

Group failures by their shared interface or invariant. Fix each group, then rerun
its failed cases and controls. Do not use full CI, browser tests, or live cases to
collect deterministic failures that a focused suite can expose.

The [PostgreSQL wrapper guide](../../run-ci/references/postgresql.md) describes
tool requirements and retained logs. Confirm that database cases ran. A passing
suite with those cases skipped does not validate persistence.

## 2. Check the affected backend and frontend

Once the slice is coherent, run the affected module wrappers. They include lint
and select tests from committed and working changes. Use the PostgreSQL wrapper
when the backend slice changes persistence or reconnect behavior:

```sh
./scripts/test_ai_postgres.sh --base origin/dev
# For backend changes that do not need PostgreSQL:
./scripts/test_core_affected.sh --base origin/dev
(cd web-frontend && bun run test:affected -- --base origin/dev)
```

Choose the backend command that applies, rather than running both. Run frontend
checks when frontend files change. Broaden checks if a failure exposes a wider
dependency. Do not repeat the full affected suite after each individual fix.

## 3. Check affected browser behavior

Run the relevant browser specs when the slice changes session actions, replay,
or visible state. Deterministic API and client tests do not prove browser behavior.
The runner builds the current checkout and starts an isolated server:

```sh
(cd web-frontend && bun run test:e2e:affected -- e2e/experimental-ai-basic.spec.ts e2e/experimental-ai-proposal.spec.ts)
```

Select specs explicitly for app changes, since browser coverage cannot be inferred
from imports. Use the full browser suite only when the affected behavior requires it.

## 4. Smoke-test affected model behavior

Run selected live cases when changes affect model instructions, tools, provider
requests, or conversation context. Choose cases for that behavior, including a
contrasting control for ambiguity or scope changes. For example:

```sh
AI_ENV_FILE=/absolute/checkout/docker/.env.staging ./scripts/run_ai_eval.sh --case ask-people-count --case approve-then-follow-up-edit --jobs 4
```

Use an existing ignored credential file without printing its contents. Linked
worktrees may need its absolute path. Four concurrent case jobs are the tested
default. Follow `core/AGENTS.md` for repeated comparisons and broader evaluation
criteria. One passing live run is a smoke check, not a performance measurement.

## Report the result

Record the commit range, commands, selected cases, pass counts, and relevant skips
in the review artifact. State which broader checks were omitted and why. After a
rebase, inspect changes from the new base and rerun checks for changed behavior.
Reuse prior evidence only when its tested inputs and relevant configuration match.
