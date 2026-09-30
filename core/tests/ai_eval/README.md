# AI evaluation case format

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

For a scalar, mapping, or whole-section replacement, use `before` and `after` instead of `removed` and `added`.
Use `null` for a missing path, such as an export section created from scratch.

Keep `assert` for outcomes that intentionally allow multiple valid objects or need invariants across a large cascade.
Examples include optional descriptions, case-insensitive natural-language values, and deleting one ID from many
history entries while preserving similarly named IDs. Use `{"path": "...", "unchanged": true}` when a value must
match the input fixture, so fixture copy edits do not stale a literal expectation. Use `answer_contains` for read-only and refusal cases,
`intermediate_answer_contains` for clarification turns, and `tool_usage` only when the trajectory itself is under test.

Every proposal case must also declare `changes`. It guards all schedule paths outside the listed scope. Diff checks
guard every addition and removal inside their selected collection.

Use `--repeat 3` for reliability checks on a tuning subset. Repetitions share the global `--jobs` limit and reports
show per-case pass rates plus median and p95 cost. Use `--baseline-report <report-dir>` to compare reliability, model
turns, and tokens with an earlier run. Reports record the model, Git revision, dirty diff hash, prompt, and fixture
hashes so comparisons do not silently mix configurations. Reference hashes cover every file hydrated into the sandbox,
including the user guide pages the app-UI cases are graded on. Case hashes cover each case's parsed criteria, including
untracked case files during local development.

Cases tagged `holdout` use schedules that differ from the primary tuning fixtures. Run them to check generalization,
but do not rewrite prompts to match one held-out trajectory. Promote a recurring failure pattern into a separate
tuning case before changing agent guidance.

The runner reports the full relative category, for example `basics/03-structure`. `--category` accepts that full name
or its trailing category name, so existing commands such as `--category 03-structure` remain valid. Use tags for
cross-cutting evaluation properties such as `holdout`, `tuning`, or `clarification`, not for dataset provenance.

## Prompt steps

`nurse_scheduling/ai/prompts/system-steps.json` orders the Markdown sections used by production and assigns each
one a stable ID, hypothesis, and targeted case set. The production and evaluation loaders use the same assembler.
Anchors and section hashes make the evaluation fail fast if prompt text changes without updating the manifest.
Keep section filenames stable and change their order in the manifest. Linked cases are candidates for evidence, not
proof that a section helps. A step's `evidence` records a successful adjacent comparison only after inspecting its
before and after reports. Empty evidence means that section has not yet shown a measured marginal benefit. A `gaps`
entry records untested claims or comparisons without a measured gain. A comparison with no targeted case requires an
explicit case selection.

The runner offers a controlled `optimizer` tool with the production tool definition. It acknowledges starts and
reports a running job without submitting to the real optimizer, so cases can grade whether the agent used the tool
and explained its background behavior. This does not validate solver output or completion callbacks.

From the repository root, run `./scripts/run_ai_eval.sh --prompt-compare-step 5` to compare the first four sections
against the first five using step 5's cases. `--case ID` overrides that default case set. A comparison defaults to
three repeats per case and accepts `--repeat 3` through `--repeat 5`. It uses four concurrent case jobs by default and
alternates the before/after queue order across repetitions. Both variants receive the same tools, fixtures, and
references. `--prompt-step 0 --case ID` runs without optional prompt text, while `--prompt-step N --case ID` runs a
single prefix. The application-generated schedule summary still appears in both variants.

The comparison writes separate `before/` and `after/` reports, including full trajectories and selected prompt-variant
hashes, plus `comparison.md`. It reports a benefit only when there are no infrastructure errors, every after attempt
passes, and either at least one before attempt fails or an explicit relative cost target is met with all attempts
passing. For example, append `--cost-metric tool-calls --cost-ratio 0.6` to require at most 60% of the baseline tool
calls. Available metrics are `tool-calls`, `turns`, `uncached-tokens`, and `seconds`. Cost ratios compare successful
attempts only. Treat three to five repetitions as directional evidence, not a precise reliability or latency estimate.

Run `--prompt-ablate-step N` only for a requested full-prompt removal check. It compares the complete prompt without
section N against the complete prompt. Ordinary step comparisons run only the cases named for that step, unless
additional `--case`, `--category`, `--tag`, `--tuning`, or `--full` scope is explicitly selected. Add a contrasting
exact-target or holdout case when a new section might cause over-clarification or another nearby regression.
