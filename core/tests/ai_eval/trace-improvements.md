<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This test is mostly AI generated. -->

# Agent behavior comparisons

These selected comparisons start with three repetitions per version and four
concurrent case jobs. Noisy cases extend to five. Detailed trajectories, input
hashes, reliability, timing, and token statistics remain in ignored artifacts.
Results describe the named cases and model.

The referenced HTML exports were unavailable in this checkout. These cases
are synthetic reproductions of the reported behavior.

| Change | Testcase | Before | After | Control before/after |
| --- | --- | --- | --- | --- |
| Public example availability | `bundled-ward-example-inspection` | 0/3 | 3/3 | `bundled-example-current-schedule-control`: 3/3, 3/3 |
| Frontend timezone and server time | `current-time-frontend-taipei`, `current-time-frontend-los-angeles` | 0/5 each | 5/5 each | `explicit-date-frontend-time-control`: 3/3, 3/3 |
| Existing optimizer download | `optimizer-result-already-downloadable` | 0/3 | 5/5 | Final explicit ZIP and generated-file controls: 5/5 each |
| Inclusive senior staffing | `senior-included-in-day-total` | 2/3, then 5/5 | 5/5 | `senior-additional-day-slot`: 5/5, 5/5 |
| Day group membership | `day-group-creation` | 1/5 | 5/5 | `day-group-adds-only-day-shifts`, `day-group-explicit-broadening-control`: 3/3 before, 5/5 after each |

The example comparison used the same production prompt and current-schedule
fixture. The candidate adds sandbox hydration and advertises the reference path
in the core schema. The delivered example matches the public YAML bytes. Both API
images include the example source. The comparison had no infrastructure failures.
Model: `unsloth/Qwen3.8-27B-NVFP4`.

The clock comparison keeps the production prompt unchanged. The evaluation
freezes one server instant and supplies different frontend timezones. Current
clock questions require the matching local date, time, timezone, and next month.
The control uses the user's hypothetical instant instead of the current time.
The grader rejects VM clock reads and permits calculations from supplied dates.
There were no infrastructure failures. An additional clock instruction passed
but showed no benefit over the same data-only context, so it was not retained.
The browser sends its timezone on creation and messages. Session recovery
retains it, and each provider request refreshes the timestamp.

The download comparison first keeps the prompt unchanged and adds the known
**Download result** button to completion and later-turn status. The main case
improves from 0/3 to 2/3. A separate prompt comparison keeps these host facts in
both versions and adds the existing-download rule. It improves from 4/5 to 5/5.
The explicit archive and generated-file controls both remain 5/5. All attempts
had no infrastructure failures. Archives contain the original workbook bytes.
The completion workbook comes from solver-checked fixed assignments and the real
exporter. This comparison tests agent delivery decisions, not the optimizer job
service or stochastic solve quality. These small samples do not establish a
general success rate or performance gain.

The corrected inclusive case catches one run that sets two general day slots
plus one senior day slot, despite a total of two. The qualified-slot instruction
now explicitly subtracts included slots from that total. The control requests
two general slots plus one additional senior, for a total of three.
The first corrected baseline passes 2/3. A later five-run baseline passes 5/5,
and the candidate passes 5/5. This is an intermittent error, and the longer
comparison ties. It does not establish a general success-rate or cost gain.
The existing qualified-slot explanation witness checks numeric staffing composition.
It accepts a senior-only night shift named either `N` or `N+`.
This corrected control passes 3/3 in both versions.
The new grader compares all daily assignments admitted by compiled staffing
rules with an independent count and eligibility contract. Correct reference
assignments also pass a real local solver check. This protects the reported
interpretation without claiming that the unavailable historical chat was replayed.
There were no infrastructure failures.

Earlier staffing reports used an ignored `assertions` key for structural checks.
The staffing semantics were checked, but the extra inventory and date checks
were missing. Both versions were rerun with the supported `assert` records.
The loader now rejects the mistaken key, and the original reports are retained
as diagnostics rather than evidence for the corrected cases.

Earlier explanation-control reports rejected valid `N` naming or matched a
correct warning that one unrestricted shift cannot guarantee a senior mix.
Independent tests accept both valid names and that warning. They reject wrong
counts and claims that the app cannot represent senior staffing. Corrected
comparisons use the same final control in both versions.

The final group comparison keeps the staffing prompt, cases, fixtures, and grader
unchanged. Only the group rules in the core schema reference differ. Four of
five baseline proposals include evening shift `E` in `Day`, despite the stated
day/evening distinction. All five candidates include only day shift `D`.
The day-slot addition and explicitly requested broad-membership controls pass
all runs. There were no infrastructure failures.

