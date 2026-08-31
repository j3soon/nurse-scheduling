---
name: run-ci
description: Run and fix the repository's local CI checks when asked to "Run CI", "Run all CI", or verify all CI locally. Runs core lint and the normal core pytest suite with coverage without CBC, cuOpt, or the three explicit real-scenario tests, then runs frontend lint, build, unit coverage, and Playwright E2E coverage. Fix failures and rerun until the full script passes.
---

# Run CI

Run the bundled script from any directory by calling it with an absolute path
to the skill folder:

```bash
bash /path/to/skills/run-ci/scripts/run-ci.sh /path/to/repository
```

Resolve `scripts/run-ci.sh` relative to this skill directory, not the target
repository. When the repository path is omitted, the script uses the current
working directory.

The script intentionally:

- Excludes every core test file matching `*pulp_cbc.py` or `*pulp_cuopt.py`,
  plus the mixed CBC/cuOpt `test_solver_pulp_progress.py` suite.
- Does not explicitly run the three `core/tests/real/schedule_*.py` scenarios.
- Runs core Ruff format checking, Ruff lint, and the remaining normal pytest
  suite with coverage.
- Uses compact test output flags to keep CI output small. pytest uses the
  flags from `scripts/test_core_affected.sh`
  (`-q --tb=short --disable-warnings --maxfail=1`). Playwright coverage uses
  `--reporter=dot --quiet --max-failures=1`, matching
  `scripts/test_frontend_e2e_affected.sh`. Vitest coverage uses
  `text-summary` reporting instead of the per-file text table. Run focused
  tests with
  `--log-cli-level=INFO` when solver or job logs are needed.
- Runs frontend lint, build, unit coverage, E2E coverage, and the E2E coverage
  report. Coverage commands execute the tests, so do not run duplicate
  non-coverage test commands.
- Does not upload coverage or artifacts.

Do not replace the script with affected-test commands or add excluded solver
tests. When a check fails, diagnose and fix the underlying error while
preserving repository conventions and unrelated user changes. Run a focused
check when useful to verify the fix, then rerun the bundled script from the
beginning. Repeat until the full script passes.

Do not weaken, skip, or alter checks merely to make CI pass. If a required
dependency or Playwright browser is missing, install it using the repository's
documented setup commands, then rerun the script. Report a blocker only when
the failure cannot be fixed locally.
