# AI evaluation case format

The runner chooses case concurrency at startup from LiteLLM deployment limits
and cached health. It sums `litellm_params.max_parallel_requests` for healthy
unique deployment IDs of the selected model. It caps jobs at 20, the E2B Hobby
sandbox limit, and the number of queued attempts. `--jobs N` requests a lower
limit. Repetitions and prompt variants share one semaphore. Ladder audits let
each cohort discover capacity independently.

The evaluator and admin check reuse `AI_PROVIDER_BASE_URL` and
`AI_PROVIDER_API_KEY` for model metadata and cached health. Model metadata is
relative to the API base, such as `/v1/model/info`. Cached health uses the same
origin at `/health/latest`, with the trailing `/v1` removed from the API base.
The public gateway currently blocks this health route. Without health, the
runner falls back to at most four jobs and respects smaller known
deployment limits. Qwen uses four jobs for one confirmed healthy backend and
eight for two. If all deployments are confirmed unhealthy, evaluation stops
before sandbox provisioning. Health records older than two hours are unknown.
LiteLLM persists unchanged probe results hourly. These limits describe capacity
per proxy worker and do not measure free slots or reserve them for the evaluation.

From the repository root, inspect the selected model without inference calls:

```sh
./scripts/check_litellm_concurrency.sh
AI_ENV_FILE=docker/.env.staging ./scripts/check_litellm_concurrency.sh --model unsloth/Qwen3.8-27B-NVFP4
```

The script loads `docker/.env`, or `docker/.env.staging` if the first file is
absent. An explicit `AI_ENV_FILE` must exist. It prints the selected file to
stderr and JSON to stdout, including each deployment's limit and health, total
configured capacity, the conservative provider limit, and the evaluation ceiling.
`--base-url URL` overrides the provider API base and retains the selected provider
key. The key is read from `AI_PROVIDER_API_KEY`, never a command argument. The
script returns 1 when metadata is unavailable or all deployments are unhealthy.
Reports save `concurrency.json` with the decision and include its reason in each
summary. Keep the chosen concurrency equal across performance comparisons.

Check prefix-cache reporting on demand, without provisioning a sandbox:

```bash
AI_ENV_FILE=docker/.env.staging ./scripts/check_ai_prompt_cache.sh --repeat 3 --output ../artifacts/prefix-cache-verification/results.json
```

The probe uses the app's assembled system prompt and tool definitions, requests
one output token, and repeats the shared prefix alongside unique-prefix timing
controls. Positive provider-reported `cached_tokens` confirms reuse. Exit 0 means
confirmed hits, 1 means reported zero hits or a request error, and 2 means cache
telemetry is missing. Timing alone does not prove caching. vLLM can expose usage
details with `--enable-prompt-tokens-details`, independently of
`--enable-prefix-caching`. Zero reported hits for a short prefix does not imply
caching is disabled. Hybrid models can need longer prefixes to reuse cache.
Append a reference for this diagnostic without changing the app prompt:

```bash
AI_ENV_FILE=docker/.env.staging ./scripts/check_ai_prompt_cache.sh --append-system-file ../docs/content/user-guide/build-a-real-schedule.md
AI_ENV_FILE=docker/.env.staging ./scripts/check_ai_prompt_cache.sh --benchmark --repeat 10 --append-system-file ../docs/content/user-guide/build-a-real-schedule.md --output ../artifacts/prefix-cache-verification/benchmark-guide.json
```

The vLLM benchmark forces misses with fresh `cache_salt` values and reuses one
warmed salt. Paired requests have identical prompt tokens and a 128-token output
limit. It alternates arm order and runs sequentially to avoid local contention.
Reports include request time, time to first token, token means and standard
deviations, and paired deltas. Warmup is excluded from pair costs. Unequal output
token counts are excluded and retained as unmatched pairs. This measures cache
reuse on one running server, rather than restarting with caching off and on.
Benchmark exit 0 means controls and pair token counts are verified, even if the
tested prefix has no warm hits. Exit 2 means incomplete evidence.

Missing cached-token details are recorded as `null` in evaluations, so uncached
token comparisons remain unavailable rather than inventing cache misses.