Group membership is supplied by the YAML. The compiler does not automatically
put evening or night shifts in `Day`. The new guidance prevents the model from
proposing that interpretation without a user request. The independent fixture
check confirms that `Day` selects only `D` while reserved `ALL` still selects
every shift. Correct reference proposals pass frontend validation and the
grader. Known wrong proposals fail even when their explanations sound correct.
Only one creation pair passes in both versions, so its cost variation is
unavailable and no performance gain is claimed.

With the final group guidance, both the inclusive and explicitly additional
senior staffing cases also pass a three-run interaction check.

## Testcase field validation

The loader previously accepted unknown top-level fields. A synthetic
`answer_jsno` field silently removed the intended answer check. The loader now
rejects every unknown field before provider calls, while allowing the existing
license and provenance fields. Negative tests cover answer, semantic, tool, and
diff typos. The complete dataset still loads. This is a deterministic parser
comparison and does not require a provider evaluation.

## ZIP commands in the sandbox

The shared cloud template failed a synthetic archive check with
`zip: command not found` and exit code 127. The Dockerfile now installs `zip`
and `unzip`. An isolated rebuilt template passes ZIP creation, extraction,
archive-member byte checks, and the existing YAML/backend smoke check.
The tested template ID is `xbfavdutcvbe69ug6rl6`. The shared alias was not
rebuilt for this experiment. AI server startup rebuilds its configured alias
from the tracked Dockerfile.

With the complete prompt, cases, fixtures, and reference hashes unchanged,
`download-generated-zip`, `optimizer-result-explicit-zip`, and
`optimizer-result-already-downloadable` each pass 3/3 before and after.
The live model is `unsloth/Qwen3.8-27B-NVFP4`, with four concurrent jobs.
There are no infrastructure failures. Missing-ZIP command failures fall from
two to zero. The archive cases check actual delivered bytes. The existing
workbook control checks a follow-up in a fresh workspace without another ZIP.
Optimizer workbooks use solver-checked fixed assignments and the production
exporter and completion formatter, not the HTTP job queue.

This repairs a missing tool. It does not establish a model cost improvement.
Mean CSV-case tool calls increase from 1.33 to 2.00, while explicit-workbook
archive calls remain 1.67 in both versions. Python archive creation remains
an equally valid approach. Complete paired timing and token statistics remain
in the ignored comparison reports.

## Further staffing and guide experiments

Two new cases, `staffing-explanation-included-in-day-total` and
`staffing-explanation-additional-day-slot`, grade compiled staffing requirements and
explicit answer counts separately. The final JSON fields specify integer
units for day assignments, senior day assignments, all working assignments,
people OFF, and eligible seniors. Independent correct proposals and wrong
answer counts test the grader before provider calls. These checks do not
analyze every sentence of free-form prose.

The focused-guide candidate changes only the initial reading paragraph of
`new-schedule-guide`. It keeps all references available and uses the same code
and tools. The declared gate requires correct controls and a combined
matched-passing total-token ratio of at most 0.80. After correcting ambiguous
JSON field descriptions in both versions, inclusive staffing falls from 2/3
to 1/3. One failure has correct YAML but reports five working slots instead of
four. The setup and qualified-staffing controls pass 3/3. The ward prototype
also exposes a method-specific grader that rejects a valid Bash inspection.
The prompt candidate fails the correctness gate and is reverted. Its prototype
ward case and complete diagnostic reports remain in ignored artifacts.

A separate code experiment keeps the production prompt unchanged and adds
computed exact staffing counts to trusted validation feedback after an edit.
It uses compiled selectors and eligibility. It omits totals for overlapping,
incomplete, preferred-range, or weighted requirements and bounds its output.
Deterministic tests verify the calculation and model-facing delivery. All
232 focused checks and the affected PostgreSQL suite pass for the candidate.

Three live runs initially improve inclusive staffing from 2/3 to 3/3. A
matched two-run extension produces a five-run tie: inclusive staffing passes
4/5 before and after, and the additional-slot control passes 5/5 in both.
There are no infrastructure failures. The remaining failure misinterprets the
requested total, although its explanation matches the wrong proposal. The
candidate shows no repeated correctness or cost gain and is reverted. The
new staffing regression cases remain. Original attempts and complete paired
statistics, including token categories, tool calls, turns, timing, and sample
standard deviations, remain in the ignored reports.

More original chat exports would help distinguish incorrect interpretation
from incorrect prose about a correct proposal. Include the starting YAML,
attachments, final proposal, and the expected staffing counts. A useful runner
follow-up is to record the exact E2B template and build ID in evaluation
metadata so environment comparisons need no manual identity record.
