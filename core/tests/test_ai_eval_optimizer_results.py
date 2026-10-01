"""Controlled optimizer result delivery and semantic grading checks."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This test is mostly AI generated.

import asyncio
import hashlib
import json
from dataclasses import replace
from io import BytesIO

import pytest
from openpyxl import load_workbook

from nurse_scheduling.ai.optimizer import WORKSPACE_OPTIMIZER_RESULT, optimizer_completion_message
from nurse_scheduling.ai.provider import TextDelta, ToolCall, ToolCallRequest
from nurse_scheduling.ai.sandbox_agent import WORKSPACE_SCHEDULE
from nurse_scheduling.ai.validation import validate_frontend_schedule_yaml

from .ai_eval.grading import EvalCase, RunOutcome, grade
from .ai_eval.optimizer_fixtures import ASSIGNMENTS, FIXTURE, completion_result
from .ai_eval.prompt_ladder import case_digest, load_prompt_steps, validate_prompt_evidence
from .ai_eval.runner import run_case
from .test_ai_eval_runner import CASE_BY_ID, FIXTURE_DIGESTS, ScriptedProvider, _factory, settings


def test_controlled_completion_exports_the_verified_assignment():
    source = FIXTURE.read_text()
    assert validate_frontend_schedule_yaml(source, 1_000_000).valid
    workbook, metadata = completion_result("request-audit", source)
    assert metadata["source_sha256"] == hashlib.sha256(source.encode()).hexdigest()
    assert metadata["result"]["score"] == 33_000_000_000
    ws = load_workbook(BytesIO(workbook)).active
    for row in range(3, 6):
        person = ws.cell(row, 1).value
        for col, assigned in enumerate(ASSIGNMENTS[person], 5):
            value = ws.cell(row, col).value or ""
            assignment = value.split(" [", 1)[0].strip() or "OFF"
            assert assignment == assigned
    assert ws.cell(7, 5).value == "FEASIBLE"
    notes = list(load_workbook(BytesIO(workbook))["Notes"].values)
    assert len(notes) == 3
    assert {r[2] for r in notes[1:]} == {
        "Weight of unmet single-style request: 11000000000",
        "Weight of unmet single-style request: 11000000",
    }


def test_completion_uses_the_production_message_and_mounts_a_fresh_result():
    case = CASE_BY_ID["optimizer-score-same-model"]
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("start", "optimizer", '{"action":"start","timeout_seconds":60}'),))],
        [TextDelta("Running in the background.")],
        [ToolCallRequest((ToolCall("inspect", "bash", '{"command":"inspect result"}'),))],
        [TextDelta(json.dumps(case.answer_json))],
    )
    factory = _factory()
    run = asyncio.run(run_case(provider, settings(), case, factory))
    assert run.passed, run.failures
    source = factory.created[0].files[WORKSPACE_SCHEDULE].decode()
    workbook, metadata = completion_result(case.optimizer_completion, source)
    assert WORKSPACE_OPTIMIZER_RESULT not in factory.created[0].files
    assert factory.created[1].files[WORKSPACE_OPTIMIZER_RESULT] == workbook
    completion = run.trajectory["prompts"][1][-1]
    assert completion == {"role": "user", "content": optimizer_completion_message(metadata)}
    assert run.trajectory["prompts"][1][-2]["content"] == "Running in the background."
    assert all(backend.closed for backend in factory.created)
    assert any(e["kind"] == "optimizer" for e in run.trajectory["events"])


def test_completion_is_not_delivered_without_a_started_job():
    case = CASE_BY_ID["optimizer-score-same-model"]
    provider = ScriptedProvider([TextDelta(json.dumps(case.answer_json))])
    run = asyncio.run(run_case(provider, settings(), case, _factory()))
    assert not run.passed
    assert len(run.trajectory["prompts"]) == 1
    assert run.trajectory["events"][-1]["reason"] == "optimizer was not started"


@pytest.mark.parametrize("value", ["lower", "higher"])
def test_score_oracle_rejects_the_wrong_direction(value):
    case = CASE_BY_ID["optimizer-score-same-model"]
    outcome = RunOutcome(answer=json.dumps({"better": "previous", "scoreDirection": value}))
    assert grade(replace(case, tool_usage=None, optimizer_completion=""), outcome).passed == (value == "higher")


def test_existing_evidence_survives_optional_case_fields():
    validate_prompt_evidence(load_prompt_steps(), CASE_BY_ID, FIXTURE_DIGESTS)
    case = CASE_BY_ID["optimizer-score-same-model"]
    assert case_digest(case) != case_digest(replace(case, answer_json={"better": "current"}))


@pytest.mark.parametrize("answer", ['{"count": 0}', '{"count": false}', "{}", "not JSON"])
def test_structured_oracle_rejects_false_success(answer):
    case = EvalCase("count", "new-schedule", "Count", False, answer_json={"count": 0})
    assert grade(case, RunOutcome(answer=answer)).passed == (answer == '{"count": 0}')