Use `frontend_timezone` to set the VM timezone. Put fixed reference instants in
the user question, as the `local-date-from-instant-*` cases do. The runner rejects
the historical `current_time` field because it no longer injects clock values.

Store one JSON object per case under `cases/<dataset>/<category>/<id>.json`. Existing synthetic coverage lives under
`cases/basics/`, mirroring the normal YAML testcase layout under `tests/testcases/basics/`. Reserve sibling dataset
directories such as `cases/real/` for cases derived from real user scenarios. Every case names a fixture, one question or a
`user_turns` sequence, and whether one turn should change the schedule. Like the app, the runner applies each
turn's validated change before the next turn. Proposal cases, which grade that change, default to the final
turn. Set the one-based `proposal_turn` when a later turn should discuss an earlier proposal without reproposing it.
Every other turn is explicitly graded as producing no proposal.

Use `attachments` to name deterministic binary fixtures built by `attachment_fixtures.py`. Attachments are sent only
with the first turn, matching the frontend request lifecycle. Attachment cases should assert the answer and the tools
that prove the sandbox inspected the file rather than relying on its declared media type.

Use ordered `proposal_turns` when revisions should produce more than one proposal. The last listed proposal is graded
by `expected_diff` against the fixture. Use `turn_actions` to apply a trusted external `update` after a turn. An
update supplies a shallow top-level `schedule_patch` and adds a schedule-change app event.

Use `expected_diff` for a deterministic mutation to a list-valued path. Each entry gives the complete semantic
multiset delta, so an unlisted addition or removal at that path fails:

```json
{
  "expected_diff": [
    {
      "path": "people.items",
      "removed": [{"id": "P1", "description": "", "history": ["OFF"]}],
      "added": [{"id": "P1", "description": "Lead", "history": ["OFF"]}]
    }
  ],
  "changes": ["people.items"]
}
```

Object key order and list position within the selected collection do not matter. Nested list order remains semantic,
which is required for values such as succession patterns. Include complete objects rather than partial patterns.
For a pure addition, `allow_added_description: true` accepts an optional label when the user did not request one.
This cannot hide changes to existing objects or a requested description. Exact staffing requirements without a
preferred target ignore their ineffective weight. Requirements, qualifications, and preferred-staffing penalties
remain semantic.

For a scalar, mapping, or whole-section replacement, use `before` and `after` instead of `removed` and `added`.
Use `null` for a missing path, such as an export section created from scratch.

Keep `assert` for outcomes that intentionally allow multiple valid objects or need invariants across a large cascade.
The loader rejects `assertions`, which would otherwise silently omit these checks.
Examples include optional descriptions, case-insensitive natural-language values, and deleting one ID from many
history entries while preserving similarly named IDs. Use `{"path": "...", "unchanged": true}` when a value must
match the input fixture, so fixture copy edits do not stale a literal expectation. Use `answer_contains` for read-only and refusal cases,
`intermediate_answer_contains` for clarification turns, and `tool_usage` only when the trajectory itself is under test.
Use `answer_json` to check required fields in the final JSON object, including nested objects. Additional object
fields are allowed. Scalar values and lists remain exact.
Use `turn_tool_usage` as an ordered list of tool criteria to grade individual user turns. A `null` entry skips a turn.
This distinguishes a forbidden premature edit from the edit required after clarification. `answer_matches` and
`answer_not_matches` accept case-insensitive regular expressions for focused answer contracts. Validate them against
correct paraphrases and known incorrect answers. They do not replace semantic schedule checks or prove every possible
answer wording is correct.
Use `optimizer_error` to simulate an optimizer API outage, and `tool_usage.required_errors` to require an observed
tool failure. This exercises the agent's response to a tool error without treating a controlled outage as a provider
or sandbox infrastructure failure.
The `schedule-recovery` cases use one uploaded script to save a valid description
change, then stage an unfinished rename, a truncated YAML write, or an optional
audit error in another tool call. They require the earlier accepted edit and
preserve unrelated schedule data. The restore case requires a successful read
of `/workspace/last-accepted-schedule.yaml`. The control runs the audit command
unchanged so its nonzero exit reaches the tool.

