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
