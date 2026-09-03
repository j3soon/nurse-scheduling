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
from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.provider import (
    ChatMessage,
    ProviderAttempt,
    ProviderError,
    ReasoningDelta,
    TextDelta,
    TokenUsage,
    ToolCall,
    ToolCallRequest,
)
from nurse_scheduling.ai.sandbox import CommandResult, SandboxError
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory
from nurse_scheduling.ai.sandbox_agent import WORKSPACE_SCHEDULE, SandboxTurnMetrics

from .ai_eval.grading import load_cases
from .ai_eval.runner import CASES, CaseRun, default_output_dir, run_all, run_case, select, summarize, write_report

CASE_BY_ID = {case.id: case for case in load_cases(CASES)}


def settings(**overrides: object) -> AiSettings:
    values = {
        "provider_base_url": "https://provider.example/v1",
        "provider_api_key": "test-token",
        "provider_model": "test-model",
    }
    values.update(overrides)
    return AiSettings(**values)


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


class ConcurrentProvider:
    """Return one answer while measuring simultaneous provider streams."""

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def stream_events(self, messages: Sequence[ChatMessage], tools=None) -> AsyncIterator:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.01)
            yield TextDelta("Done.")
        finally:
            self.active -= 1


def _factory(command_handler=None) -> FakeSandboxFactory:
    if command_handler is None:
        command_handler = lambda *_: CommandResult("ok\n", "", 0)
    return FakeSandboxFactory(
        lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=command_handler),
    )


def _description_factory() -> FakeSandboxFactory:
    def edit(_command: str, _timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
        current = backend.files[WORKSPACE_SCHEDULE].decode()
        backend.files[WORKSPACE_SCHEDULE] = current.replace(
            "apiVersion: alpha\ndescription: ''",
            "apiVersion: alpha\ndescription: March ward roster",
        ).encode()
        return CommandResult("updated\n", "", 0)

    return _factory(edit)


def _run(case_id: str, provider: ScriptedProvider, factory: FakeSandboxFactory | None = None) -> CaseRun:
    return asyncio.run(run_case(provider, settings(), CASE_BY_ID[case_id], factory or _factory()))


def test_a_correct_answer_passes_and_records_its_cost():
    run = _run("ask-people-count", ScriptedProvider([TextDelta("There are 87 people.")]))

    assert run.passed
    assert run.category == "00-summary"
    assert run.turns == 1
    assert run.tools == []
    assert not run.proposed
    assert run.seconds >= 0


def test_provider_wait_time_is_recorded_per_inference_turn():
    run = asyncio.run(run_case(ConcurrentProvider(), settings(), CASE_BY_ID["ask-people-count"], _factory()))

    assert run.llm_inference_seconds >= 0.005
    assert run.llm_turn_seconds == pytest.approx([run.llm_inference_seconds])


def test_provider_retries_are_reported_separately_from_logical_turns():
    run = _run(
        "ask-people-count",
        ScriptedProvider([ProviderAttempt(1), ProviderAttempt(2), TextDelta("There are 87 people.")]),
    )

    assert run.as_record()["provider_requests"] == {
        "turns": 1,
        "attempts": 2,
        "retries": 1,
        "retried_turns": 1,
        "attempts_per_turn": [2],
    }


def test_an_answer_in_words_is_accepted():
    run = _run("ask-people-count", ScriptedProvider([TextDelta("There are eighty-seven people.")]))

    assert run.passed


def test_a_wrong_answer_fails_with_the_reason():
    run = _run("ask-people-count", ScriptedProvider([TextDelta("There are 12 people.")]))

    assert not run.passed
    assert "not mentioned" in run.failures[0]


def test_an_edit_case_records_the_tools_and_the_proposal():
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call_0", BASH_TOOL, '{"command":"edit description"}'),))],
        [TextDelta("I propose the new description.")],
    )

    run = _run("description-set", provider, _description_factory())

    assert run.passed
    assert run.tools == [BASH_TOOL]
    assert run.proposed
    assert run.turns == 2


def test_eval_uses_the_sandbox_runner_and_closes_its_backend():
    factory = _description_factory()
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call_0", BASH_TOOL, '{"command":"edit"}'),))],
        [TextDelta("I propose the new description.")],
    )

    run = asyncio.run(
        run_case(
            provider,
            settings(),
            CASE_BY_ID["description-set"],
            factory,
        )
    )

    assert run.passed
    assert run.tools == [BASH_TOOL]
    assert run.proposed
    assert factory.created[0].closed
    assert "`/workspace/schedule.yaml`" in run.trajectory["prompt"][0]["content"]
    timing = run.as_record()["timing"]
    assert timing["end_to_end_seconds"] >= timing["llm_inference_seconds"]
    assert len(timing["llm_turn_seconds"]) == run.turns
    assert sum(timing["llm_turn_seconds"]) == pytest.approx(timing["llm_inference_seconds"], abs=0.002)
    assert timing["sandbox"]["available"] is True
    sandbox = timing["sandbox"]
    assert sandbox["lifetime_seconds"] == pytest.approx(
        sandbox["provisioning_seconds"]
        + sandbox["execution_seconds"]
        + sandbox["pause_transition_seconds"]
        + sandbox["warm_waiting_seconds"]
        + sandbox["suspended_seconds"]
        + sandbox["resume_wait_seconds"]
        + sandbox["teardown_seconds"],
        abs=0.005,
    )
    assert timing["end_to_end_seconds"] >= sandbox["lifetime_seconds"]
    assert timing["sandbox"]["suspension"] == {
        "pause_count": 0,
        "resume_count": 0,
    }


