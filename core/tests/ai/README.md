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
and `E2B_TEMPLATE` for your deployment. Cases run sequentially, once each,
without automatic testcase retries. Production provider retries still apply.
Missing configuration fails the run. Failures include a case, turn, step, and
observed evidence. JSON transcripts and before/after schedule YAML are saved
under repository-root `artifacts/ai-testcases/`. `--output-dir` overrides this.

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
| `assistant` | Requires `contains_any`, with optional boolean `case_sensitive`. |
| `schedule` | Requires `unchanged: true` or `added` mapping dotted list paths to exact objects. |

Unknown fields fail validation, except tool argument fields, which depend on
the tool being asserted. Fixtures must exist inside `fixtures/`. Schedule
fixtures must contain YAML mappings. Duplicate YAML keys are rejected.

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

Schedule assertions compare parsed YAML at the beginning and end of the turn.
Formatting and mapping-key order do not matter. Without a schedule assertion,
no schedule change is allowed. Multiple `added` steps combine into one expected
change. Each listed object must match exactly, including all of its fields.
For `people.items`, omitted `history`, `history: null`, and `history: []` are equivalent.
Omitted `description`, `description: null`, and `description: ''` are also equivalent.
Nonempty values and all other fields must match exactly.
Additional fields, additions, removals, edits, and reordered existing items
fail. New items can appear anywhere in the target list. `unchanged: true`
cannot be combined with another schedule assertion. Only list additions are
supported initially. Add other operators when a reviewed case requires them.

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
The live job builds its template from `docker/e2b/e2b.Dockerfile` before running
the conversations. Jobs with the same template alias serialize building and
testing, without cancelling an active job. The default CI alias is separate
from production and staging. Missing credentials or a failed template build
fail the live job. Each turn has a five-minute limit.
Failure evidence is uploaded as the `ai-testcase-failures` workflow artifact.
