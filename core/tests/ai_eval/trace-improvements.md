<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This test is mostly AI generated. -->

# Agent behavior comparisons

These selected comparisons start with three repetitions per version and four
concurrent case jobs. Noisy cases extend to five. Detailed trajectories, input
hashes, reliability, timing, and token
statistics remain in ignored artifacts. Results describe the named cases and model.

| Change | Testcase | Before | After | Control before/after |
| --- | --- | --- | --- | --- |
| Public example availability | `bundled-ward-example-inspection` | 0/3 | 3/3 | `bundled-example-current-schedule-control`: 3/3, 3/3 |
| Frontend timezone and server time | `current-time-frontend-taipei`, `current-time-frontend-los-angeles` | 0/5 each | 5/5 each | `explicit-date-frontend-time-control`: 3/3, 3/3 |
| Existing optimizer download | `optimizer-result-already-downloadable` | 0/3 | 5/5 | Final explicit ZIP and generated-file controls: 5/5 each |
| Inclusive senior staffing | `senior-included-in-day-total` | 2/3, then 5/5 | 5/5 | `senior-additional-day-slot`: 5/5, 5/5 |

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