def test_a_failed_tool_call_is_recorded_as_such():
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call_0", BASH_TOOL, '{"command":"false"}'),))],
        [TextDelta("I could not find that text.")],
    )
    factory = _factory(lambda *_: CommandResult("", "not found", 1))

    run = _run("description-set", provider, factory)

    assert not run.passed
    assert run.tools == [f"{BASH_TOOL}(failed)"]
    assert not run.proposed


def test_a_command_that_raises_is_recorded_before_the_sandbox_failure():
    provider = ScriptedProvider(
        [ToolCallRequest((ToolCall("call_0", BASH_TOOL, '{"command":"slow command"}'),))],
    )

    def fail(*_args):
        raise SandboxError("sandbox command failed")

    run = _run("description-set", provider, _factory(fail))

    assert not run.passed
    assert run.error == "sandbox command failed"
    assert run.trajectory["events"][-1] == {
        "kind": "tool_start",
        "name": BASH_TOOL,
        "arguments": '{"command":"slow command"}',
    }


def test_tool_calls_continue_until_the_model_finishes():
    provider = ScriptedProvider(
        *[[ToolCallRequest((ToolCall(f"call_{index}", BASH_TOOL, '{"command":"true"}'),))] for index in range(4)],
        [TextDelta("I need more input.")],
    )

    run = _run("ask-people-count", provider)

    assert run.tools == [BASH_TOOL] * 4
    assert run.turns == 5
    tool_events = [event for event in run.trajectory["events"] if event["kind"] == "tool"]
    assert len(tool_events) == 4


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


def test_token_usage_is_aggregated_across_provider_turns():
    provider = ScriptedProvider(
        [
            ToolCallRequest((ToolCall("call_0", BASH_TOOL, '{"command":"rg people"}'),)),
            TokenUsage(100, 20, 120, cached_prompt_tokens=40, reasoning_tokens=5),
        ],
        [TextDelta("There are 87 people."), TokenUsage(150, 10, 160, cached_prompt_tokens=90)],
    )

    run = _run("ask-people-count", provider)

    assert run.as_record()["token_usage"] == {
        "available": True,
        "complete": True,
        "reported_turns": 2,
        "prompt_tokens": 250,
        "cached_prompt_tokens": 130,
        "completion_tokens": 30,
        "reasoning_tokens": 5,
        "total_tokens": 280,
    }


def test_missing_provider_usage_is_recorded_explicitly():
    run = _run("ask-people-count", ScriptedProvider([TextDelta("There are 87 people.")]))

    assert run.as_record()["token_usage"] == {
        "available": False,
        "complete": False,
        "reported_turns": 0,
        "prompt_tokens": None,
        "cached_prompt_tokens": None,
        "completion_tokens": None,
        "reasoning_tokens": None,
        "total_tokens": None,
    }


def test_cases_are_selected_by_id_and_by_category():
    cases = load_cases(CASES)

    assert len(select(cases, [], [])) == len(cases)
    assert [case.id for case in select(cases, ["people-add"], [])] == ["people-add"]
    assert {case.category for case in select(cases, [], ["06-refusal"])} == {"06-refusal"}


def test_an_unknown_case_id_stops_the_run():
    with pytest.raises(SystemExit, match="no-such-case"):
        select(load_cases(CASES), ["no-such-case"], [])


@pytest.mark.parametrize(("jobs", "expected_max_active"), [(1, 1), (2, 2)])
def test_run_all_bounds_parallelism_and_preserves_case_order(jobs: int, expected_max_active: int):
    cases = load_cases(CASES)[:3]
    provider = ConcurrentProvider()

    runs = asyncio.run(run_all(cases, settings(), provider, jobs, _factory()))

    assert provider.max_active == expected_max_active
    assert [run.case_id for run in runs] == [case.id for case in cases]


def test_run_all_rejects_non_positive_jobs():
    with pytest.raises(ValueError, match="jobs must be positive"):
        asyncio.run(run_all([], settings(), ScriptedProvider(), 0, _factory()))


