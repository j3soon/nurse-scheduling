"""Tests for the evaluation runner, using a scripted provider."""

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
import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.provider import (
    ChatMessage,
    ProviderError,
    ReasoningDelta,
    TextDelta,
    ToolCall,
    ToolCallRequest,
)

from .ai_eval.grading import load_cases
from .ai_eval.runner import CASES, CaseRun, default_output_dir, run_case, select, summarize, write_report

CASE_BY_ID = {case.id: case for case in load_cases(CASES)}


def settings() -> AiSettings:
    return AiSettings(
        provider_base_url="https://provider.example/v1",
        provider_api_key="test-token",
        provider_model="test-model",
        max_agent_turns=4,
    )


class ScriptedProvider:
    """Replay prepared turns, or fail, without contacting a provider."""

    def __init__(self, *turns) -> None:
        self._turns = list(turns)

    async def stream_events(self, messages: Sequence[ChatMessage], tools=None) -> AsyncIterator:
        turn = self._turns.pop(0) if self._turns else [TextDelta("Done.")]
        if isinstance(turn, Exception):
            raise turn
        for event in turn:
            yield event


def _run(case_id: str, provider: ScriptedProvider) -> CaseRun:
    return asyncio.run(run_case(provider, settings(), CASE_BY_ID[case_id]))


def test_a_correct_answer_passes_and_records_its_cost():
    run = _run("ask-people-count", ScriptedProvider([TextDelta("There are 87 people.")]))

    assert run.passed
    assert run.category == "00-summary"
    assert run.turns == 1
    assert run.tools == []
    assert not run.proposed
    assert run.seconds >= 0


def test_an_answer_in_words_is_accepted():
    run = _run("ask-people-count", ScriptedProvider([TextDelta("There are eighty-seven people.")]))

    assert run.passed


def test_a_wrong_answer_fails_with_the_reason():
    run = _run("ask-people-count", ScriptedProvider([TextDelta("There are 12 people.")]))

    assert not run.passed
    assert "not mentioned" in run.failures[0]


def test_an_edit_case_records_the_tools_and_the_proposal():
    # The anchor includes the line above, because every person also has a description.
    edit = json.dumps(
        {
            "old_str": "apiVersion: alpha\ndescription: ''",
            "new_str": "apiVersion: alpha\ndescription: March ward roster",
        }
    )
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call_0", "edit_schedule", edit),))],
        [TextDelta("I propose the new description.")],
    )

    run = _run("description-set", provider)

    assert run.passed
    assert run.tools == ["edit_schedule"]
    assert run.proposed
    assert run.turns == 2


def test_a_failed_tool_call_is_recorded_as_such():
    edit = json.dumps({"old_str": "nothing matches this", "new_str": "x"})
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call_0", "edit_schedule", edit),))],
        [TextDelta("I could not find that text.")],
    )

    run = _run("description-set", provider)

    assert not run.passed
    assert run.tools == ["edit_schedule(failed)"]
    assert not run.proposed


def test_a_provider_failure_is_reported_rather_than_raised():
    run = _run("ask-people-count", ScriptedProvider(ProviderError("The AI provider is unavailable.")))

    assert not run.passed
    assert run.error == "The AI provider is unavailable."
    assert run.failures == ["the provider failed"]


def test_reasoning_length_is_measured_without_entering_the_answer():
    provider = ScriptedProvider([ReasoningDelta("Counting people."), TextDelta("There are 87 people.")])

    run = _run("ask-people-count", provider)

    assert run.passed
    assert run.reasoning_chars == len("Counting people.")
    assert "Counting" not in run.answer


def test_cases_are_selected_by_id_and_by_category():
    cases = load_cases(CASES)

    assert len(select(cases, [], [])) == len(cases)
    assert [case.id for case in select(cases, ["people-add"], [])] == ["people-add"]
    assert {case.category for case in select(cases, [], ["06-refusal"])} == {"06-refusal"}


def test_an_unknown_case_id_stops_the_run():
    with pytest.raises(SystemExit, match="no-such-case"):
        select(load_cases(CASES), ["no-such-case"], [])