The final comparison uses the same prompt, fixture and provider in both versions,
with three repetitions and four concurrent jobs. Provider requests and E2B commands
are real. No optimizer job runs. Model: `unsloth/Qwen3.8-27B-NVFP4`. Template:
`nurse-scheduling-trace-validation`, with a 900-second test-only turn limit.

| Case | Automatic restoration | Separate draft and last accepted copy |
| --- | --- | --- |
| `schedule-recovery-partial-edit` | 3/3 | 3/3 |
| `schedule-recovery-restore-last-accepted` | 0/3 | 3/3 |
| `schedule-recovery-valid-edit-control` | 3/3 | 3/3 |

The original flow does not provide the accepted file. One baseline run ended
with an unresolved trusted-validation rejection. There were no provider or
sandbox infrastructure failures. All three candidate partial-edit runs kept the
unfinished group definition and edited only its remaining references. These
checks validate the explicit recovery workflows. Performance was not an acceptance
criterion. Earlier runs with a weaker restore check and an ambiguous control
command remain in local reports. The final comparisons use the corrected cases.

Use `provider_timeout_after_text` to inject one partial assistant answer followed by a stream timeout.
The production retry policy resends the original request to the live provider,
without the failed partial answer or an interruption instruction. The final answer
check grades only output from completed responses. Failed attempt text remains in
the trajectory as `omitted_response`.
Only that recovery request is live. The initial text and timeout are synthetic, so their timing does not measure
a real provider outage. The ordinary response control runs without this field.
Use `rejected_write_turn` to inject one malformed schedule write before a selected
user turn's first live model request. Zero disables it. The seed runs through the
production tool and trusted validator. The trace labels it `evaluation_fault`.
Provider timing and token telemetry exclude the synthetic response. Tool counts
include its write and validation. This tests recovery, not first-write reliability.
`workbook-build-rejected-write-recovery` retains the strict construction case's
source assertions and requires feedback that keeps the draft and names the recovery copy. It grades final recovery,
so it does not limit repeated validation feedback while the rejection is unresolved.
Keep strict cases at zero rejections. Do not replay customer commands as fixtures.
The retained-draft recovery case and `workbook-build-after-confirmation` control
both passed 3/3 with `unsloth/Qwen3.8-27B-NVFP4`, the isolated
`nurse-scheduling-trace-validation` E2B template, four jobs and a 900-second test-only
turn limit. No infrastructure errors occurred. Every proposal preserved the full
source assertions. One recovery run made an additional schema-invalid write before
repairing it. None read the last accepted copy. These results validate controlled
final recovery, not first-write reliability, backup use or provider-outage recovery.
This test-only change does not establish a production improvement or cost saving.
Deterministic checks also verify that the draft remains malformed and the recovery
copy keeps the starting schedule before the live provider responds.

The command-outcome fix also passes these two live cases 3/3 each with the same
model, template and settings. All recovery runs keep the rejection visible on
successful commands without marking those commands as failed. The traces include
reads, a shell command and scratch-file writes. One run needs two additional
rejected edits before the final valid proposal. No infrastructure failures occur.
The 15 command-status regression cases fail on the parent implementation and
pass with the fix. A separate control preserves genuine command failures.
Finalization and optimization remain blocked while the draft is invalid. These
checks validate command status and final recovery, not first-write reliability
or a performance gain.

Use `tool_usage.max_validation_errors` to bound failed trusted schedule checks. A valid final proposal does not erase
an invalid intermediate mutation. Unrelated tool errors are not schedule-validation repairs.

Every proposal case must also declare `changes`. It guards all schedule paths outside the listed scope. Diff checks
guard every addition and removal inside their selected collection.

