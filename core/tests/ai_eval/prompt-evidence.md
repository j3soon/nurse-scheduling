<!--
This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
Copyright (C) 2023-2026 Johnson Sun
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

# System prompt evidence

The [ordered manifest](../../nurse_scheduling/ai/prompts/system-steps.json) maps each production clause to its
behavioral hypothesis, witness testcase, and contrasting controls. It keeps one reviewed aggregate receipt per
clause: model, paired pass counts, infrastructure-error count, and an input fingerprint. Counts are directional
evidence for the named model and cases, not proof that a clause is universally necessary.

## Causal explanation checks

A fresh check after restoring YAML parser guidance reproduces four false passes
in the parent checks. The revised grading suite passes 455 tests. Two independent
solver checks confirm that the compatible fixture can satisfy every request and
that the contrasting fixture has a genuine conflict.

The unchanged production agent passes 9/9 automatically, but manual review
accepts only 2/3 summaries, 0/3 retry explanations and 3/3 verified-conflict
controls. It still invents priority tradeoffs for compatible requests. The
sentence-wide uncertainty filter can treat the month May as a modal verb, and
paraphrases can escape the patterns. These are known limitations of the
conservative language check. Do not treat its pass rate as validated explanation
quality or extend it with one pattern for each observed sentence. Keep manual
review of causal claims. No production prompt or cost improvement is claimed.

The summary and retry cases now reject claims that an unmet request was caused by
higher-weight requests taking precedence. Negation, uncertainty and general
statements about the weighted objective remain allowed. This is a grader change,
not an agent behavior improvement.

Earlier manual review of the production prompt found a false pass containing
an unsupported cause, incorrect counts and a reversed hard prohibition. A fresh
comparison with the corrected cases passes 2/3 summaries, 3/3 retries and 3/3
verified-conflict controls. All runs use the real provider and E2B sandbox with
verified result fixtures, three repetitions and four jobs. No HTTP optimizer jobs
run. Two focused conflict-wording candidates pass 6/9 and 8/9 versus 8/9 baseline.
Both are rejected. A separate audit-scope description experiment passes 9/9
automatically but only 8/9 on manual review: one answer acknowledges uncertainty
then still asserts that higher weights caused the miss. It is also rejected.
No infrastructure errors occur in these completed batches.

These historical comparisons included the now-removed evidence-strength step.
Their pass rates describe that prompt. Unsupported causal explanations remain
unresolved. Manual
review is still needed for facts and causal language beyond the conservative
patterns. No cost or reliability improvement is claimed.

## Historical retry continuation guidance

Commit `f909cf9b` added `provider-timeout-continuation` for the earlier policy that
sent partial answers and an interruption event to the model. Its named witness,
`provider-text-timeout-continuation`, improved from 0/3 to 3/3 on
`unsloth/Qwen3.8-27B-NVFP4`. The uninterrupted control passed 2/3 before and 3/3
after. No infrastructure errors occurred. These counts describe the old policy.

Retries now resend the original request and omit failed output. The continuation
instruction no longer applies and is removed. The named witness now grades one
complete answer from the successful attempt. The witness and uninterrupted
control both pass a live smoke check before and after removal. This confirms the
new request behavior without claiming a reliability or performance improvement.

## Repository and artifact boundary

Keep prompt text, testcase definitions, hypotheses, concise scope notes, and the latest aggregate receipts tracked.
Keep exact prompt snapshots, reference and environment hashes, timing, tokens, trajectories, diagnostic failures,
old receipts, and round-by-round analysis under ignored repository-root `artifacts/`. Commit messages should name
the motivating testcase and briefly state the behavior change. Do not grow this page into a run journal.

CI checks that every shipped clause has a clean benefit witness. The receipt's `input_sha256` binds its clause,
parsed testcase, and fixture. Editing any of these invalidates the receipt. Helper fingerprints cover relevant scripts, their imports and catalog entries. Full hydration hashes stay in run metadata, so adding an unrelated helper does not invalidate a receipt. Controls have their own paired counts,
so a targeted deeper investigation can extend one witness without rerunning already verified controls.
CI validates reviewed receipts locally. It does not call the provider or require ignored artifacts to exist.
Receipts describe their tested context, not a fresh evaluation of every later prompt composition.
Bind the JSON answer comparator for every answer shape, including scalar values.
`oracle_sha256` hashes each grader with every grading helper that its source names, transitively,
so a helper change also invalidates the receipts it can affect.
For a fingerprint-only correction, verify each existing receipt with the previous calculation before
refreshing its dependency hash. Preserve its measurements and label the correction separately from model runs.
If a previously untracked grader changed earlier, audit that change separately. Regrade its historical outputs,
or replace missing evidence with a clearly labeled fresh comparison.

## Reproduce a comparison

From the repository root with credentials in ignored `docker/.env` or `docker/.env.staging`:

```bash
./scripts/run_ai_eval.sh --prompt-compare-step N --repeat 3 --jobs 4
./scripts/run_ai_eval.sh --prompt-compare-step N --case CASE_ID --repeat 10 --jobs 4
```

Use three repeats routinely. Up to ten are available for an explicitly requested deeper investigation. Compare only
that clause's cases by default. Use full-prompt ablation when requested or when investigating an interaction.
Exact historical contexts are preserved in the ignored reports.