def test_the_summary_reports_each_category_and_every_failure():
    runs = [
        CaseRun("a", "00-summary", True, 2.0, 1, [], provider_attempts=2, provider_attempts_per_turn=[2]),
        CaseRun("b", "01-reading", False, 7.0, 2, [BASH_TOOL], ["answer mentions '27': not mentioned"]),
    ]

    report = summarize(runs)

    assert "00-summary         1/1" in report
    assert "01-reading         0/1" in report
    assert "total              1/2" in report
    assert "attempts" in report
    assert "retries" in report
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
        "timing",
        "turns",
        "tools",
        "failures",
        "proposed",
        "reasoning_chars",
        "answer",
        "error",
        "token_usage",
        "provider_requests",
    }
    assert record["timing"]["end_to_end_seconds"] == pytest.approx(run.seconds, abs=0.001)
    assert record["timing"]["llm_inference_seconds"] == pytest.approx(run.llm_inference_seconds, abs=0.001)
    assert record["timing"]["llm_turn_seconds"] == pytest.approx(run.llm_turn_seconds, abs=0.001)
    assert record["timing"]["sandbox"]["available"] is True
    assert record["timing"]["sandbox"]["lifetime_seconds"] >= 0
    assert json.loads(json.dumps(record))["case_id"] == "ask-people-count"


def test_each_run_reports_into_its_own_timestamped_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("AI_EVAL_ARTIFACT_ROOT", str(tmp_path))

    directory = default_output_dir()

    assert directory.parent == tmp_path / "ai-evals"
    assert directory.name.endswith("Z")


def test_a_report_holds_the_summary_and_one_line_for_each_case(tmp_path: Path):
    runs = [
        CaseRun("a", "00-summary", True, 2.0, 1, []),
        CaseRun("b", "01-reading", False, 7.0, 2, [BASH_TOOL], ["answer mentions '27': not mentioned"]),
    ]

    summary = write_report(runs, tmp_path / "run")

    assert summary.name == "summary.md"
    assert "00-summary         1/1" in summary.read_text(encoding="utf-8")
    lines = (tmp_path / "run" / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["case_id"] for line in lines] == ["a", "b"]
    assert json.loads(lines[0])["token_usage"]["total_tokens"] is None


def test_a_report_records_case_concurrency_and_wall_time(tmp_path: Path):
    summary = write_report(
        [CaseRun("a", "00-summary", True, 2.0, 1, [])],
        tmp_path / "run",
        jobs=4,
        wall_seconds=1.25,
    )

    text = summary.read_text(encoding="utf-8")
    assert "Case concurrency: 4" in text
    assert "Wall time: 1.2 seconds" in text


def test_summary_markdown_reports_every_sandbox_metric_per_case(tmp_path: Path):
    metrics = SandboxTurnMetrics(
        provisioning_seconds=0.4,
        execution_seconds=1.0,
        pause_transition_seconds=0.3,
        warm_waiting_seconds=3.0,
        suspended_seconds=5.0,
        resume_wait_seconds=0.1,
        max_resume_wait_seconds=0.06,
        teardown_seconds=0.2,
        lifetime_seconds=10.0,
        pause_count=2,
        resume_count=2,
    )
    summary = write_report(
        [CaseRun("a", "00-summary", True, 10.0, 1, [], sandbox_metrics=metrics)],
        tmp_path / "run",
    )

    text = summary.read_text(encoding="utf-8")
    assert "mutually exclusive lifetime components" in text
    assert "| a | 10.000 | 0.400 | 1.000 | 0.300 | 3.000 | 5.000 | 0.100 | 0.200 |" in text
    assert "| a | 2 | 2 | 0.100 | 0.060 |" in text


def test_a_report_never_overwrites_an_earlier_one(tmp_path: Path):
    write_report([CaseRun("a", "00-summary", True, 2.0, 1, [])], tmp_path / "run")

    with pytest.raises(FileExistsError):
        write_report([CaseRun("a", "00-summary", True, 2.0, 1, [])], tmp_path / "run")


def test_a_run_records_everything_it_did():
    edit = '{"command":"edit description"}'
    provider = ScriptedProvider(
        [
            ReasoningDelta("Looking for the description. "),
            ToolCallRequest((ToolCall("call_0", BASH_TOOL, edit),)),
        ],
        [TextDelta("I propose the new description.")],
    )

    trajectory = _run("description-set", provider, _description_factory()).as_trajectory()

    assert trajectory["question"].startswith("Give this schedule the description")
    assert trajectory["prompt"][0]["role"] == "system"
    kinds = [event["kind"] for event in trajectory["events"]]
    assert kinds == ["reasoning", "tool_start", "tool", "text", "proposal"]
    assert trajectory["events"][1]["arguments"] == edit
    tool_event = trajectory["events"][2]
    assert tool_event["ok"]
    assert "passed trusted server-side validation" in tool_event["result"]
    assert "March ward roster" in trajectory["proposal"]["schedule_yaml"]
    assert all(check["passed"] for check in trajectory["checks"])


def test_a_report_keeps_one_trajectory_file_for_each_case(tmp_path: Path):
    runs = [CaseRun("a", "00-summary", True, 2.0, 1, [], trajectory={"events": [{"kind": "text", "text": "hi"}]})]

    write_report(runs, tmp_path / "run")

    trajectory = json.loads((tmp_path / "run" / "cases" / "a.json").read_text(encoding="utf-8"))
    assert trajectory["case_id"] == "a"
    assert trajectory["events"] == [{"kind": "text", "text": "hi"}]