An unexpected proposal or exceeded tool limit is an irreversible failure for that case. By default the runner records
it and stops, avoiding work that cannot restore a passing verdict. Missing required tools are not an early failure
because later calls may satisfy them. Use `--continue-after-failure` when the later trajectory is useful for diagnosis.
Successful cases always execute every user turn. Metadata records this setting and sandbox timeouts so differing
evaluation configurations remain visible.
A shell timeout returns a failed tool result after verified process-group cleanup. Working files remain
available and the agent may recover. If cleanup cannot be confirmed, the sandbox is terminated and
the evaluation ends as a behavioral failure with the original failed tool result retained. Execution
deadlines are separate from E2B connection timeouts. Commands are never replayed automatically.
Responses that exceed text, reasoning, tool-argument or tool-count limits are model behavior failures.
Their limit reason and partial trajectory remain recorded. Provider connection and other sandbox failures
remain infrastructure errors.

For a real-provider timeout recovery comparison, load the ignored local env file and run from `core/`:

```bash
set -a
source ../docker/.env.staging
set +a
python -m tests.ai_eval.timeout_recovery_benchmark --baseline-ref b1521bd^ --repeat 3 --jobs 4
```

This runs `tool-timeout-checkpoint-recovery` against the historical and current E2B adapters with identical
prompts and tools. Before teardown, an independent check verifies one sandbox, one hydration, preserved
checkpoint data, one diagnostic execution, and no delayed child write. Reports and historical adapter snapshots
stay under ignored `artifacts/`. The historical arm aborts, so its shorter run is not a cost saving.
The ordinary `run_ai_eval.sh --case tool-timeout-checkpoint-recovery` grades the schedule and tool error only.

Use `--repeat 3` for reliability checks on a tuning subset. Repetitions share the global `--jobs` limit and reports
show per-case pass rates plus median and p95 cost. Use `--baseline-report <report-dir>` to compare reliability, model
turns, and tokens with an earlier run. Reports record the model, Git revision, dirty diff hash, prompt, and fixture
hashes so comparisons do not silently mix configurations. Reference hashes cover every file hydrated into the sandbox,
including the user guide pages the app-UI cases are graded on. Case hashes cover each case's parsed criteria, including
untracked case files during local development.

Each result records `provider_responses` with completion-signal presence, finish
reason and emitted text/reasoning character counts per model request. A completed
response with no finish reason means the endpoint sent `[DONE]`. An incomplete
request remains `completed: false`. Counts include partial retry output, but contain
no response text. Use the saved prompts and events to compare model output with
retained history. A mid-word ending alone does not establish a transport error.

Completed attempts are saved immediately to `results.jsonl` and `cases/`, with initial metadata and a
`progress.json` status. Comparison arms keep separate directories. Interrupted batches retain completed
attempts and are not complete comparisons. Final reports restore dataset order. Existing output directories
are rejected before model work starts.

Extend a completed comparison from three to five attempts per case from the repository root:

```sh
AI_ENV_FILE=docker/.env.staging ./scripts/run_ai_eval.sh \
  --extend-report artifacts/ai-evals/three-runs \
  --prompt-compare-step 5 --repeat 5 \
  --output-dir artifacts/ai-evals/five-runs
```

Use the original prompt selector, such as `--prompt-step`, `--prompt-compare-step` or
`--prompt-ablate-step`. `--repeat` is the target total and defaults to five for an extension.
Only missing repetitions run, with one global concurrency limit selected for the new batch. Add `--case ID` to extend
only a noisy case. The new report keeps the other cases at their original repetition counts.
Single-prompt reports can also be extended. Omit the prompt selector when the original report
used the current production prompt.

The runner checks the saved cases, fixtures, attachments, prompt, references, provider model,
sandbox configuration and failure policy before provider work. Changed inputs require a new
comparison. Incomplete reports, duplicate repetitions and inconsistent trajectories are rejected.
The original report stays unchanged. The new report preserves old failures and missing usage,
records each extension's source and Git revision, and recomputes summaries and paired statistics
from all attempts. An extension retains the original cost target. Its wall time covers only
the new execution, while per-attempt timings include the saved attempts. Review the extended
comparison before updating prompt receipts.
Add `--plan-only` to verify fingerprints and print the missing attempts without provider calls
or creating the output directory.

