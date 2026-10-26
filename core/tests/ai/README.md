<!--
This file is part of Nurse Scheduling Project.
SPDX-License-Identifier: AGPL-3.0-or-later
-->
<!-- This file is mostly AI generated. -->

# Human-reviewed AI testcases

`testcases/` contains manually authored AI regression conversations. A human
must review each case before merging it. An AI generation marker records file
provenance, not review status. These tests are independent of `ai_eval` and
`ai_fixtures` and use production provider and workspace APIs.

From `core/`, validate all definitions without AI credentials:

```sh
python -m tests.ai.runner validate
pytest -q tests/test_ai_testcases.py
```

Run all cases, or select files or directories:

```sh
python -m tests.ai.runner run
python -m tests.ai.runner run tests/ai/testcases/basics
```

For local live runs, export the existing settings from repository-root
`docker/.env`, or `docker/.env.staging` if `.env` does not exist. From the
repository root:

```sh
set -a
source docker/.env.staging  # Use docker/.env when present.
set +a
cd core
python -m tests.ai.runner run
```

Required settings are `AI_PROVIDER_BASE_URL`, `AI_PROVIDER_API_KEY`, and
`E2B_API_KEY`. Set `AI_SANDBOX_BACKEND=e2b` and select `AI_PROVIDER_MODEL`
and `E2B_TEMPLATE` for your deployment. Independent cases run in parallel using
LiteLLM deployment limits and cached health, capped at 20 sandboxes. Missing
metadata or health uses the shared conservative fallback of at most four jobs.
`--jobs` can lower concurrency. See `concurrency.json` in the run directory for
the selected limit and reason. By default, each case runs once.

Use `--repeat 12` to run each selected case twelve times with fresh history and
sandboxes. Repeated runs share the same concurrency limit and save transcripts
under separate `run-N/` directories. Any failed run fails the command.
`--diagnostic-attempts 3` runs three independent attempts when the first fails,
even if the second passes. It also judges the same conversation twice more
when an assertion's first judge verdict fails or errors. Judge retries do not
rerun the agent or include earlier verdicts in the judge request. Every verdict
is saved with its attempt number. Any failure keeps the command failed, even
when later judges pass. CI uses this option. Production
provider retries still apply.
Missing configuration fails the run. Failures include a case, turn, step, and
observed evidence. Failed attempts print the full conversation to stdout,
including reasoning, tool calls and results, and before/after schedule YAML.
Every attempt saves a readable Markdown transcript under repository-root
`artifacts/ai-testcases/<run>/`, including successful conversations. Passing
attempts print one status line with the file path. Each run has its own directory,
with a separate file for each case and attempt. The final summary shows each
outcome and failed/total attempt counts. Assertion failures do not stop later turns.
Execution errors stop that attempt.

## Authoring

Use the ordered `steps` list in
[testcases/basics/01_already-in-ai-chat.yaml](testcases/basics/01_already-in-ai-chat.yaml)
as an example. Each step has exactly one primary key:

| Key | Meaning |
| --- | --- |
| `date` | ISO 8601 datetime with timezone. Persists until changed. |
| `yaml` | Schedule fixture name relative to `fixtures/`. Replaces current schedule data. |
| `user` | Starts a new turn. Optional `attachment` accepts a fixture name or list. |
| `tool` | Requires a tool call with the exact name and matching supplied arguments. |
| `assistant` | Requires `contains_any`, a `judge` rubric, or both. Optional `case_sensitive` applies to matching. |
| `schedule` | Requires `unchanged: true`, an `added` mapping, or `equals: <fixture.yaml>`. |

Unknown fields fail validation, except tool argument fields, which depend on
the tool being asserted. Attachments must exist inside `fixtures/`. Schedule
fixtures can reference existing files within `core/tests/`, relative to
`fixtures/`, and must contain YAML mappings. Duplicate YAML keys are rejected.

Configuration affects the next user turn. Finish a turn's assertions before
its next `date` or `yaml` step. Conversation history survives replacements.
Without `yaml`, the starting schedule is `fixtures/empty.yaml`, including the
app's mandatory one-shift-per-day rule. Without `date`, the clock is real UTC.

Attachments remain available in later turns. Production paths include the
one-based upload position, for example `/workspace/attachments/01-people.txt`.
Use the actual production path when asserting a read.

