# Real-World Scenario Checks

These checks solve larger real-world scenarios with a fixed optimization budget.
They are slower and less deterministic than the normal unit and regression tests.

The Python files in this directory intentionally omit pytest's `test_` filename
prefix so that the default test suite does not collect them.

Run real-world checks explicitly:

```sh
cd core
pytest --log-cli-level=INFO tests/real/schedule_ortools_cp_sat.py
pytest --log-cli-level=INFO tests/real/schedule_pulp_cbc.py
pytest --log-cli-level=INFO tests/real/schedule_pulp_cuopt.py
```

## Solver capability probe

The capability probe uses four possible isolated rounds: timeout, cancel,
finish-now, then intermediate scores. Timeout is always exercised so it can
collect evidence for an unconfirmed solver. Other traits run only when the
server registry confirms them. Run one configured solver or all solvers with at
least one confirmed trait:

```sh
cd core
python tests/real/solver_capabilities.py --solver ortools/cp-sat
python tests/real/solver_capabilities.py --all \
  --json-output solver-capabilities.json
```

All capability pairs use the large 87-person scenario by default. PuLP/CBC is
listed in `REAL_SCENARIO_UNSUITABLE_SOLVERS` because it cannot reliably find an
incumbent on that scenario. Its timeout round still uses the large scenario.
Only the `(pulp/cbc, intermediate-scores)` pair uses
`tests/testcases/basics/01_1nurse_1shift_1day.yaml`, allowing the progress
capability to be exercised independently of CBC's real-scenario limitation.

The timeout and intermediate-score rounds give the solver 10 seconds plus a
50-second return grace period, for a 60-second observation window after solving
starts. Cancel and finish-now use independent large-scenario jobs with a
60-second solver timeout. Cancel is requested two seconds after solving starts.
Finish-now waits up to 10 seconds for an incumbent before requesting the current
result. Each enabled round has its own subprocess so the parent can terminate a
solver that ignores its limit or control request.

The command prints a Markdown table and exits nonzero when any round reports
`FAIL`. `UNAVAILABLE` identifies a missing solver runtime. `INCONCLUSIVE`
means the solver finished before the capability was exercised or finish-now
stopped before a feasible incumbent was available. Use the JSON report for
elapsed times, terminal states, solver statuses, and runtime information.
`NOT_CONFIRMED` means the registry does not claim that capability and the probe
did not exercise it.

To print model-build timing and variable/constraint deltas for the large
scenario, run:

```sh
cd core
python -m nurse_scheduling.cli \
  tests/testcases/real/large-ward-with-87-people-2025-11.yaml \
  --solver ortools/cp-sat \
  --timeout 10 \
  --show-model-build-stats
```

To record a score/comment-count curve for later plotting, write progress events
to JSON Lines:

```sh
cd core
python -m nurse_scheduling.cli \
  tests/testcases/real/large-ward-with-87-people-2025-11.yaml \
  --solver ortools/cp-sat \
  --timeout 180 \
  --progress-output progress.jsonl
```

To record the same progress JSONL while injecting the real-test critical-request
comment formatting rules, use the real CLI wrapper:

```sh
cd core
python tests/real/run_schedule.py \
  tests/testcases/real/large-ward-with-87-people-2025-11.yaml \
  --prettify \
  --solver ortools/cp-sat \
  --timeout 180 \
  --progress-output progress.jsonl
```