Cases tagged `holdout` use schedules that differ from the primary tuning fixtures. Run them to check generalization,
but do not rewrite prompts to match one held-out trajectory. Promote a recurring failure pattern into a separate
tuning case before changing agent guidance.

The runner reports the full relative category, for example `basics/03-structure`. `--category` accepts that full name
or its trailing category name, so existing commands such as `--category 03-structure` remain valid. Use tags for
cross-cutting evaluation properties such as `holdout`, `tuning`, or `clarification`, not for dataset provenance.

## Prompt steps

`nurse_scheduling/ai/prompts/system-steps.json` orders the Markdown sections used by production and assigns each
one a stable ID, hypothesis, and targeted case set. The production and evaluation loaders use the same assembler.
Leading SPDX license blocks and AI provenance comments are excluded from model-facing text.
Run `python3 scripts/print_ai_system_prompt.py` from the repository root to print the assembled prompt to stdout.
The script uses the production assembler and needs only Python's standard library. The app appends request-specific
context, such as the schedule pointer and download size limit, when building a request. Changing state, such as the
current time, goes into a final status message. Case attachments enter history as an upload event before the first
question, as production uploads do.
Section hashes make the evaluation fail fast if prompt text changes without updating the manifest.
Keep section filenames stable and change their order in the manifest. Linked cases are candidates for evidence, not
proof that a section helps. A step's `evidence` records a clean repeated comparison only after inspecting its
before and after reports. CI requires at least one benefit witness for every shipped clause. It rejects stale clause
or testcase/fixture inputs, ties without a declared cost benefit, infrastructure errors, and failing controls.
Candidate comparisons remain runnable before evidence is available. Keep aggregate counts, the model, and an
input fingerprint tracked. Preserve full prompt contexts, run metadata, diagnostics, and old receipts in ignored
`artifacts/`. Use selected integration checks when an earlier clause could affect later policies.

The [evidence workflow](prompt-evidence.md) documents the repository/artifact boundary and reproducible commands. A passing linked case alone does not establish a section's benefit.

The runner offers a controlled `optimizer` tool with the production tool definition. Ordinary cases acknowledge
starts without submitting real jobs. Startup acknowledgements use the production formatter, including the source
hash and automatic completion notification. Cases with `optimizer_completion` also deliver the production-shaped completion
message and an exporter-generated workbook with verified fixed assignments. These test result interpretation and
completion delivery through the agent harness, rather than stochastic solve quality or the service job lifecycle.

For an on-demand check with unrestricted OR-Tools solves, run from `core/`:

```bash
set -a
source ../docker/.env.staging
set +a
python -m tests.ai_eval.provider_preflight
python -m tests.ai_eval.real_optimizer --repeat 3 --timeout 60 --output-dir /app/artifacts/real-optimizer-check
```

This runs the small policy fixture and the 87-person ward with four concurrent
case jobs. It solves the agent's submitted YAML through the production
`OptimizationRunner`, exports the actual workbook, and delivers its actual
completion metadata. It grades preservation of the input and the agent's reported
status, score, and unmet 11b request count. Passing these checks does not imply
every finite-weight preference was satisfied. Inspect the retained audits for
schedule quality. Timing separates the optimizer subprocess from agent and
sandbox work, with solver/model/export time reported separately. HTTP submission,
queue persistence, anonymization, and worker recovery are outside this check.
It is not part of ordinary prompt comparisons or CI.