To audit every section and then all linked cases with the complete production prompt:

```bash
AI_ENV_FILE=docker/.env.staging ./scripts/run_ai_eval.sh --ladder-audit --plan-only
AI_ENV_FILE=docker/.env.staging ./scripts/run_ai_eval.sh --ladder-audit
```

The audit defaults to three repetitions and four concurrent case jobs. Cohorts run sequentially.
It uses each section's declared `comparison_mode` and predeclared cost target. The final pass includes
only linked ladder cases, not the entire evaluation inventory. Plan, logs, metrics, and partial results
stay in ignored `artifacts/`. Inputs are fingerprinted before execution and checked between cohorts.
Changing an input or losing a report stops the audit. Behavioral failures, infrastructure failures,
and missed benefit gates are reported separately. Retries are separate runs, never replacements.

Inspect the raw trajectories before replacing a receipt. Require all after attempts to pass, no infrastructure
errors, and either a correctness gain or a predeclared relative cost gain with both arms passing. Retain behavioral
failures. Infrastructure-invalid pairs may be rerun only with the original failures preserved in artifacts.

The evaluation stops when a section's text no longer matches its ledger hash. After editing a section, record its
new hash so that its comparison can run. After reviewing the report, write the witness receipt from it. The `write`
command checks that the report measured the current prompt, testcases, and fixtures. It lists the report's other
cases as controls and replaces the step's earlier receipt for the same witness. CI then checks the receipt.

```bash
cd core
python -m tests.ai_eval.receipt hash STEP_ID
python -m tests.ai_eval.receipt write ../artifacts/REPORT_DIR --case CASE_ID --note "Concise scope note."
```

For a stronger witness, freeze the case and grading before comparing, then confirm a promising gain in an
independent batch with unchanged inputs. Difficulty alone is not evidence. Keep passing ties as controls,
and do not require a guide read as a substitute for correct app behavior. Correct grader mistakes in both
arms and preserve the original results. For a grading-only change, first regrade saved outputs from both arms
with matching testcase and fixture fingerprints. Refresh grading fingerprints and record that regrading used
saved outputs. Keep historical counts and costs only when every affected check retains its result. Rerun the
affected provider comparison when model inputs changed or saved outputs and matching fingerprints are unavailable.

Keep behavioral regression cases when removing redundant guidance. They need not remain in the active
clause-evidence manifest. Identify clauses by their stable IDs when reviewing results, since removing a
section changes the numeric step selectors used by historical commands.

The literal-expression witness measures avoiding validation repairs, not eventual YAML correctness. The startup
witness holds optimizer-error guidance fixed in both arms. Optimizer startup cases use a controlled tool. Completion
cases replay verified assignments through the exporter and production message shape, without testing stochastic
solve quality or the service job lifecycle. Those durable limits remain beside their receipts in the manifest.

## Confirm inferred rules from a completed schedule

The `completed-schedule-inference` step asks the agent to suggest candidate rules
from an XLSX completed schedule, explain the observations, and confirm the rules
before building YAML. User corrections take precedence. A question about what
is established still leaves unstated rules unknown. The recorded paired
comparison held an additional evidence-strength step fixed. That step is no
longer retained. Its token measurements describe the historical prompt.

Historical measurements use the integrated branch. Adjacent prefixes 35/36 use the
same model, helpers and workbook. Each case has
three repetitions with four concurrent jobs and no infrastructure failures.

| Case | Without the added step | With the added step |
| --- | --- | --- |
| completed-schedule-onboarding | 3/3 | 3/3 |
| completed-roster-unknown-policy | 3/3 | 3/3 |
| completed-roster-confirmed-policy | 3/3 | 3/3 |

The baseline already suggests rules. This amendment makes that expectation
explicit. On the fact-only witness, generated tokens decrease from a mean of
1,647 to 1,001, or 39.2%, meeting the declared 15% target. Sample standard
deviations are 777 and 396 tokens. Full local reports retain all token categories,
matched-pair variation, tool counts and timing. These small samples do not prove
a general performance improvement.

Separate full-prompt checks cover structured suggestions and the user's later
correction to a five-day work limit and unrestricted D/E/N eligibility. The
saved proposals are checked with the frontend validator and the source grader.
The construction case no longer requires a literal question mark in the first
confirmation request. Both versions' saved answers are regraded with that same
correction. This changes no model input or final-source requirement. Regraded
correctness is separate from the original timing and token measurements. Structured suggestions
pass 3/3 in both full-prompt versions. Corrected-rule construction passes 3/3 in
each version after regrading, and all six saved YAML proposals independently
pass the frontend validator.

These checks validate suggestions, confirmation and use of corrected rules.
They do not establish general workbook arithmetic accuracy. Replies still contain
counting errors, which remain a separate follow-up. Earlier wording candidates
and test-format errors remain in local reports. Model calls and E2B commands are real.
No optimizer jobs run in the onboarding checks.

A separate check without evidence-strength passes 3/3 each for natural onboarding,
fact-only policy, explicit policy and corrected-rule construction. Structured
inference passes 2/3. One response omits a comma in JSON. These runs use the
same inference prompt and make no token or timing improvement claim.
