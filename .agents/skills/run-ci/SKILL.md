---
name: run-ci
description: Run the repository's local CI checks when asked to "Run CI", "Run all CI", or verify all CI locally. Runs core lint and the normal core pytest suite with coverage without CBC, cuOpt, or the three explicit real-scenario tests, then runs frontend lint, build, unit coverage, and Playwright E2E coverage.
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
- Runs frontend lint, build, unit coverage, E2E coverage, and the E2E coverage
  report. Coverage commands execute the tests, so do not run duplicate
  non-coverage test commands.
- Does not upload coverage or artifacts.

Do not replace the script with affected-test commands or add excluded solver
tests. Stop on the first failed check and report the failed command. If a
required dependency or Playwright browser is missing, install it using the
repository's documented setup commands, then rerun the script.
