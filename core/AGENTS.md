# Core Guidelines

The FastAPI backend entry point is `nurse_scheduling/serve.py`.

## Setup And Commands
Run commands from `core/`:

- `uv venv --python 3.12 && source .venv/bin/activate`
- `uv pip install -r requirements.txt`
- `python -m nurse_scheduling.cli <input.yaml> [output.csv] --solver <selector>`: selectors are documented in `../README.md`.
- `pytest --log-cli-level=INFO`: run the normal core test suite.
- `pytest --log-cli-level=INFO <affected_test_paths>`
- `../scripts/test_core_affected.sh`: run changed test files with compact
  output, or the compact normal suite when core source/helper files change.
- `pytest --log-cli-level=INFO tests/real/schedule_ortools_cp_sat.py tests/real/schedule_pulp_cbc.py tests/real/schedule_pulp_cuopt.py`: run the slower bounded real-world checks.
- `python -m nurse_scheduling.cli tests/testcases/real/large-ward-with-87-people-2025-11.yaml --solver ortools/cp-sat --timeout 10 --show-model-build-stats`: print compact real-case model-build statistics.
- `python tests/real/solver_capabilities.py --solver ortools/cp-sat`: probe
  timeout, cancel, and finish-now behavior on the large real scenario.
- `pytest --log-cli-level=INFO tests/test_solver_ortools_cp_sat.py tests/test_solver_pulp_cbc.py tests/test_schedule_ortools_cp_sat.py tests/test_schedule_pulp_cbc.py`: run the primary solver/schedule suites.
- `ruff check nurse_scheduling tests`
- `ruff format nurse_scheduling tests`

After modifying core code, run Ruff and affected pytest suites before finishing.
Prefer `../scripts/test_core_affected.sh` for routine validation. Pass explicit
test paths when a narrower suite is known to be sufficient.

## Server Job Processes
- `run_optimization_process` owns its optimization process tree through
  `server/jobs/process_tree.py`. Tree cleanup is required for PuLP command-line
  backends, which launch external solver executables. OR-Tools runs inside the
  direct optimization child and does not require descendant cleanup.
- The child finish-now event is exclusively for cooperative early completion.
  Cancellation and internal aborts terminate the optimization process tree
  immediately.
- Worker shutdown uses normal claim expiry recovery. Do not add a separate
  persisted shutdown failure unless immediate terminal state becomes required.
- A worker that cannot persist an execution outcome must relinquish its lease.
  Continue only after cleanup succeeds, otherwise stop the claim loop.

## Experimental AI
- Keep optional AI features server-configured and report safe limits through
  `/capabilities`. Treat schedules and attachments as untrusted provider input.
- Bound and validate uploads before provider calls. Do not retain raw
  attachments longer than their documented session behavior requires.
- Keep canonical schedule invariants in `NurseSchedulingData`. Implement
  consumer-specific subsets through explicit Pydantic entry points rather than
  input-controlled or global validation flags.

## Testing
- Normal tests live under `tests/`.
- Resolve input selectors and input-derived invariants in
  `NurseSchedulingData.compiled_schedule`. Scheduler, preference, and export
  phases should consume that representation instead of reparsing YAML fields.
- Treat a validated schedule and its compiled representation as one snapshot.
  Revalidate changed input instead of mutating a validated model and reusing
  stale compiled data.
- Keep server-facing solver traits in
  `nurse_scheduling/server/solver_capabilities.py`. Runtime control checks and
  `/optimize/options` must use that registry rather than duplicate selector
  lists.
- Real-world checks under `tests/real/` intentionally omit pytest's `test_`
  filename prefix. Run them explicitly; do not include them in normal test
  commands.
- Primary suites are:
  `tests/test_solver_ortools_cp_sat.py`,
  `tests/test_solver_ortools_linear.py`,
  `tests/test_solver_ortools_mathopt.py`,
  `tests/test_solver_pulp_cbc.py`,
  `tests/test_solver_pulp_glpk.py`,
  `tests/test_solver_pulp_python.py`,
  `tests/test_schedule_ortools_cp_sat.py`,
  `tests/test_schedule_ortools_mpsolver_cbc.py`,
  `tests/test_schedule_ortools_mathopt_gscip.py`,
  `tests/test_schedule_pulp_cbc.py`, and `tests/test_serve.py`.
  PuLP/GLPK has bounded schedule smoke coverage in
  `tests/test_schedule_pulp_glpk.py`. PuLP Python-API schedule coverage lives
  in `tests/test_schedule_pulp_highs.py` and `tests/test_schedule_pulp_scip.py`.
- Add scheduling cases as fixture pairs under `tests/testcases/**`, typically a
  `.yaml` input with matching `.csv` or `.txt` expected output.
- Use `--show-model-build-stats` when checking or benchmarking model-building
  optimizations against real testcases. It emits a compact aggregated summary
  and suppresses the full schedule output.

## Python Style
- Use 4-space indentation, `snake_case` functions/modules, and `PascalCase`
  classes. Keep type names explicit.
- Treat existing comments and docstrings as durable project knowledge. When
  moving or replacing code, preserve their information near the replacement.
  Do not silently delete them unless the documented behavior is obsolete, and
  explain that decision during review.
- Core linting and formatting use Ruff.
- Every Python file must use the repository module-docstring and AGPL header
  convention documented in `../docs/agent-license-headers.md`.
- For Python tests mostly generated by AI coding agents, add
  `# This test is mostly AI generated.` immediately after the license block.
