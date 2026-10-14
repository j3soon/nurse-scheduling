<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- SPDX-FileCopyrightText: 2026 Johnson Sun -->
<!-- This file is mostly AI generated. -->

# Optimizer results and roster quality

Use fixed assignments checked by the solver and exported as real workbooks when
testing result interpretation. These isolate agent behavior from solver
variation. They do not prove that the optimizer can find a good roster. For that
claim, solve the submitted YAML without forcing an assignment and retain its
actual status, score, workbook, and preference counts. A local engine check
does not test the HTTP job service, queue, or worker recovery. Use the existing
real-optimizer check when that level of validation is requested.

Grade input preservation, truthful result interpretation, and schedule quality
separately. A feasible roster can still miss finite-weight preferences. Define
quality requirements in advance, such as staffing shortfalls and unmet requests
at an exact numeric weight. Define JSON counting units and which finite-weight
preferences must be satisfied for handoff. Do not let a vague term such as
"usable" make that choice for the grader. Keep solver/model/export time separate
from agent and sandbox time.
For automatic completion messages, preserve the production message role,
format, and workbook. Uploading a workbook alone does not test that delivery.

Correct counts do not prove a causal explanation. Contrast compatible missed
preferences with requests that cannot both hold. Verify those facts against the
source rules. Preserve multiple results when the error follows a retry, and
review explanations as well as structured answer fields.

See the [evaluation guide](../../../core/tests/ai_eval/README.md) for fixed-result
tests and the on-demand real-optimizer check.

For autonomous retries, deliver a completion sequence with no user message
between results. Require a new successful submission before each completion,
then check its source, distinct artifact and final quality counts. Grade a
truthful running update without requiring incidental words in that update.
Check that explicit draft and read-only requests still stop without optimizing.

For initiative guidance, grade whether the agent offers or starts the loop,
according to the user's intended behavior. Check submissions and source
preservation independently of its explanation. An offer need not list every
loop step. Keep policy counts and report formats in separate result-review
cases. When the user changes the intended behavior, retain stronger existing
cases as diagnostics and report the tradeoff.
