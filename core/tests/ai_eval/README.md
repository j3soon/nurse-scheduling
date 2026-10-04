# AI evaluation case format

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

Store one JSON object per case under `cases/<dataset>/<category>/<id>.json`. Existing synthetic coverage lives under
`cases/basics/`, mirroring the normal YAML testcase layout under `tests/testcases/basics/`. Reserve sibling dataset
directories such as `cases/real/` for cases derived from real user scenarios. Every case names a fixture, one question or a
`user_turns` sequence, and whether one turn should propose a schedule change. Proposal cases default to the final
turn. Set the one-based `proposal_turn` when a later turn should discuss an earlier proposal without reproposing it.
Every other turn is explicitly graded as producing no proposal.

Use `attachments` to name deterministic binary fixtures built by `attachment_fixtures.py`. Attachments are sent only
with the first turn, matching the frontend request lifecycle. Attachment cases should assert the answer and the tools
that prove the sandbox inspected the file rather than relying on its declared media type.

Use ordered `proposal_turns` when revisions should produce more than one proposal. The last listed proposal is graded
by `expected_diff`. Use `turn_actions` to apply a trusted frontend `approve`, `reject`, or external `update` after a
turn. An update supplies a shallow top-level `schedule_patch` and invalidates any pending proposal.

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

Completed attempts are saved immediately to `results.jsonl` and `cases/`, with initial metadata and a
`progress.json` status. Comparison arms keep separate directories. Interrupted batches retain completed
attempts and are not complete comparisons. Final reports restore dataset order. Existing output directories
are rejected before model work starts.

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
context, such as the schedule pointer and download size limit, when building a request. Changing state, such as a
pending proposal, goes into a final status message. Case attachments enter history as an upload event before the first
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
Cases marked `optimizer_completion_only` seed a fixed successful start and acknowledgement without a provider call.
The seed remains in the grading trace but is excluded from model tool and token metrics.
`request-audit-stale-summary` supplies an earlier verified incumbent's counts with a different source hash
to check that the agent uses the current workbook instead.

From the repository root, run `./scripts/run_ai_eval.sh --prompt-compare-step 5` to compare the first four sections
against the first five using step 5's cases. `--case ID` overrides that default case set. A comparison defaults to
three repeats per case and accepts up to `--repeat 10` for deeper investigations. It uses four concurrent case jobs by default and
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
