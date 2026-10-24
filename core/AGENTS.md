# Core Guidelines

The FastAPI backend entry point is `nurse_scheduling/serve.py`.

## Setup And Commands
Check `test -f /.dockerenv` first, per the root `AGENTS.md` environment
section. In a dev container the checkout mounts at `/workspace/core`, and
project packages are installed system-wide, so run `python`, `pytest`, and
`ruff` directly. On a host checkout, run commands below from your local
`core/` clone and create the virtual environment once with
`uv venv --python 3.12 && source .venv/bin/activate`.
- `uv pip install -r requirements-optional.txt`: the development install. See
  the Dependencies section below.
- `python -m nurse_scheduling.cli <input.yaml> [output.csv] --solver <selector>`: selectors are documented in `README.md`.
- `pytest`: run the normal core test suite with logs captured unless a test fails.
- `pytest <affected_test_paths>`
- `../scripts/test_core_affected.sh`: run full Ruff checks and compact affected
  pytest suites. AI code, guidance, tests, shared AI fixtures, and deleted AI
  files run all `test_ai_*.py` files. Other source, helper, dependency, and deleted-file changes run the
  normal local suite, excluding optional PuLP CBC, cuOpt, and mixed progress
  suites. Tests marked `requires_solver` skip automatically when their optional
  runtime package is absent. An installed runtime that fails its availability
  check still stops the script. Use `--skip-unavailable-solvers` to skip those
  tests too.
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
test paths when a narrower suite is known to be sufficient. Use `--base REF` to
include committed branch changes since the merge base with `REF`, `--list` to
inspect selection without running checks, or `--full` for the normal local
suite. Run optional solver and real-scenario suites explicitly when affected.

For AI refactor slices, use the
[AI validation ladder](../skills/implement-change-series/references/ai-validation.md)
to choose focused, affected, browser, and selected live checks. For AI persistence
checks, use `../scripts/test_ai_postgres.sh` with explicit test paths or `--base REF`.
It creates a fresh UTF-8 cluster, stops it on exit, and retains compact logs. See
the [PostgreSQL wrapper guide](../skills/run-ci/references/postgresql.md) for tool
requirements. Confirm that database cases ran. A passing suite with those cases
skipped does not validate persistence.

`ConnectionInfo.dsn` omits passwords. Preserve `ConnectionInfo.password` when
passing database URLs to subprocesses. Check password authentication separately
from the trust-based local harness.

Read-only admin commands must not call `ChatHistory.initialize`, which applies
migrations and prunes sessions. Enforce read-only transactions in PostgreSQL
and truncate prompt previews in SQL before returning them to Python.
When an admin command selects a deployment environment file, print its path to
stderr. Do not replace an explicitly selected file with a fallback.

## Dependencies
- `requirements.txt` is the minimal runtime set. Deployment images install only
  it, so a small file keeps those builds fast. Add a package there only when
  the CLI, the backend, or the AI service imports it at runtime.
- `requirements-optional.txt` starts with `-r requirements.txt` and adds the
  extra solver backends, the sandbox-only attachment tool packages, and the
  test and lint tooling. It is the development and CI install.
- A package a sandbox tool imports belongs in the optional file even when the
  tool ships under `nurse_scheduling/`. Those scripts are uploaded and run
  inside the E2B image, which installs its own pinned copies, and only the
  tests import them here. Keep the two pin sets in step.
- Verify sandbox dependency changes in a rebuilt image with a synthetic script.
  A successful host import or fake-backend test does not prove availability in
  the deployed template. State which template was tested and whether production
  still needs a rebuild.
- Keep an optional solver reachable through a lazy import and let
  `server/solver_options.py` report it unavailable. It already treats
  `ImportError` as unavailable, so a missing optional backend must degrade
  rather than break startup.
- Verify a dependency move by installing `requirements.txt` alone into a
  throwaway virtual environment, then importing `nurse_scheduling.cli`,
  `serve`, `ai_serve`, `server.diagnostic`, and `server.usage_report`, and
  running one CLI solve with `--prettify` to reach the XLSX export path.
  Reading the imports is not enough, because transitive-only packages such as
  the `jinja2` that `pandas.DataFrame.style` needs have no import statement.

## Service Monitoring
- Initialize Sentry with the application build version, not the API version.
  Standalone services use `version.get_app_version()` and keep a distinct `app`
  tag. API services also pass their API version for event tags and log attributes.