`optimizer-start-preserves-ward` checks the submitted YAML retains every original
constraint and weight. `optimizer-edit-before-start` checks requested changes
reach that snapshot before startup, using the `optimizer-start-source` oracle.
Result sandboxes include a compiled request context and `/reference/tools/inspect_optimizer_result.py`.
Use its repeatable `--person` and `--date` filters to query assigned shifts by
exact person ID and ISO date. The reader separates export annotations from
assignments, verifies the completion source hash, and reports truncated output.
The same helpers are available in both arms of prompt comparisons. Their scripts, catalog, and context projector
are fingerprinted so changes cannot silently reuse a result-reading receipt.
Completions include bounded `request_audit` counts computed by the production reader.
When space permits, `policy` adds compiled staffing shortfalls and signed
succession-window counts, including history. Its scope excludes other preference
types. The reader also exposes these counts when the compiled context's source
and workbook hashes match. `result-policy-misses`, `result-policy-clean`, and
`result-policy-stale` check preferred targets, clean counts, and stale-audit fallback.
Score-bearing completions report `score_direction: maximize` and restrict score
comparisons to unchanged constraints and weights. `optimizer-score-same-model`
checks direction and `optimizer-score-changed-model` guards comparability.
`optimizer_follow_up_completions` adds at most two named completion fixtures after
`optimizer_completion`. Each is delivered only after another successful start,
with the new submitted source and a fresh workbook. No user message is inserted
between results. This checks autonomous retries rather than a user asking again.
The `optimization-loop-*` cases isolate initiative. Outcome cases accept an
unsolicited offer or a successful start with the correct source. Edit-only cases
check the offer, acceptance and refusal without requiring the offer to list every
loop step. `optimization-loop-authorized-retry` checks that explicit authorization
continues through a missed request and a fresh satisfactory result, with every
submitted source preserved. It does not require a particular report format.

The stronger `autonomous-optimize-updated-proposal` diagnostic requires an
immediate start. `autonomous-policy-review-retry` requires an automatic retry and
exact final policy counts. Keep these separate from initiative evidence. The
shorter guidance can offer further work rather than meet those automatic-only
contracts. Their graders remain unchanged.

The `result-explanation` cases distinguish a compatible missed request from a
same-day conflict. An unrestricted solve checks both fixtures independently.
The summary cases also check unsolicited causal claims, including a retry that
improves stronger requests while leaving a compatible request unmet. Their
lexical checks catch observed claims and permit negation or uncertainty. Review
explanations manually. Correct categories and counts do not prove accurate prose.

Cases marked `optimizer_completion_only` seed a fixed successful start and acknowledgement without a provider call.
The seed remains in the grading trace but is excluded from model tool and token metrics.
`after_optimizer_turns` adds user messages after completion in fresh workspaces with the retained workbook.
The `optimizer-download` check rejects redundant ZIP delivery or offers. An explicitly requested archive
must contain the original workbook bytes under `optimizer_download_file`.
The `qualified-staffing` check compares every possible daily assignment in a small fixture with
`staffing_contract.counts` and `staffing_contract.qualified`. It uses compiled selectors and the engine's
staffing expression, so different rule layouts can pass when their staffing and eligibility match.
`request-audit-stale-summary` supplies an earlier verified incumbent's counts with a different source hash
to check that the agent uses the current workbook instead.

From the repository root, run `./scripts/run_ai_eval.sh --prompt-compare-step 5` to compare the first four sections
against the first five using step 5's cases. `--case ID` overrides that default case set. A comparison defaults to
three repeats per case and accepts up to `--repeat 10` for deeper investigations. It discovers case concurrency at startup and
alternates the before/after queue order across repetitions. Both variants receive the same tools, fixtures, and
references. `--prompt-step 0 --case ID` runs without optional prompt text, while `--prompt-step N --case ID` runs a
single prefix. The application-generated schedule summary still appears in both variants.

The comparison writes separate `before/` and `after/` reports, including full trajectories and selected prompt-variant
hashes, plus `comparison.md`. It reports a benefit only when there are no infrastructure errors, every after attempt
passes, and either at least one before attempt fails or an explicit relative cost target is met with all attempts
passing. For example, append `--cost-metric tool-calls --cost-ratio 0.6` to require at most 60% of the baseline tool
calls. Available metrics are `tool-calls`, `turns`, `uncached-tokens`, `completion-tokens`, `total-tokens`, and `seconds`. Cost ratios compare successful
attempts only. Treat these small repeated samples as directional evidence, not a precise reliability or latency estimate.

Every comparison also reports all token categories, tool calls, reads, bash calls, turns, and elapsed seconds,
even without `--cost-metric`. It shows before/after means, sample standard deviations, and mean paired deltas
(after minus before) with their sample standard deviations. Pairs match by case ID and repetition, not arrival order.
Cost statistics use only pairs where both attempts pass without infrastructure errors. Token statistics additionally
require complete provider usage in both attempts. Reports show usable/matched pair counts and exclude missing data
instead of treating it as zero. With fewer than two pairs, standard deviation is unavailable. Reasoning tokens are
included in generated tokens. Total tokens must not count them twice.

