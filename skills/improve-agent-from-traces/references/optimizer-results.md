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
quality requirements in advance, such as staffing shortfalls and unmet strong
requests. Keep solver/model/export time separate from agent and sandbox time.
For automatic completion messages, preserve the production message role,
format, and workbook. Uploading a workbook alone does not test that delivery.

See the [evaluation guide](../../../core/tests/ai_eval/README.md) for fixed-result
tests and the on-demand real-optimizer check.