- Services that re-read raw request bodies with a custom `Request` wrapper, such
  as the AI upload endpoint, must initialize Sentry with
  `fastapi_integration=False`. The SDK's FastApiIntegration reads
  `request.json()`/`request.form()` before the handler, which drains the body
  stream and hangs the re-read.
- `_should_enable_sentry()` disables Sentry under pytest, so integration
  wiring bugs only surface in deployed environments. After changing
  `init_sentry` options or integration flags, smoke-test the affected
  endpoints on a staging deploy.
  Use `configure_service_logging` for the shared service logging defaults.
  Short-lived services flush Sentry in a `finally` block before exit.
- Log a caught failure with its exception through `logger.exception` or
  `exc_info`. Do not drop the exception or keep only its type to keep data out
  of logs, because sending that data to Sentry is acceptable. Keep credentials
  out with the `event_scrubber` in `init_sentry` instead.

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
- A background loop that retries a dependency on a fixed interval must wrap its
  failures in `RepeatedFailure`, so one outage reports once and backs off rather
  than reporting every attempt. Report the recovery through
  `report_outage_recovery`, because a failure reaches Sentry as an error log
  while the warning that ends it never would.
- A worker that cannot persist an execution outcome must relinquish its lease.
  Continue only after cleanup succeeds, otherwise stop the claim loop.

## Experimental AI
- Prioritize maintainability, readability, and simplicity. Avoid over-engineering.
  Use Pi agent v1.0.0 as a reference for AI chat architecture and design philosophy.
  Clone external reference code under the ignored repository-root `artifacts/`
  directory and record the inspected revision in related developer documentation.
  Preserve upstream compaction prompt text exactly and record its revision and
  hashes. Keep project-specific workspace guidance in the main system prompt
  instead of duplicating it in compaction prompts.
- `AgentSession` owns conversation changes, steering, applied schedules, and
  the shared foreground and optimizer-review execution path. `SessionStore`
  owns access, expiry, and retained-byte budgets. `SessionRecovery` owns ordered
  recovery writes and eviction pins. `SessionEventStream` owns bounded replay.
  Keep HTTP routes thin.
- Keep conversation entries independent of provider wire messages. Derive model
  requests and retained history through `context.py`. Count retained partial text
  in session byte budgets even when model requests omit the failed response.
  Preserve completed exchanges and append a note when the workspace is discarded. Retain completed tool exchanges and native reasoning metadata across runs.
  Replay opaque metadata only to its original endpoint, API, and model. Keep the
  stored metadata intact when switching models. Release tool images after session
  finalization and omit failed or incomplete native output from provider requests.
- Keep compaction entries in the ordered transcript. Apply a summary only after
  every summary request completes, and invalidate summaries from failed or
  cancelled runs. Keep a summary and its referenced recent tool messages together
  during retention. Reset older usage estimates at each compaction boundary.
  Keep app-event indices tied to transcript entries across compaction and retention.
  Keep summary requests visible in provider cost records, but keep their text out
  of the answer stream. Use `tests/test_ai_compaction.py` for these contracts.
  Test chunked summaries through the provider's token-limit calculation, including
  updates with a previous split-turn summary and small model context windows.
  Coalesce streamed context estimates with text batches. Replace token estimates
  with provider usage without adding estimates to billed usage or cost totals.
  Test history character and message thresholds without model context metadata.
  For live cross-run checks, use `../scripts/test_ai_compaction_live.sh` with
  `AI_ENV_FILE`. It runs four concurrent scenarios through the real session API
  and prebuilt E2B sandboxes. A smaller history budget forces compaction.
  Select two distinct available models that both report a context limit.
  Check remembered file context separately from file availability in the new VM.
- Apply queued steering before each follow-up provider request, including requests
  after refused tool batches. Reject conflicting provider finish reasons and any
  further output after a completion signal.
- `Agent` owns observable model-loop state. `agent_loop` executes registered
  `AgentTool` contracts and derives concurrency from each tool's read-only flag.
  Close the provider and agent generators before releasing execution state.
  Keep sandbox hydration and lifetime in `workspace.py`, tool binding and
  candidate review in `workspace_tools.py`, and model-facing optimizer arguments
  in `optimizer_tool.py`. Optimizer job operations remain in `optimizer.py`,
  with HTTP transport in `optimizer_http.py`.