`comparison.json` stores these statistics and reliability counts for scripts. `--baseline-report` includes the same
metrics in `summary.md` and `baseline-comparison.json`, marking unmatched repetitions explicitly. All attempts remain
in success and infrastructure counts. These descriptive metrics do not change the declared benefit gate. Keep all
metrics in artifacts, while user-facing summaries may show only meaningful changes.

For helper discovery, keep the same helper scripts in both arms and use `--cost-metric completion-tokens` to test
reduced generated parsing and reasoning. Use `--cost-metric total-tokens` for scoped inspection. Declare the ratio
before confirmation. Attachment receipts bind deterministic binary bytes and hydrated helpers, alongside the
case and clause. Correct equivalent custom readers remain valid, including readers needed for color-only data.

Run `--prompt-ablate-step N` only for a requested full-prompt removal check. It compares the complete prompt without
section N against the complete prompt. Ordinary step comparisons run only the cases named for that step, unless
additional `--case`, `--category`, `--tag`, `--tuning`, or `--full` scope is explicitly selected. Add a contrasting
exact-target or holdout case when a new section might cause over-clarification or another nearby regression.

## Optimizer inspector statistics

Use `inspect_optimizer_result.py --statistics --source-sha256 HASH` for observed
per-person shift counts and longest work/OFF runs. `--include-history` uses only
source YAML whose bytes match the completed run. These statistics do not audit
scheduling policies.

A repeated comparison checked the same calculations exposed through a separate
roster command versus this inspector mode. The prompt, case inputs and fixed
assignments were unchanged. The CLI and helper catalog changed together.
Both versions used `unsloth/Qwen3.8-27B-NVFP4`, real E2B commands, three repetitions
and four concurrent case jobs. Optimizer submission was simulated with verified
assignments exported as real XLSX files.

| Case | Separate command correctness | Inspector correctness | Separate command use | Inspector statistics use |
| --- | ---: | ---: | ---: | ---: |
| `result-roster-statistics` | 3/3 | 3/3 | 2/3 | 3/3 |
| `result-single-tier-summary` | 3/3 | 3/3 | 0/3 | 0/3 |

Neither version had infrastructure errors. Helper use counts runs that execute
the calculation, excluding source reads and `--help`. The single-tier control
correctly answered from completion metadata without an inspection call. Three
repetitions establish observed adoption, not a general reliability estimate. Twelve deterministic CLI comparisons also preserved
statistics, history-source checks, request audits and assignment queries.
This supports consolidation for maintainability. No efficiency gain is claimed.


Check helper adoption on saved before/after reports with the receipt tool:

```sh
python -m tests.ai_eval.receipt check-helper BEFORE AFTER \
  --case result-roster-statistics --helper inspect_optimizer_result.py \
  --flag=--statistics --cost-metric completion-tokens --cost-ratio 0.9 \
  --output helper-comparison.json
```

Declare the cost target before running the comparison. The command exits nonzero
unless all candidate runs pass, every selected case executes the helper with the
required flags, and a selected helper-use case has a correctness gain or the declared cost benefit.
All report cases remain correctness controls. With a cost target, missing usage
or a cost increase in any passing control also fails the gate. Reports retain
all token categories, tool calls, reads, turns, timing and paired variation.

Execution checks recognize one direct Python command with structured JSON output.
Source reads, `--help`, quoted command text and failed calls do not count.
Compound commands, pipelines, redirections and substitutions also do not count,
because their exit status and output cannot be attributed to the helper.
These forms and calls through inline Python or another wrapper need separate trajectory review.
The target flags must occur on the helper invocation, not elsewhere in the call.
Keep automatic counts separate from manually verified execution in historical receipts.
Rejecting a compound command means its execution is unverified by this check.
Keep answer grading independent so correct alternative methods remain valid.

