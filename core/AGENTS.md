# Core Guidelines

The FastAPI backend entry point is `nurse_scheduling/serve.py`.

## Setup And Commands
Run commands from `core/`:

- `uv venv --python 3.12 && source .venv/bin/activate`
- `uv pip install -r requirements.txt`
- `python -m nurse_scheduling.cli <input.yaml> [output.csv] --solver <selector>`: selectors are documented in `../README.md`.
- `pytest`: run the normal core test suite with logs captured unless a test fails.
- `pytest <affected_test_paths>`
- `../scripts/test_core_affected.sh`: run changed test files with compact
  output, or the compact normal suite when core source/helper files change.
- `pytest tests/real/schedule_ortools_cp_sat.py tests/real/schedule_pulp_cbc.py tests/real/schedule_pulp_cuopt.py`: run the slower bounded real-world checks.
- `pytest tests/real/schedule_score_ground_truth.py`: replay the fixed real-world assignment and verify its exact objective score.
- `python -m nurse_scheduling.cli tests/testcases/real/large-ward-with-87-people-2025-11.yaml --solver ortools/cp-sat --timeout 10 --show-model-build-stats`: print compact real-case model-build statistics.
- `python tests/real/solver_capabilities.py --solver ortools/cp-sat`: probe
  timeout, cancel, and finish-now behavior on the large real scenario.
- `pytest tests/test_solver_ortools_cp_sat.py tests/test_solver_pulp_cbc.py tests/test_schedule_ortools_cp_sat.py tests/test_schedule_pulp_cbc.py`: run the primary solver/schedule suites.
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
- The assistant is reachable only from the web frontend, so its schedule tools
  target the frontend subset alone. Validate through
  `ai/validation.py`, and do not expose the canonical backend flavor, which
  accepts shapes the editor cannot represent.
- Frontend validation checks normalized frontend state, not raw import
  compatibility. Do not broaden it merely because an import path can convert
  or repair additional input shapes.
- Keep schedule facts out of the prompt summary in `describe_schedule` and put
  them in a tool result instead. The evaluation asserts that a reading case
  cannot be answered from the summary alone, so listing item IDs or line numbers
  there turns a reading case into a copying case. See
  `test_reading_questions_cannot_be_answered_from_the_prompt_summary`.
- Decide what to fix next by tallying failed tool calls across a whole
  evaluation run, not from one trajectory. A repeated recoverable failure costs
  more than the case that exposed it, and a bounded tool should clamp an
  over-large request rather than refuse it.
- Expose only Pi's default `read`, `bash`, `edit`, and `write` model tools over
  the disposable sandbox. Use `read` for bounded inspection, `edit` for unique
  exact-text replacements, and `write` only for a complete file rewrite. Put
  domain guidance in task-sized reference documents that return related schema
  shapes together instead of adding model-specific tools or fine-grained lookup
  turns. Keep trusted validation after every possible schedule change and the
  structural diff at review, since those catch a dropped entry that still
  parses. Emit an intermediate working-copy preview only after that trusted
  validation.
- Run a provider batch concurrently only when every call is read-only. Preserve
  call order in the returned results, keep mixed or mutating batches sequential,
  and make sandbox close wait for active reads before teardown.
- Keep model-facing tool contracts and output behavior in pinned Pi ports under
  `ai/pi`. Keep E2B execution and service timeout policy in the thin sandbox
  adapter so upstream behavior remains identifiable and testable.
- Retry a provider timeout only before any stream event reaches the caller.
  Once text, reasoning, usage, or a tool call is visible, surface the timeout
  rather than replaying the request and risking duplicate output or tool work.

## Server Authentication
- `API_AUTH_TOKEN` is optional. Unset means the deployment serves without
  authentication, which keeps local runs and older clients working.
- `API_AUTH_REQUIRED` makes a token mandatory and is set in the deployment images,
  so a published backend fails to start rather than serving openly by accident.
  Leave it unset outside those images.
- `/optimize/{job_id}/events` accepts a signed, job-scoped, expiring URL token as
  well as the bearer header, because `EventSource` cannot set headers. Mint it
  into `links.events`; never put `API_AUTH_TOKEN` itself in a URL. Its lifetime
  comes from `ServerSettings.stream_token_ttl_seconds`, which tracks the longest
  run the deployment allows.
- Keep `/info` and `/ready` public. Clients discover the requirement from
  `/info`, and deployment probes must not need credentials. Gate every other
  route with the shared-token dependency.
- The separately deployed AI service uses `AI_AUTH_TOKEN` when configured. Keep
  `/health`, `/ready`, and `/capabilities` public, advertise the effective bearer
  auth requirement through `/capabilities`, and gate every session route when a
  token is set. Native runs may omit auth. Docker Compose services set
  `AI_AUTH_REQUIRED=true`; opting out must be explicit in the env file and must
  leave `AI_AUTH_TOKEN` empty.

## Sentry
- Initialize Sentry before configuration or logging in every first-party
  standalone service process. Use a distinct `app` tag and flush Sentry before
  short-lived processes exit.

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
- Core tests run on Linux, macOS, and Windows in CI. Keep tests platform
  neutral, including paths, line endings, and environment limits.
- Give `pytest.mark.parametrize` explicit `ids` when a parameter is a large
  binary or text payload. Pytest derives the node ID from the parameter value
  and exports it through `PYTEST_CURRENT_TEST`, which fails on Windows once the
  ID exceeds the 32767-character environment variable limit.

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
- For files mostly generated by AI coding agents, add a marker immediately after
  the license block. Use `# This test is mostly AI generated.` for anything under
  `tests/`, including helpers and runners that are not themselves tests, and
  `# This code is mostly AI generated.` for modules in `nurse_scheduling/`. The
  web frontend uses `// This code is mostly AI generated.` the same way. Mark a
  file that was written by an agent, not one an agent merely edited.