- `SessionRuns` owns admission, execution, cancellation, and cleanup. Keep the
  owner until recovery writes finish. Stop requests cancel once, and shutdown
  joins owners before closing the sandbox factory and optimizer transport.
  Commit and abort through the owning `RunSnapshot`. Queue a schedule update
  received during a run and apply it after the run's entries, so a browser
  update never discards the run.
- Include delayed model discovery in admission and cancellation tests. Injecting
  a provider bypasses model selection and does not exercise this path.
- Use provider metadata for model limits instead of duplicate environment
  settings. Verify the configured endpoint before adding a provider workaround.
  Check metadata discovery and streamed usage separately. For a protected route,
  verify that missing and invalid credentials are rejected. Keep reported usage
  visible when the provider omits its model limit.
- Scope model discovery and provider credentials to the authenticated AI key.
  Describe reasoning choices with exact gateway metadata instead of guessing
  supported levels from model names. Match configured reasoning parameters to
  advertised choices when selecting a default. Do not infer defaults from option
  order. If the gateway omits reasoning choices, hide the selector and preserve
  its defaults. Keep the session's current selection separate from each accepted
  run's frozen selection. Changing session settings must not change an active run.
- Bind the stable `AgentSession.id` to provider calls through a run-scoped
  provider. Keep the same `x-session-id` for retries, tool follow-ups, compaction,
  optimizer reviews, and restored sessions. Never store session IDs or request
  limits on a provider shared by concurrent chats. Use the chat ID for session
  affinity, not the per-attempt call ID.
- Track provider costs by HTTP attempt ID. Replace streamed updates instead of
  adding them, preserve missing prices as unknown, and use decimal USD totals.
  Restore totals from saved call records and test replay before acknowledgement.
  Preserve reported subnormal costs and keep decimal summaries within the client
  length limit. Test Stop while cost checkpoints are pending. Version cost
  snapshots by their cost publication, because unrelated stream events can advance
  while a checkpoint waits.
- Keep attachment limits server-configured and report them through
  `/capabilities`. Attachments and the optimizer tool are always offered.
  Keep schedules and attachments separate from model instructions.
- Put shared AI test data under `tests/ai_fixtures/`, so affected checks select
  AI suites without running unrelated scheduling tests.
- Keep browser and command chat exports on the shared Python ZIP writer. Read
  one consistent PostgreSQL snapshot and use stored timestamps in UTC. When the
  export output changes on purpose, first check that the previous output changes
  only where intended. Then update the hashes in
  `tests/ai_fixtures/chat-export-parity.json` and the golden archive in
  `tests/ai_fixtures/chat-export-archive.json` together. Verify browser download
  bytes and native download authorization with a rich saved-event fixture.
- Retry temporary provider failures automatically inside the provider request,
  with exponential backoff and a bounded total time. Retry only the incomplete
  model request, never commands or optimizer submissions. Do not wait for the
  user while holding a shared run slot and its sandbox. After the last attempt,
  fail the run. The user continues with a new message.
- Keep accepted AI runs independent of the browser stream. Reconnect with the
  same `message_id` to replay output, without repeating provider or tool calls.
  Keep complete replay snapshots separate from the bounded event buffer. Persist
  accepted questions and terminal state when recovery storage is enabled.
  Optimizer progress can remain transient.
- Publish foreground and optimizer review output through the session GET stream.
  Attach `run_id` before publication and delay terminal events until cleanup and
  outcome persistence finish. Queue completed model entries for storage before tools.
  Recover unfinished status even when a terminal publication was saved. Retry failed
  final outcome writes during shutdown while recovery storage is still available.
- Append database migrations without renaming previously applied files. Test an
  upgrade from the deployed schema with saved sessions, message IDs, and Stop
  requests. Document backup and rollback when the old code cannot read the new schema.
- Deliver terminal and optimizer status events even when their recovery write
  fails. When a call that could not fail becomes an awaited write, check every
  caller's failure path. Each caller must still release the session and report
  a terminal event.
- Keep durable entry identity separate from SSE cursors. After combining text
  fragments, restore complete output with a replacement snapshot. Test a cursor
  inside a combined entry and an entry crossing the replay tail boundary.
  Save execution status with terminal output and conversation context instead
  of inferring status from a bounded replay buffer.
  Break saved-event timestamp ties with event IDs. A batch can share one
  database transaction timestamp.
- Keep execution metadata on recovery sessions and runs. Use one expiry policy
  for content and metadata instead of adding a second conversation log.