The roster consolidation comparison passes the helper-use gate. It has no
correctness gain or declared cost target, so it does not pass the benefit gate.
It supports the tested capability and consolidation, not an efficiency claim.


For a prompt comparison, `receipt write` also accepts `--helper NAME`, repeated
`--flag=--OPTION` and `--helper-case CASE` options. It checks the saved trajectories
before storing helper-use counts with the existing benefit receipt. The prompt
evidence validator requires all candidate runs to use the helper and binds those
counts to the measured helper bytes. This adds an adoption condition without
replacing the receipt's correctness or declared cost requirement.


The bundled `inspect_xlsx.py --comments` reads stored legacy comment text, including
blank cells. Use `--range` to select at most 10,000 cells. It returns at most 100
comments per sheet and 2000 characters per comment, with separate truncation flags.
`comment_part` identifies the source XML part or is null when no legacy comment
part exists. `threaded_comment_part` reports unsupported threaded comments anywhere
on the sheet without reading their text. The reader streams legacy comment XML
and does not traverse worksheet cells.
The cell modes keep their existing streaming behavior.
The fresh comment comparison passes 3/3 per case and arm. Its receipt requires
both `--comments` and `--range` on every candidate run. Generated tokens fall
48.7% for extraction and 52.5% for the empty control. Empty-control candidates
still write verification scripts. See [helper evidence](helper-evidence.md).

## Taiwan calendar generator adoption

The renewal policy generates holiday groups with
`build_taiwan_holiday_groups.py --start START --end END`. The TypeScript table
remains the generator's input, without a direct-read instruction in this policy.
A fresh comparison used the original policy and this wording, with the same
helper, fixtures, model and full production prompt otherwise unchanged.
Both versions used `unsloth/Qwen3.8-27B-NVFP4`, real E2B commands, three repetitions
and four concurrent jobs. No optimizer jobs ran.

| Case | Correct before / after | Generator use before / after | TypeScript reads before / after |
| --- | ---: | ---: | ---: |
| `dates-range-renew-small` | 3/3 / 3/3 | 1/3 / 3/3 | 3/3 / 0/3 |
| `dates-range-renew-custom-group-small` | 3/3 / 3/3 | 0/3 / 3/3 | 3/3 / 1/3 |
| `dates-range-renew-makeup` | 3/3 / 3/3 | 0/3 / 3/3 | 3/3 / 1/3 |

Use counts require successful calculation with both range flags. Source reads
and `--help` do not count. Custom-group scope and the makeup workday remained
correct. Some runs still read the source table after using the generator.

Generated tokens, mean ± sample standard deviation, with three matched pairs:

| Case | Before | After | Paired change ± SD |
| --- | ---: | ---: | ---: |
| Ordinary renewal | 5547 ± 2040 | 3825 ± 835 | -1722 ± 1733 |
| Custom-group renewal | 5685 ± 271 | 5279 ± 2211 | -406 ± 2380 |
| Makeup-workday renewal | 6244 ± 1098 | 4510 ± 897 | -1734 ± 202 |

These are descriptive measurements. No cost target was declared, so the
original-versus-revised comparison passes adoption but not the benefit gate.

A separate full-prompt ablation removed the complete revised renewal policy.
The four candidate cases each passed 3/3, including explanation-before-edit and
custom-group controls. Both renewal controls executed the generator with both
range flags in 3/3 runs. The saved prompt receipt enforces this adoption condition
and binds it to the helper bytes. Its correctness benefit validates the complete
policy, not the independent effect of selecting the generator. Neither comparison
had infrastructure errors.

A conservative recheck recognizes all three ordinary-renewal candidates and one
custom-group candidate automatically. Manual review confirms the other two
custom-group invocations and their calendar JSON. One redirects stderr, and the
other runs `--help` before the calculation with `&&`. The historical 3/3 count
includes this manual verification. These reports need manual review under the
stricter execution check and do not pass its automatic adoption gate.

Receipt creation rejects a failed or missing overall benefit decision. New
receipts keep measured control cost ratios, and validation rejects a control
cost regression. A favorable witness does not override the comparison result.
