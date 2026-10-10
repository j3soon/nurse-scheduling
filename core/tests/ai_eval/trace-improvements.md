<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This test is mostly AI generated. -->

# Agent behavior comparisons

These selected comparisons use three repetitions per version and four concurrent
case jobs. Detailed trajectories, input hashes, reliability, timing, and token
statistics remain in ignored artifacts. Results describe the named cases and model.

| Change | Testcase | Before | After | Control before/after |
| --- | --- | --- | --- | --- |
| Public example availability | `bundled-ward-example-inspection` | 0/3 | 3/3 | `bundled-example-current-schedule-control`: 3/3, 3/3 |
| Frontend timezone and server time | `current-time-frontend-taipei`, `current-time-frontend-los-angeles` | 0/5 each | 5/5 each | `explicit-date-frontend-time-control`: 3/3, 3/3 |
| Existing optimizer download | `optimizer-result-already-downloadable` | 0/3 | 5/5 | Final explicit ZIP and generated-file controls: 5/5 each |

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