- Test Stop before acceptance, during execution, and after completion but before
  acknowledgement. Verify recovery after buffer overflow and backend restart,
  including session ownership and expiry. Use an isolated UTF-8 PostgreSQL
  database with fresh migrations for persistence tests.
- Test a graceful shutdown separately from a crash. Seeded running rows cover
  only a crash. Exit the application lifespan during a turn, then check that
  recovery reports a restart instead of a user Stop.
- A turn owner saves the outcome after the event task ends, and `asyncio.run`
  cancels an owner that is still running when the test returns. A test that runs
  AI turns directly must wait for the owners in `app.state.runs` before it
  checks saved recovery records.
- Use one application lifespan when a test simulates several browsers. Entering
  a nested `TestClient` context starts and stops the same application again.
- Entering the AI application lifespan calls `E2BSandboxFactory.prepare`, which
  publishes the configured remote template. Reuse the existing template in live
  lifecycle smoke tests unless the image build is part of the check.
- A fake provider that sleeps between fragments starts each delay only after
  the consumer asks for the next event. A network stream keeps arriving during
  that work. Treat such stream timings as an upper bound.
- Bound uploads before provider calls and place them under fixed sandbox paths.
  Archive uploads, generated downloads, and optimizer files until the session
  expires. Removing a file detaches it from active use without deleting its archive.
  With recovery storage, keep upload metadata in sessions and run snapshots.
  Release bytes only after a successful save, and load persisted files one at a
  time during sandbox hydration. Count all pending file writes, memory-only uploads, and
  generated downloads against the session memory budget. Count every stored file
  version, including removed files, against `AI_MAX_ARCHIVE_BYTES` before accepting it.
  Test removal during a storage outage. Keep unsaved file bytes in the pending
  archive until a successful write, even after the user removes the active file.
  Keep removed upload paths reserved through restart, so reused IDs cannot change
  the file version referenced by an earlier transcript entry.
  After rejecting optimizer files, check that a restart does not load an older
  workbook as the latest result.
- Bound sandbox file and command output bytes while receiving them. Truncating
  tool output after buffering does not bound the AI service's memory use.
- Test file workflows across message boundaries and session expiry. Check the
  bytes delivered by the download API and the files loaded into the next VM.
  A printed workspace path does not prove delivery or retention.
- Check workbook text types after all download processing, including person ID
  restoration. User text that resembles a formula or an Excel error must stay text.
- Put fixed model instructions in a manifest-tracked prompt segment under
  `ai/prompts/`, so they get a hash, linked cases, and a benefit witness.
  `build_provider_messages` appends only request-specific values, such as a
  configured limit or the current time.
- Keep model-facing prompts and intermediate messages concise. Avoid repeated
  warnings about malicious uploads or prescribed workbook-inspection commands.
  Rely on sandbox and server controls for security, and give generated artifacts
  exact paths when available.
- Keep bundled attachment helpers general and optional. Preserve meaningful
  source data such as spreadsheet formulas and cached values, report truncation,
  and let the agent write a focused sandbox parser when a helper is insufficient.
  Check the helper catalog and `--help` before generating read-only parsing or
  counting code. Add recurring missing operations to a maintained inspector.
  Keep source inspection separate from schedule construction and policy audits.
- Fix repeated representation failures at the data boundary before adding prompt
  exceptions. Use the app's YAML 1.2 semantics for both reading and writing
  schedule data. Prefer the installed library over custom scalar converters.
  Keep schema validation in the trusted server instead of asking the model to
  maintain a second validator.
- When adding a bundled reference, include it in sandbox hydration, production
  Docker copy paths, and evaluation reference hashes.
- Prefer one inspector per file format for related read-only operations.
  Reuse its loading and validation for uploaded and generated files. Keep
  schedule-specific calculations separate when they require schedule context.
  Group related schedule analyses in one inspector when they share an assignment
  reader and source context.
- Keep the agent run deadline separate from the sandbox provider's continuous
  runtime limit. Paused time still counts toward the agent run deadline.
- Separate command execution deadlines from provider connection timeouts. Reuse a
  sandbox after a command timeout only when process cleanup is verified. Keep
  shell commands single-attempt because a lost acknowledgement does not prove
  they stopped or that replay is safe.
  Evaluate tool deadlines through the tool's timeout parameter. Shell timers can
  start separate process groups and exercise a different cleanup path.