def test_the_summary_reports_each_category_and_every_failure():
    runs = [
        CaseRun("a", "00-summary", True, 2.0, 1, []),
        CaseRun("b", "01-reading", False, 7.0, 2, ["view_schedule"], ["answer mentions '27': not mentioned"]),
    ]

    report = summarize(runs)

    assert "00-summary         1/1" in report
    assert "01-reading         0/1" in report
    assert "total              1/2" in report
    assert "b: answer mentions '27': not mentioned" in report
    assert summarize([]) == "No cases ran."


def test_the_report_records_enough_to_explain_a_run():
    run = _run("ask-people-count", ScriptedProvider([TextDelta("There are 87 people.")]))

    record = run.as_record()

    assert set(record) == {
        "case_id",
        "category",
        "passed",
        "seconds",
        "turns",
        "tools",
        "failures",
        "proposed",
        "reasoning_chars",
        "answer",
        "error",
    }
    assert json.loads(json.dumps(record))["case_id"] == "ask-people-count"


def test_each_run_reports_into_its_own_timestamped_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("AI_EVAL_ARTIFACT_ROOT", str(tmp_path))

    directory = default_output_dir()

    assert directory.parent == tmp_path / "ai-evals"
    assert directory.name.endswith("Z")


def test_a_report_holds_the_summary_and_one_line_for_each_case(tmp_path: Path):
    runs = [
        CaseRun("a", "00-summary", True, 2.0, 1, []),
        CaseRun("b", "01-reading", False, 7.0, 2, ["view_schedule"], ["answer mentions '27': not mentioned"]),
    ]

    summary = write_report(runs, tmp_path / "run")

    assert summary.name == "summary.md"
    assert "00-summary         1/1" in summary.read_text(encoding="utf-8")
    lines = (tmp_path / "run" / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["case_id"] for line in lines] == ["a", "b"]


def test_a_report_never_overwrites_an_earlier_one(tmp_path: Path):
    write_report([CaseRun("a", "00-summary", True, 2.0, 1, [])], tmp_path / "run")

    with pytest.raises(FileExistsError):
        write_report([CaseRun("a", "00-summary", True, 2.0, 1, [])], tmp_path / "run")


def test_a_run_records_everything_it_did():
    edit = json.dumps(
        {
            "old_str": "apiVersion: alpha\ndescription: ''",
            "new_str": "apiVersion: alpha\ndescription: March ward roster",
        }
    )
    provider = ScriptedProvider(
        [
            ReasoningDelta("Looking for the description. "),
            ToolCallRequest((ToolCall("call_0", "edit_schedule", edit),)),
        ],
        [TextDelta("I propose the new description.")],
    )

    trajectory = _run("description-set", provider).as_trajectory()

    assert trajectory["question"].startswith("Give this schedule the description")
    assert trajectory["prompt"][0]["role"] == "system"
    kinds = [event["kind"] for event in trajectory["events"]]
    assert kinds == ["reasoning", "tool", "text", "proposal"]
    tool_event = trajectory["events"][1]
    assert tool_event["arguments"] == edit
    assert tool_event["ok"]
    # The new-schedule fixture has no date range yet, so the edit is accepted for
    # adding no new problem rather than for leaving the file valid.
    assert "Changes so far" in tool_event["result"]
    assert "March ward roster" in trajectory["proposal"]["schedule_yaml"]
    assert all(check["passed"] for check in trajectory["checks"])


def test_a_report_keeps_one_trajectory_file_for_each_case(tmp_path: Path):
    runs = [CaseRun("a", "00-summary", True, 2.0, 1, [], trajectory={"events": [{"kind": "text", "text": "hi"}]})]

    write_report(runs, tmp_path / "run")

    trajectory = json.loads((tmp_path / "run" / "cases" / "a.json").read_text(encoding="utf-8"))
    assert trajectory["case_id"] == "a"
    assert trajectory["events"] == [{"kind": "text", "text": "hi"}]
