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

The capability probe uses four isolated rounds: timeout, cancellation,
finish-now, then intermediate scores. Timeout and cancellation are always
exercised because the server enforces them for every solver. The timeout round
records whether the solver returns on its own with `solver_timeout` or requires
`process_timeout` server termination. A solver registered for graceful timeout
fails that round if it requires `process_timeout`. Other traits run only when
the server registry confirms them. Run one configured solver or all solvers
with at least one confirmed trait:

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
Cancellation and finish-now use independent large-scenario jobs with a
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

## Performance benchmark

Run the real 87-person scenario in isolated OR-Tools CP-SAT processes with the
Docker workflow. The default normalized compute benchmark performs one
unmeasured warm-up followed by five measured bounded runs:

```sh
./scripts/run_performance_benchmark.sh
```

The wrapper reuses the existing `j3soon/nurse-scheduling:dev` development image
and bind-mounts the current repository read-only. Select another compatible
local image when needed:

```sh
BENCHMARK_IMAGE=custom-benchmark:tag ./scripts/run_performance_benchmark.sh
```

If the default image does not exist, build it with the repository's existing
development Dockerfile:

```sh
docker build -f docker/Dockerfile -t j3soon/nurse-scheduling:dev .
```

The primary score rewards reaching a fixed ladder of real-case objective
thresholds early. For each threshold, a run earns `100 × (1 - first reach time
÷ wall-time budget)` points, with zero for an unreached threshold. The run score
is the mean across thresholds and the machine score is the mean across measured
runs. It is bounded from 0 to 100, with higher values indicating better
real-case solver performance. Each run stops after reaching the top
`4,470,000,000,000` threshold or a 900-second hard wall-time limit. The score
still uses 900 seconds as its denominator after an early success. The benchmark
uses normal nondeterministic parallel CP-SAT and all CPUs visible to Docker. It
does not enable deterministic solver or interleaved-search mode, and it leaves
all solver settings at their defaults except for the wall-time limit.

Customize the measured and warm-up counts or wall-time budget:

```sh
./scripts/run_performance_benchmark.sh \
  --runs 7 --warmup-runs 1 --timeout 300
```

The older solution-quality experiments remain available explicitly. These are
useful for solver behavior but are not normalized computer-power metrics:

```sh
./scripts/run_performance_benchmark.sh --mode search --runs 3 --timeout 300
./scripts/run_performance_benchmark.sh \
  --mode search --runs 5 --timeout 300 --target-score SCORE
```

Run benchmarks only while the host is otherwise idle. No CPU or memory limit is
applied by the wrapper. Compare machines only when their scenario hash, core
source hash, OR-Tools version, wall-time budget, and Docker CPU
visibility policy match. The benchmark harness hash must also match. The report
includes sample variance, standard deviation, and coefficient of variation.
Compare the mean primary score because it averages independent bounded runs.
A high coefficient of variation still indicates that more runs are needed.

Reports are written under the repository-root
`artifacts/performance-benchmarks/` directory. Each report records the scenario
and core source hashes, application and OR-Tools versions, CPU visibility,
initial load average, per-run logs, threshold reach times, normalized attainment
scores, final objectives, solver time, and end-to-end time. Both modes record
raw progress JSONL.
`summary.md` is the human-readable result and `report.json` is the stable
machine-readable record. Solver time excludes parsing, model construction, and
export. End-to-end time includes those phases but excludes Docker image build,
container startup, and Python process startup. The per-run `processSeconds`
field includes Python startup for diagnostic context.

For matching compute reports, use the mean attainment score as the normalized
machine score. This score ranks performance on the real solver workload. It is
not a linear claim that one computer has a specific multiple of another's raw
CPU throughput.

The benchmark currently fixes the solver to `ortools/cp-sat`. Both modes record
score events, but neither persists intermediate schedule contents. That belongs
to the separate intermediate-solution corpus workflow.