- Sandbox allocation is lazy. Only file tools and optimizer start need a
  sandbox. Optimizer status and finish-now controls must not allocate or resume
  one. Tests that verify attachment hydration must call a sandbox tool.
- Keep backend schedule format invariants in `NurseSchedulingData`. Implement
  consumer-specific subsets through explicit Pydantic entry points rather than
  input-controlled or global validation flags.
- Parse schedules through `loader._load_yaml`, including comparisons of draft
  schedules. It bounds nesting and alias expansion before constructing data.
  Direct `YAML.load` calls bypass those bounds.
- Parse, validate, and compile schedules in worker threads, not on the event
  loop. One large schedule can take most of a second, which stalls every
  session's stream.
- The assistant is reachable only from the web frontend, so its schedule tools
  target the frontend subset alone. Validate through
  `ai/validation.py`, and do not expose the full backend schedule format, which
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
- For irreversible evaluation trajectory violations, prefer stopping at
  `tool_start` before execution. Retain the attempted call in the trace so a
  known behavioral failure does not become an avoidable command timeout.
- For AI behavior changes, run deterministic affected pytest checks first. Then
  smoke-test the smallest relevant live evaluation set with repeatable
  `./scripts/run_ai_eval.sh --case CASE_ID` selectors from the repository root.
  Check ignored `docker/.env` and `docker/.env.staging` before reporting missing
  credentials. Set `AI_ENV_FILE` to the existing file when evaluating a linked
  worktree.
  Include a contrasting control for ambiguity or scope changes. Expand to a
  category or tag only when the changed behavior spans it or a selected case
  reveals a neighboring risk. A bare evaluation command exits without running
  cases. Use `--tuning` to opt into the default tuning set.
- When a helper, its catalog entry, a fixture or a grader changes, re-measure
  each prompt receipt that it makes stale in the same commit. CI requires a
  current receipt for every shipped clause, so a later repair leaves every commit
  in between failing. List stale steps with `validate_prompt_evidence` on each
  step separately, because the CI test stops at the first one. When the fresh
  comparison shows no benefit, keep the old receipt stale and report the step.
  Do not copy the new fingerprints into it.
- Count exceeded model-output limits as behavior failures, not infrastructure
  outages. Count invalid or oversized generated downloads as behavior failures
  too. Keep the limit reason and partial trace. Keep provider connection and
  sandbox availability failures separate.
- Before live import comparisons, check an independent correct proposal against
  both frontend validation and the case grader. Check cell-to-format associations
  and finite weights, not just whether the inspector reports colors.
- Reuse production response formatters in controlled evaluations. Shortened mock
  replies can change the agent's decisions.
- Treat one provider pass as a smoke check. Before claiming a tuning improvement,
  repeat affected cases at least three times with the same concurrency and compare
  pass rate, infrastructure failures, turns, and tokens with a recorded baseline.
  Treat success rate, tool calls and reads, turns, latency, and provider token
  categories as first-class comparison metrics. Report before/after means and
  mean token deltas with sample standard deviations and usable pair counts.
  Keep all metrics in full reports. User-facing summaries may show only material
  changes. Compare costs on matched passing repetitions with complete telemetry,
  retain every attempt in reliability counts, and never count missing usage as zero.
  With only one matched passing pair, report cost changes as preliminary and
  standard deviation as unavailable. Repeated correctness does not establish
  repeated performance gains.
  Reserve `--tuning` for broad changes or final tuning confirmation.
  Use `--full` only when explicitly requested, for release-level confirmation,
  or when cross-cutting behavior could affect cases outside the tuning set.
  Otherwise report the selected cases and that the wider evaluation was not run.
- For live AI evaluations, load provider and E2B credentials from the ignored
  repository-root `docker/.env`, or `docker/.env.staging` if it does not exist,
  in the evaluation process. Never print or commit credential values. Check
  that the selected file and required values exist before starting. If absent,
  report the missing configuration instead of running a known-to-fail evaluation.
  Leave `--jobs` unset to discover provider capacity, capped at 20 case jobs.
  Reuse `AI_PROVIDER_BASE_URL` and `AI_PROVIDER_API_KEY` for model metadata
  and cached deployment health checks.
  Missing health uses a conservative fallback of at most four jobs. Keep
  concurrency equal across variants when comparing performance.
