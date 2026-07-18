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

The capability probe uses four possible isolated rounds: timeout, graceful
cancel, finish-now, then intermediate scores. The timeout round is always
exercised so it can record whether the solver returns on its own with
`solver_timeout` or requires `timeout_forced` server termination. A solver
registered for graceful timeout fails that round if it requires
`timeout_forced`. Other traits run only when the server registry confirms them.
Forced cancellation is a server guarantee and is covered by the server tests
rather than this solver probe. Run one configured solver or all solvers with at
least one confirmed trait:

```sh
cd core
python tests/real/solver_capabilities.py --solver ortools/cp-sat
python tests/real/solver_capabilities.py --all \
  --json-output solver-capabilities.json
```

All capability pairs use the large 87-person scenario by default. PuLP/CBC is
listed in `REAL_SCENARIO_UNSUITABLE_SOLVERS` because it cannot reliably find an
incumbent on that scenario. Its graceful-timeout round still uses the large
scenario. Only the `(pulp/cbc, intermediate-scores)` pair uses
`tests/testcases/basics/01_1nurse_1shift_1day.yaml`, allowing the progress
capability to be exercised independently of CBC's real-scenario limitation.

On the large scenario, the bundled CBC 2.10.3 spends the bounded run in the
root relaxation and preprocessing. It does not enter branch-and-bound or
produce an integer incumbent. Default preprocessing may report the
known-feasible model as infeasible or unbounded. Disabling preprocessing can
instead let that phase overrun the internal solver limit. An absent incumbent
in this round is solver behavior rather than a progress-log parsing failure.

The graceful-timeout and intermediate-score rounds request a 10-second solver
limit. The server's hard watchdog starts with the child process and allows the
requested limit plus a 90-second timeout grace period before forced
termination, for a maximum 100-second observation window after solving starts.
Graceful cancel and finish-now use independent large-scenario jobs with a
60-second solver timeout. Cancellation is requested two seconds after solving
starts. Finish-now waits up to 10 seconds for an incumbent before requesting
the current result. Each enabled round also has its own outer subprocess as a
final safety boundary.

The command prints a Markdown table and exits nonzero when any round reports
`FAIL`. `UNAVAILABLE` identifies a missing solver runtime. `INCONCLUSIVE`
means the solver finished before the capability was exercised or finish-now
stopped before a feasible incumbent was available. Use the JSON report for
elapsed times, terminal states, solver statuses, and runtime information.
`NOT_CONFIRMED` means the registry does not claim a cooperative control or
progress capability and the probe did not exercise it.

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