Tool and assistant assertions match chronological events within the preceding
user turn. Unasserted events are allowed between matches. Each match consumes
an event, so duplicate assertions require separate events. Tool argument
mappings match supplied fields and allow other arguments. Tool assertions
verify attempted calls, not successful results. Require a specific tool only
when using that tool is part of the intended behavior.

Assistant assertions inspect individual completed messages, including text
before a tool call. They exclude reasoning and failed responses. Matching is
case-insensitive unless `case_sensitive: true` is set.

`assistant.judge` is a nonempty rubric string. Write it as a positive pass
condition. It can be used alone for semantic
checks such as reply language. A judge-only assertion requires a nonempty reply.
When phrase matching is also supplied, both matching and the LLM judge must pass.
The language cases use judge-only assertions for English and Chinese script.
For a numbered rubric, optional `assistant.count: 12` asks the judge to include
`N/12` in its explanation and identify omitted or incomplete points by number.
The entire rubric must still pass. An omitted or null `count` adds no scoring
instructions. `count` requires `judge` and must be a positive integer or null.
Chinese replies default to Traditional Chinese, including for Simplified Chinese
input. Explicit language or script requests override this default. The Simplified
Chinese case checks that exception. The judge always runs for an
executed turn, even when phrase matching or agent execution fails. It reads the
conversation in a separate request with no tools and returns a boolean verdict
and explanation. Invalid verdicts, request errors, and its two-minute timeout
fail the attempt. All saved transcripts include the rubric, model, full judge
request, raw response, verdict, and explanation. The judge uses the configured
provider and model by default. `AI_TEST_JUDGE_MODEL` selects another model on
the same provider. Other cases have no judge unless their assertion requests one.

Schedule assertions compare parsed YAML at the beginning and end of the turn.
Formatting and mapping-key order do not matter. Without a schedule assertion,
no schedule change is allowed. Multiple `added` steps combine into one expected
change. Each listed object must match exactly, including all of its fields.
For `people.items`, omitted `history`, `history: null`, and `history: []` are equivalent.
Omitted `description`, `description: null`, and `description: ''` are also equivalent.
Nonempty values and all other fields must match exactly.
For additions, extra fields, additions, removals, edits, and reordered existing
items fail. New items can appear anywhere in the target list.

`equals: empty.yaml` requires the complete schedule to match that fixture,
including the mandatory one-shift-per-day rule. It ignores `appVersion` metadata.
Optional empty groups, date items, description, and export settings can be omitted.
Mapping-key order and formatting do not matter. Neither `unchanged` nor `equals` can be combined with another
schedule assertion. See `testcases/basics/01_reset-schedule.yaml` for reuse of
the existing 87-person solver fixture without duplication.

When a date is configured, the tester sets and verifies the E2B system clock
immediately after sandbox creation, before hydration. Time then advances
normally. Each new sandbox starts at the persisted configured instant, even
across turns. The timestamp offset determines sandbox timezone. Host clocks
and timeout accounting remain real. A clock setup failure fails the testcase
and closes the sandbox. No production clock or prompt changes are required.

## CI

The dedicated **Test Core AI** workflow validates definitions and runs the
deterministic tester tests on Ubuntu for pushes and pull requests. Live
conversations run on pushes to `j3soon/nurse-scheduling`, after validation passes.
Pull requests and fork repositories do not run live conversations.

Configure repository secrets `AI_PROVIDER_BASE_URL`, `AI_PROVIDER_API_KEY`, and
`E2B_API_KEY`. No repository variables are required. Optional repository
variables `AI_PROVIDER_MODEL` and `E2B_TEMPLATE` override the CI defaults:
`unsloth/Qwen3.8-27B-NVFP4` and `nurse-scheduling-ai-sandbox-github-ci`.
Optional variable `AI_TEST_JUDGE_MODEL` overrides the judge model.
The live job builds its template from `docker/e2b/e2b.Dockerfile` before running
the conversations. Jobs with the same template alias serialize building and
testing, without cancelling an active job. The default CI alias is separate
from production and staging. Missing credentials or a failed template build
fail the live job. Each turn has a five-minute limit.
CI runs two additional attempts for each initially failed case and stays failed.
Read failed attempts' full conversations and the final summary in the
**Run human-reviewed AI conversations** step's job log. CI uploads all saved
transcripts in the `ai-testcase-conversations` artifact, on success and failure.