- Pair ambiguous-language cases with exact-target controls so clarification
  guidance does not teach the agent to ask when the user already supplied a
  unique ID. Keep structurally different fixtures under a `holdout` tag. Do not
  tune prompts directly against one held-out trajectory.
- Keep `nurse_scheduling/ai/prompts/system-steps.json` aligned with the ordered
  production prompt sections. Give independently evaluated policies separate
  prompt fragments and targeted cases. Each step must have one intent and be
  understandable on its own, including its trigger and scope limits. A shared
  workflow or testcase does not make independent behaviors one intent.
  Split a new intent before evaluating it, including one exposed by a failed
  control. After splitting a step, measure each extracted policy separately.
  Do not copy the bundled receipt to the new steps.
  Keep each receipt tied to that policy's comparison.
  Compare a changed step against its immediately
  previous prefix on its targeted cases, repeating three to five times. Treat linked
  cases as hypotheses until a clean comparison shows better outcomes or an
  explicit relative cost gain. Run full-prompt ablation only when requested or
  when a suspected interaction needs investigation. Extend selected cases up
  to ten paired trials only for an explicitly requested deeper investigation.
- Order ladder fragments so each tested prefix includes the policies its cases
  need. For example, a case that starts optimization needs the background-start
  rule before a separate goal-policy rule. If later guidance competes with a
  policy, test that policy after the competing guidance. Rerun its adjacent
  comparison after moving it. Do not reuse evidence from a different prefix.
- Separate final correctness from the tool-call behavior a prompt claims to
  improve. Preserving optimizer input does not prove a direct start or solver
  quality. Inspect every repetition before describing its trajectory. Add a
  tool-usage assertion when that behavior is a required outcome.
- Ship a prompt clause only with a reviewed, clean repeated benefit witness.
  Bind the receipt to the clause, parsed testcase, and fixture with one input
  fingerprint. Keep tracked receipts to aggregate counts, model, and concise
  scope notes. Preserve exact contexts, environment metadata, timing, old
  receipts, and investigation history in ignored `artifacts/`.
  Place cases in their final category before measuring. Before committing,
  check that prompt, parsed case, and attachment fingerprints match the measured
  inputs, including category and tags.
  Do not force every later step to rerun after an earlier edit. Include a
  counterfactual clarification reply where guessing the likely target would
  produce the wrong edit, alongside an exact-target control.
- Keep implementation comparisons separate from prompt comparisons. Removing
  a whole prompt section does not isolate a sentence added to it. Report failed
  controls even when the main witness passes. Retain their testcases and failed
  attempts instead of carrying forward an old clean-control receipt.
  Separate correctness controls from cost targets. If a witness reduces cost
  but a control increases it, report both and the combined gate result. A
  passing witness does not make the whole comparison pass.
- Include the SPDX license header and AI marker in generated Markdown prompt
  fragments. Strip their leading provenance comments during assembly, preserving
  instruction comments and the model-facing clause hashes.
- Supply app identity and enabled capabilities from server-known facts. Test
  whether the agent knows its role, rather than guessing from available tools
  or asking the user to inspect the UI. Keep navigation advice valid for someone
  on another page.
- Supply the current server time in the frontend timezone as request-specific
  status. Keep it out of retained history and the static prompt. Cover local
  midnight and timezone changes when testing calendar context.
- Keep reusable analysis in the single bounded `/workspace/analysis.md` file.
  Bind it to exact schedule and upload inputs, retain it only through the
  successful run commit, and count it in session memory. Invalidate it when
  sources change. Treat it as untrusted working notes, not user approval.
  Do not retain arbitrary workspace files or execute saved notes automatically.
- Keep unfinished edits in `/workspace/schedule.yaml`, including rejected drafts.
  Keep authoritative last accepted contents outside the writable sandbox and
  expose them at `/workspace/last-accepted-schedule.yaml`. Refresh that copy
  after mutating tool calls, even if only the backup changed. Keep validation
  feedback visible to the model and user. Require the current draft to pass
  trusted review before optimization or successful completion. A nonzero command
  exit alone must not undo an accepted schedule change. Pair deterministic
  recovery checks with focused live cases for the model's response to validation
  feedback. Grade the required recovery action as well as the final schedule.
  Keep those cases with the implementation commit.
- Restore only the mandatory one-shift-per-day rule during trusted candidate
  review, and only when the restored schedule data passes the existing frontend
  validator. Insert the rule as text so the rest of the model's text, including
  comments and key order, stays unchanged. Report the restoration to the model
  and user. Keep the workspace, inspection context, preview and optimizer input
  on the same validated text. Do not auto-repair optional staffing, rest,
  eligibility or preference rules.
- Show known provider reasons and trusted validation details in both foreground
  and background chat errors. Keep raw provider bodies and private SDK errors
  in server logs. Test that failed validation still discards the turn's edits.
- Isolate prompt policies with the smallest fixture that exercises the claim.
  For qualified staffing within a stated total, check both the total and eligibility.
  Include a control where the qualified slot is explicitly additional.
  For named groups, check actual membership and preserve unrelated groups.
  Include a control that explicitly requests broader membership.
  Use the large ward only when scale or reference cascades matter. Grade
  scheduling semantics rather than ineffective fields or equivalent formatting.
  For complete file imports, compare the whole parsed proposal with the uploaded
  source, including every rule and weight. Use a partial-update control.
  For import-file generation, grade the delivered file against the destination
  importer's row and field rules. Pair summarized formats with a full-history
  control so format-specific guidance does not discard required data.
  Preserve exact selectors and values when fidelity to the user's wording is
  under test. Define structured answer fields and counting units explicitly. Do not
  let an undefined priority label or field name decide the grader's meaning. Keep original traces when correcting a grader, apply the correction
  to both variants, and rerun affected comparisons before claiming an improvement.
- Drop link and token fields before saving or exporting a response from another
  service. Optimizer job links carry stream tokens signed with this service's
  credential.
- Expose Pi's default `read`, `bash`, `edit`, and `write` model tools over
  the disposable sandbox. Always offer the server-side `optimizer` lifecycle
  tool. Keep optimizer execution and credentials outside
  the sandbox. Match the browser's basic optimizer anonymization, retain the
  reverse ID map server-side, restore IDs before download, and pass retained
  workbooks into a dedicated sandbox result path, separate from user attachments.
  Use `read` for bounded text and image inspection, `edit` for unique
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
- When changing `ai/pi`, compare with the exact upstream Pi revision cited in
  the module header. Preserve model-facing wording and edge-case behavior, add
  focused regression tests, and document intentional differences beside the port.
- Diagnose partial replies with completion signals and character counts before
  changing retry behavior. Preserve finish reasons in evaluation reports. A reply
  ending mid-word does not prove a transport failure when the provider reports
  completion. Keep response content and credentials out of diagnostic logs.
- Retry provider timeouts with bounded exponential backoff. After visible text,
  omit the failed attempt from model context and retry the original request.
  Keep the partial output visible and label it as omitted from future context. Discard incomplete tool calls and release tools only after confirmed
  response completion. Keep output limits cumulative across attempts and use
  distinct errors for timeouts before and during streaming.

## Server Authentication
- `API_AUTH_TOKEN` is the optional legacy credential. Authentication is
  disabled only when neither legacy nor identified credentials are configured,
  which keeps local runs and older clients working.
- `API_AUTH_TOKENS` accepts a JSON object mapping IDs to keys. IDs are for
  administration and audit logs only. Clients continue to send only the key as
  a bearer token and must never receive the ID. Keep `legacy` reserved for
  `API_AUTH_TOKEN`.
- Identified keys attribute requests, they do not isolate them. Every key
  reaches every protected route and every job. Do not present them as tenants
  or add per-key ownership checks without a deliberate multi-tenancy design.
- `API_AUTH_REQUIRED` makes a token mandatory and is set in the deployment images,
  so a published backend fails to start rather than serving openly by accident.
  Leave it unset outside those images.
- `/optimize/{job_id}/events` accepts a signed, job-scoped, expiring URL token as
  well as the bearer header, because `EventSource` cannot set headers. Mint it
  into `links.events`; never put a bearer key itself in a URL, and never put a
  stable key-derived value such as a per-key selector there either, because it
  correlates every stream a key opens and never expires. Verify the token
  against each configured key instead. Its lifetime
  comes from `ServerSettings.stream_token_ttl_seconds`, which tracks the longest
  run the deployment allows.
- Keep `/info` and `/ready` public. Clients discover the requirement from
  `/info`, and deployment probes must not need credentials. Gate every other
  route with the bearer-auth dependency.
- The separately deployed AI service uses `AI_AUTH_TOKEN` or `AI_AUTH_TOKENS`
  when configured. Keep
  `/health`, `/ready`, and `/capabilities` public, advertise the effective bearer
  auth requirement through `/capabilities`, and gate every session route when a
  token is set. Native runs may omit auth. Docker Compose services set
  `AI_AUTH_REQUIRED=true`; opting out must be explicit in the env file and must
  leave `AI_AUTH_TOKEN` and `AI_AUTH_TOKENS` empty.
- `AI_AUTH_TOKENS` provides the same JSON static-key behavior for the AI
  service. Either legacy or identified keys satisfy required-auth startup.

## Sentry
- Initialize Sentry before configuration or logging in every first-party
  standalone service process. Use a distinct `app` tag and flush Sentry before
  short-lived processes exit.
- Report a client error only when it requires knowledge of the API contract that
  a scanner cannot have. Missing routes and unauthenticated probes stay
  unreported. Add new signals to `classify_suspicious_request`, and never let a
  signal change the response a caller sees.
- Record the resolved client address as a tag rather than overriding Sentry's
  own attribution.
  `tag_client_address` does this for every request. Compose treats its local
  service containers as trusted and tells Uvicorn to accept forwarded headers
  from them. NGINX must replace public `X-Forwarded-For` with Cloudflare's
  `CF-Connecting-IP`, so a caller cannot choose the API's client address.
- Count repeats in `server/suspicion.py`, keyed by signal and a salted address
  digest. Counting is advisory, so a storage failure must leave a report
  unescalated rather than drop it or change the response. Keep the salt private.
  The deployment ID is public and cannot serve as a salt by itself.

## Server Concurrency
- Synchronous routes and `run_in_threadpool` calls share one bounded thread
  pool per worker. Write a long-lived response, such as an SSE stream, as an
  async generator. Let it wait on the event loop and offload only short store
  reads. A synchronous generator holds a pool thread for its whole wait, so a
  few idle clients can stall every synchronous route.
  `test_idle_event_streams_do_not_hold_worker_threads` guards the job event
  stream.

## Input Limits
- Match middleware routes relative to the ASGI `root_path`. Test authentication
  and body limits at the application root and under a mounted URL prefix.
- For streamed multipart limits, raise `MultiPartException` so Starlette closes
  temporary files, then translate the rejection to HTTP 413. Check file closure
  as well as the response and consumed bytes.
- Bound submitted scheduling data by its alias expansion and nesting depth as
  well as its byte size. `loader.measure_yaml_expansion` measures both from the
  parse events without building the structure, and both the API and `load_data`
  refuse past either bound. Read untrusted data off the event loop.

## Testing
- Normal tests live under `tests/`.
- When replacing a browser cookie in a test, delete the existing cookie first
  or match its domain and path. Setting only its name can add a duplicate.
  HTTP client versions can send those duplicates in different orders.
- Derive a fixture timestamp from the current clock whenever the code under test
  compares it against real time, such as a Redis `EXPIREAT` or a retention
  window. A hardcoded date passes until that instant arrives and then fails for
  a reason the assertion does not name. `tests/test_usage_metrics.py` shifts its
  whole timeline onto the current reporting week for this reason.
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
  Read UTF-8 fixtures and generated reports with explicit `encoding="utf-8"`.
  Windows can use a legacy default encoding. Compare text-loaded references with UTF-8 text
  because text reads normalize checkout line endings. Use byte comparisons
  only when exact bytes are required.
- The `legacy_text_encoding` fixture in `tests/conftest.py` simulates legacy
  Windows decoding for implicit `Path.read_text` calls.
  `tests/test_ai_eval_grading.py` and `tests/test_ai_ladder_audit.py` use it.
  Run them locally after changing evaluation fixtures, reports, or grading
  tests, so encoding regressions fail before a push.
- Write hash-bound fixture inputs as exact encoded bytes to avoid platform
  newline translation. Keep optimizer source hashes tied to exact bytes.
  Hash helper evidence as UTF-8 text with normalized line endings. Check report
  creation, receipt creation, and receipt validation together. When changing
  text hashes or their fixtures, cover LF and CRLF inputs and check that changed
  content is rejected. Fix ZIP creator metadata as well as timestamps when
  generated archive bytes must match across platforms.
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
- Mark a file written entirely by an AI coding agent immediately after the license
  block, using `# This test is mostly AI generated.` for anything under `tests/`,
  including helpers and runners, and `# This file is mostly AI generated.` in any
  other new file. Editing a file someone else wrote does not earn a marker.
