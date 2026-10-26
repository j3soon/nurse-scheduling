"""Test human-reviewed AI definitions, assertions, and production execution."""

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
from datetime import datetime

import pytest

from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.provider import ResponseEnd, TextDelta, ToolCallRequest
from nurse_scheduling.ai.sandbox import CommandResult, SandboxError
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory
from nurse_scheduling.ai.transcript import ToolCall
from nurse_scheduling.ai.workspace import WORKSPACE_SCHEDULE
from tests.ai.assertions import check_event, check_schedule
from tests.ai.judge import evaluate
from tests.ai.runner import DatedFactory, _timezone, main, run_case, run_cases
from tests.ai.schema import FIXTURES, TESTCASES, DefinitionError, Step, load_case, load_yaml


def definition(tmp_path, text):
    path = tmp_path / "case.yaml"
    path.write_text(text, encoding="utf-8")
    return load_case(path)


@pytest.mark.parametrize("path", sorted(TESTCASES.rglob("*.yaml")), ids=lambda path: path.stem)
def test_reviewed_case_definitions(path):
    assert load_case(path).steps


def test_parser_retains_order_dates_and_attachment_lists(tmp_path):
    case = definition(
        tmp_path,
        """steps:
  - date: 2026-10-25T09:00:00+08:00
  - yaml: empty.yaml
  - user: Read these.
    attachment: [people.txt, empty.yaml]
  - tool: read
    path: /workspace/attachments/01-people.txt
  - assistant: {contains_any: [Alice], case_sensitive: true}
  - schedule: {unchanged: true}
""",
    )
    assert [step.kind for step in case.steps] == ["date", "yaml", "user", "tool", "assistant", "schedule"]
    assert case.steps[0].value.isoformat() == "2026-10-25T09:00:00+08:00"
    assert case.steps[2].options["attachment"] == (FIXTURES / "people.txt", FIXTURES / "empty.yaml")


@pytest.mark.parametrize(
    "text",
    [
        "steps: []",
        "steps: [hello]",
        "steps: [{user: one, yaml: empty.yaml}]",
        "steps: [{tool: read}]",
        "steps: [{assistant: {contains_any: [yes]}}]",
        "steps: [{date: 2026-10-25T09:00:00}, {user: hi}]",
        "steps: [{date: yesterday}, {user: hi}]",
        "steps: [{user: hi, typo: true}]",
        "steps: [{yaml: absent.yaml}, {user: hi}]",
        "steps: [{yaml: ../schema.py}, {user: hi}]",
        "steps: [{yaml: people.txt}, {user: hi}]",
        "steps: [{user: hi, attachment: []}]",
        "steps: [{user: hi, attachment: absent.txt}]",
        "steps: [{user: hi}, {assistant: {contains_any: []}}]",
        "steps: [{user: hi}, {assistant: {contains_any: [true]}}]",
        "steps: [{user: hi}, {assistant: {contains_any: [hello], case_sensitive: 1}}]",
        "steps: [{user: hi}, {assistant: {contains: hello}}]",
        "steps: [{user: hi}, {schedule: {unchanged: false}}]",
        "steps: [{user: hi}, {schedule: {removed: {people.items: []}}}]",
        "steps: [{user: hi}, {schedule: {added: {people.items: []}}}]",
        "steps: [{user: hi}, {schedule: {added: {people.items: [Alice]}}}]",
        "steps: [{user: hi}, {schedule: {unchanged: true}}, {schedule: {added: {people.items: [{id: Alice}]}}}]",
        "steps: [{user: hi}, {schedule: {unchanged: true}}, {schedule: {unchanged: true}}]",
        "steps: [{user: hi}, {yaml: empty.yaml}, {tool: read}]",
        "steps: [{user: hi}, {date: 2026-10-25T09:00:00Z}]",
        "steps: [{user: hi}]\nextra: value",
        "steps: [{user: hi, user: bye}]",
    ],
    ids=[f"invalid-{index}" for index in range(27)],
)
def test_invalid_definitions(tmp_path, text):
    with pytest.raises(DefinitionError, match=r"case.yaml: step \d+:"):
        definition(tmp_path, text)


def test_duplicate_fixture_keys_fail_without_credentials(tmp_path):
    (tmp_path / "bad.yaml").write_text("people: []\npeople: {}\n", encoding="utf-8")
    path = tmp_path / "case.yaml"
    path.write_text("steps: [{yaml: bad.yaml}, {user: hi}]", encoding="utf-8")
    with pytest.raises(DefinitionError, match="duplicate key"):
        load_case(path, fixtures=tmp_path)


def test_reset_reuses_solver_fixture_and_requires_complete_empty_schedule():
    case = load_case(TESTCASES / "basics" / "01_reset-schedule.yaml")
    source = case.steps[0].value
    assert source == TESTCASES.parents[1] / "testcases" / "real" / "large-ward-with-87-people-2025-11.yaml"
    before = source.read_text(encoding="utf-8")
    assert len(load_yaml(before)["people"]["items"]) == 87
    expected = (FIXTURES / "empty.yaml").read_text(encoding="utf-8")
    checks = [case.steps[-1]]
    check_schedule(checks, before, "# Reformat\n" + expected)
    omitted_defaults = expected.replace("  groups: []\n", "").replace(
        "dates:\n  range: {}\n  items: []", "dates:\n  range: {}"
    )
    check_schedule(checks, before, omitted_defaults)
    check_schedule(checks, before, expected + "export: {formatting: [], extraColumns: [], extraRows: []}\n")
    for version in ("test", "null", "42"):
        check_schedule(checks, before, expected + f"appVersion: {version}\n")
    for after in (
        before,
        expected.replace("people:\n  items: []", "people:\n  items: [{id: Alice}]"),
        expected.replace("preferences:\n  - type: at most one shift per day", "preferences: []"),
        expected + "extra: true\n",
        expected.replace("range: {}", "range: {startDate: '2025-11-01', endDate: '2025-11-30'}"),
        expected.replace("  groups: []", "  groups: [{id: leftover, members: []}]", 1),
    ):
        with pytest.raises(AssertionError, match="schedule does not equal fixture"):
            check_schedule(checks, before, after)


@pytest.mark.parametrize(
    "text",
    [
        "steps: [{yaml: ../../../AGENTS.md}, {user: hi}]",
        "steps: [{user: hi, attachment: ../../testcases/real/large-ward-with-87-people-2025-11.yaml}]",
        "steps: [{user: hi}, {schedule: {equals: absent.yaml}}]",
        "steps: [{user: hi}, {schedule: {equals: people.txt}}]",
        "steps: [{user: hi}, {schedule: {equals: 42}}]",
        "steps: [{user: hi}, {schedule: {equals: empty.yaml}}, {schedule: {unchanged: true}}]",
        "steps: [{user: hi}, {schedule: {equals: empty.yaml}}, {schedule: {equals: empty.yaml}}]",
        "steps: [{user: hi}, {schedule: {equals: empty.yaml, unchanged: true}}]",
        "steps: [{user: hi}, {schedule: {equals: empty.yaml}}, {schedule: {added: {people.items: [{id: Alice}]}}}]",
    ],
)
def test_invalid_schedule_fixtures_and_equality_combinations(tmp_path, text):
    with pytest.raises(DefinitionError):
        definition(tmp_path, text)


def test_production_execution_checks_schedule_equality():
    case = load_case(TESTCASES / "basics" / "01_reset-schedule.yaml")
    expected = (FIXTURES / "empty.yaml").read_text(encoding="utf-8")
    provider = ScriptedProvider(
        [
            [tool_call("reset", "write", json.dumps({"path": WORKSPACE_SCHEDULE, "content": expected}))],
            [TextDelta("Reset complete."), ResponseEnd("stop")],
        ]
    )
    assert asyncio.run(run_case(case, provider, settings(), FakeSandboxFactory()))
    unchanged = ScriptedProvider([[TextDelta("Reset complete."), ResponseEnd("stop")]])
    assert not asyncio.run(run_case(case, unchanged, settings(), FakeSandboxFactory()))


def test_ordered_events_and_case_matching():
    tool = Step(2, "tool", "read", {"path": "/guide"})
    answer = Step(3, "assistant", {"contains_any": ["already here"]}, {})
    events = [
        {"kind": "assistant", "text": "ALREADY HERE"},
        {"kind": "tool", "name": "read", "arguments": {"path": "/guide", "limit": 10}},
        {"kind": "assistant", "text": "You are Already Here."},
    ]
    cursor = check_event(tool, events, 0)
    assert check_event(answer, events, cursor) == 3
    with pytest.raises(AssertionError):
        check_event(answer, events, 3)
    with pytest.raises(AssertionError):
        check_event(
            Step(3, "assistant", {"contains_any": ["already here"], "case_sensitive": True}, {}), events, cursor
        )
    with pytest.raises(AssertionError):
        check_event(tool, events, cursor)
    with pytest.raises(AssertionError):
        check_event(tool, [], 0)  # A prior turn's calls cannot satisfy this turn.


def test_schedule_additions_are_exact_and_keep_existing_item_order():
    steps = [Step(2, "schedule", {"added": {"people.items": [{"id": "Alice"}]}}, {})]
    before = "people: {items: [{id: Bob}, {id: Carol}]}\n"
    check_schedule(steps, before, "people: {items: [{id: Bob}, {id: Alice}, {id: Carol}]}\n")
    for after in (
        "people: {items: [{id: Alice, description: extra}, {id: Bob}, {id: Carol}]}",
        "people: {items: [{id: Alice}, {id: Bob}, {id: Carol}, {id: Dave}]}",
        "people: {items: [{id: Alice}, {id: Carol}, {id: Bob}]}",
        "people: {items: [{id: Alice}, {id: Bob}]}",
        "people: {items: [{id: Alice}, {id: Bob}, {id: Edited}]}",
    ):
        with pytest.raises(AssertionError):
            check_schedule(steps, before, after)
    check_schedule([], before, "# Reformat\npeople:\n  items: [{id: Bob}, {id: Carol}]\n")
    with pytest.raises(AssertionError):
        check_schedule([], before, "people: {items: [{id: Changed}]}")


def test_multiple_schedule_steps_combine_and_consume_additions_once():
    steps = [
        Step(2, "schedule", {"added": {"people.items": [{"id": "Alice"}]}}, {}),
        Step(3, "schedule", {"added": {"shiftTypes.items": [{"id": "D"}]}}, {}),
    ]
    before = "people: {items: []}\nshiftTypes: {items: []}"
    after = "people: {items: [{id: Alice}]}\nshiftTypes: {items: [{id: D}]}"
    check_schedule(steps, before, after)
    with pytest.raises(AssertionError):
        check_schedule([steps[0], steps[0]], before, after)


def tool_call(id, name, arguments):
    return ToolCallRequest((ToolCall(id, name, arguments),))


class ScriptedProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    async def stream_events(self, messages, tools=()):
        self.requests.append(messages)
        for event in next(self.responses):
            yield event


def settings():
    return AiSettings(
        provider_base_url="http://provider.invalid",
        provider_api_key="provider-secret",
        provider_model="test",
        e2b_api_key="sandbox-secret",
    )


def test_production_execution_keeps_schedule_history_and_attachments(tmp_path):
    case = definition(
        tmp_path,
        """steps:
  - user: Add Alice and read the attachment.
    attachment: people.txt
  - schedule:
      added: {people.items: [{id: Alice, description: '', history: []}]}
  - user: Read it again.
  - tool: read
    path: /workspace/attachments/01-people.txt
  - yaml: empty.yaml
  - user: Read it once more after the schedule replacement.
  - tool: read
    path: /workspace/attachments/01-people.txt
""",
    )
    initial = (FIXTURES / "empty.yaml").read_text(encoding="utf-8")
    edited = initial.replace("people:\n  items: []", "people:\n  items: [{id: Alice, description: '', history: []}]")
    read = tool_call("read-1", "read", json.dumps({"path": "/workspace/attachments/01-people.txt"}))
    provider = ScriptedProvider(
        [
            [tool_call("write-1", "write", json.dumps({"path": WORKSPACE_SCHEDULE, "content": edited}))],
            [TextDelta("Added Alice."), ResponseEnd("stop")],
            [read],
            [TextDelta("Alice, Bob, Carol."), ResponseEnd("stop")],
            [read],
            [TextDelta("Alice, Bob, Carol."), ResponseEnd("stop")],
        ]
    )
    factory = FakeSandboxFactory()
    assert asyncio.run(run_case(case, provider, settings(), factory))
    assert len(factory.created) == 3
    assert all(sandbox.closed for sandbox in factory.created)
    assert load_yaml(factory.created[1].files[WORKSPACE_SCHEDULE].decode())["people"]["items"][0]["id"] == "Alice"
    assert load_yaml(factory.created[2].files[WORKSPACE_SCHEDULE].decode())["people"]["items"] == []
    assert all("/workspace/attachments/01-people.txt" in sandbox.files for sandbox in factory.created)
    assert any(message.get("content") == "Added Alice." for message in provider.requests[2])
    assert any("schedule changed in the app" in str(message.get("content")) for message in provider.requests[4])


@pytest.mark.parametrize("failure", ["assertion", "unexpected-change", "provider"], ids=str)
def test_failure_stdout_and_sandbox_cleanup(tmp_path, capsys, failure):
    case = definition(tmp_path, "steps: [{user: hi}, {assistant: {contains_any: [expected]}}]")
    edited = (FIXTURES / "empty.yaml").read_text(encoding="utf-8").replace("description: ''", "description: changed", 1)
    responses = [
        [tool_call("write", "write", json.dumps({"path": WORKSPACE_SCHEDULE, "content": edited}))],
        [TextDelta("wrong" if failure == "assertion" else "expected"), ResponseEnd("stop")],
    ]

    class Provider(ScriptedProvider):
        async def stream_events(self, messages, tools=()):
            if failure == "provider" and self.requests:
                raise RuntimeError("provider-secret sandbox-secret connection failed")
            async for event in super().stream_events(messages, tools):
                yield event

    factory = FakeSandboxFactory()
    transcript = tmp_path / "attempt-1.md"
    assert not asyncio.run(run_case(case, Provider(responses), settings(), factory, transcript_path=transcript))
    assert factory.created[0].closed
    log = capsys.readouterr().out
    assert "provider-secret" not in log and "sandbox-secret" not in log
    assert "turn 1, step" in log and "Schedule before" in log
    saved = transcript.read_text(encoding="utf-8")
    assert "provider-secret" not in saved and "sandbox-secret" not in saved
    assert saved in log
    if failure == "unexpected-change":
        assert "unexpected schedule changes" in log


def test_clock_setup_precedes_hydration_and_retains_timezone():
    date = datetime.fromisoformat("2026-10-25T09:00:00+08:00")

    def command(command, timeout, backend):
        assert not backend.files
        assert command.startswith("sudo -n date --set=")
        return CommandResult(f"{date.timestamp()}\n{date.timestamp()}\n", "", 0)

    factory = FakeSandboxFactory(lambda name: FakeSandboxBackend(name, command_handler=command))
    clock = DatedFactory(factory)
    clock.date = date

    async def exercise():
        for _ in range(2):
            sandbox = await clock.create(envs={"TZ": _timezone(date)})
            await sandbox.close()

    asyncio.run(exercise())
    assert all(sandbox.envs["TZ"] == "UTC-08:00:00" for sandbox in factory.created)
    assert _timezone(None) == "UTC"
    assert _timezone(datetime.fromisoformat("2026-10-25T09:00:00-03:30")) == "UTC+03:30:00"


@pytest.mark.parametrize(
    "result", [CommandResult("", "denied", 1), CommandResult("0\n0\n", "", 0)], ids=["denied", "wrong-clock"]
)
def test_clock_failure_closes_new_sandbox(result):
    factory = FakeSandboxFactory(lambda name: FakeSandboxBackend(name, command_handler=lambda *_: result))
    clock = DatedFactory(factory)
    clock.date = datetime.fromisoformat("2026-10-25T09:00:00Z")
    with pytest.raises(SandboxError):
        asyncio.run(clock.create())
    assert factory.created[0].closed


def test_cli_validation_does_not_initialize_providers(monkeypatch, tmp_path):
    def forbidden():
        pytest.fail("validation initialized provider settings")

    monkeypatch.setattr(AiSettings, "from_env", forbidden)
    assert main(["validate"]) == 0
    assert main(["validate", str(tmp_path)]) == 2


def test_date_steps_persist_and_change_between_turns(tmp_path):
    case = definition(
        tmp_path,
        """steps:
  - date: 2026-10-25T09:00:00+08:00
  - user: Read the schedule.
  - user: Read it again.
  - date: 2027-01-01T12:00:00-03:30
  - user: Read it at the new date.
""",
    )
    dates = [case.steps[0].value.timestamp()] * 2 + [case.steps[3].value.timestamp()]

    def command(command, timeout, backend):
        assert not backend.files
        expected = dates[len(factory.created) - 1]
        assert f"@{expected}" in command
        return CommandResult(f"{expected}\n{expected}\n", "", 0)

    factory = FakeSandboxFactory(lambda name: FakeSandboxBackend(name, command_handler=command))
    provider = ScriptedProvider(
        [
            event
            for index in range(3)
            for event in (
                [tool_call(str(index), "read", json.dumps({"path": WORKSPACE_SCHEDULE}))],
                [TextDelta("Read."), ResponseEnd("stop")],
            )
        ]
    )
    assert asyncio.run(run_case(case, provider, settings(), factory))
    assert [sandbox.envs["TZ"] for sandbox in factory.created] == ["UTC-08:00:00", "UTC-08:00:00", "UTC+03:30:00"]
    assert all(sandbox.closed for sandbox in factory.created)


def test_schedule_failure_is_attributed_to_preceding_turn(tmp_path, capsys):
    case = definition(tmp_path, "steps: [{user: change}, {user: follow-up}]")
    edited = (FIXTURES / "empty.yaml").read_text(encoding="utf-8").replace("description: ''", "description: changed", 1)
    provider = ScriptedProvider(
        [
            [tool_call("write", "write", json.dumps({"path": WORKSPACE_SCHEDULE, "content": edited}))],
            [TextDelta("Changed."), ResponseEnd("stop")],
            [TextDelta("Follow-up reply."), ResponseEnd("stop")],
        ]
    )
    assert not asyncio.run(run_case(case, provider, settings(), FakeSandboxFactory()))
    log = capsys.readouterr().out
    assert "turn 1, step 1" in log
    assert len(provider.requests) == 3
    assert "## Turn 2" in log and "Follow-up reply." in log


@pytest.mark.parametrize(
    ("reply", "passed"),
    [
        ("You're already here in the Experimental AI chat.", True),
        ("You're already talking to the Experimental AI assistant.", True),
        ("Since you're already chatting with me here, ask what you'd like done.", True),
        ("You're in the right place. This is the Experimental AI assistant.", True),
        ("Good news, you've actually found it! This is the Experimental AI chat.", True),
        ("Yes, that's this chat! I'm the Experimental AI assistant.", True),
        ("You're chatting with it right now. This is the Experimental AI page.", True),
        ("Yes, this chat is the AI assistant in the app.", True),
        ("Yes, this chat **is** the AI assistant in the app.", True),
        ("Open Experimental AI from the menu to reach the assistant.", False),
    ],
    ids=[
        "already-here",
        "already-talking",
        "already-chatting",
        "right-place",
        "found-it",
        "this-chat",
        "chatting-now",
        "chat-is-assistant",
        "chat-is-assistant-bold",
        "navigation-only",
    ],
)
def test_chat_identity_case_accepts_equivalent_acknowledgements(tmp_path, reply, passed):
    case = load_case(TESTCASES / "basics" / "01_already-in-ai-chat.yaml")
    provider = ScriptedProvider([[TextDelta(reply), ResponseEnd("stop")]])
    judge = ScriptedProvider(
        [[TextDelta(json.dumps({"passed": passed, "reason": "Fixture verdict."})), ResponseEnd("stop")]]
    )
    assert asyncio.run(run_case(case, provider, settings(), FakeSandboxFactory(), judge_provider=judge)) is passed
    assert len(judge.requests) == 1


@pytest.mark.parametrize("expected_history", ["", ", history: null", ", history: []"], ids=["omitted", "null", "empty"])
@pytest.mark.parametrize("actual_history", ["", ", history: null", ", history: []"], ids=["omitted", "null", "empty"])
def test_empty_person_history_is_equivalent_in_schedule_assertions(expected_history, actual_history):
    expected_person = load_yaml("{id: Alice" + expected_history + "}")
    added = [Step(2, "schedule", {"added": {"people.items": [expected_person]}}, {})]
    before = "people: {items: []}"
    after = "people: {items: [{id: Alice" + actual_history + "}]}"
    check_schedule(added, before, after)
    unchanged_before = "people: {items: [{id: Alice" + expected_history + "}]}"
    check_schedule([], unchanged_before, after)
    check_schedule([Step(2, "schedule", {"unchanged": True}, {})], unchanged_before, after)
    assert added[0].value["added"]["people.items"][0] == expected_person


@pytest.mark.parametrize("history", ["null", "[]"], ids=["null", "empty"])
def test_history_equivalence_does_not_hide_history_changes_or_other_fields(history):
    added = [Step(2, "schedule", {"added": {"people.items": [{"id": "Alice", "history": []}]}}, {})]
    with pytest.raises(AssertionError):
        check_schedule(added, "people: {items: []}", "people: {items: [{id: Alice, history: [D]}]}")
    with pytest.raises(AssertionError):
        check_schedule(
            [],
            "people: {items: [{id: Alice, history: [D]}]}",
            "people: {items: [{id: Alice, history: " + history + "}]}",
        )
    with pytest.raises(AssertionError):
        check_schedule(
            [],
            "people: {items: [{id: Alice, history: " + history + "}]}",
            "people: {items: [{id: Alice, history: [D]}]}",
        )
    with pytest.raises(AssertionError):
        check_schedule(
            added, "people: {items: []}", "people: {items: [{id: Alice, description: nurse, history: " + history + "}]}"
        )
    with pytest.raises(AssertionError):
        check_schedule([], "shiftTypes: {items: [{id: D}]}", "shiftTypes: {items: [{id: D, history: " + history + "}]}")


def test_nonempty_history_and_tool_arguments_still_match_exactly():
    added = [Step(2, "schedule", {"added": {"people.items": [{"id": "Alice", "history": ["D"]}]}}, {})]
    check_schedule(added, "people: {items: []}", "people: {items: [{id: Alice, history: [D]}]}")
    for history in ("[]", "[N]", "[D, N]"):
        with pytest.raises(AssertionError):
            check_schedule(added, "people: {items: []}", "people: {items: [{id: Alice, history: " + history + "}]}")
    with pytest.raises(AssertionError):
        check_event(
            Step(2, "tool", "custom", {"history": []}),
            [{"kind": "tool", "name": "custom", "arguments": {"history": None}}],
            0,
        )


@pytest.mark.parametrize("expected", ["", ", description: null", ", description: ''"], ids=["omitted", "null", "empty"])
@pytest.mark.parametrize("actual", ["", ", description: null", ", description: ''"], ids=["omitted", "null", "empty"])
def test_empty_person_description_is_equivalent(expected, actual):
    person = load_yaml("{id: Alice" + expected + "}")
    steps = [Step(2, "schedule", {"added": {"people.items": [person]}}, {})]
    after = "people: {items: [{id: Alice" + actual + ", history: []}]}"
    check_schedule(steps, "people: {items: []}", after)
    check_schedule([], "people: {items: [{id: Alice" + expected + "}]}", after)
    assert steps[0].value["added"]["people.items"][0] == person
    for extra in (", description: nurse", ", unknown: null", ", history: [D]"):
        with pytest.raises(AssertionError):
            check_schedule(steps, "people: {items: []}", "people: {items: [{id: Alice" + extra + "}]}")
    with pytest.raises(AssertionError):
        check_schedule([], "people: {items: [{id: Alice, description: nurse}]}", after)


@pytest.mark.parametrize(
    "replies",
    [["expected"], ["wrong", "expected", "expected"], ["wrong", "wrong", "wrong"]],
    ids=["first-pass", "later-pass", "all-fail"],
)
def test_diagnostic_attempts_preserve_initial_failure_and_isolate_history(tmp_path, capsys, replies):
    case = definition(tmp_path, "steps: [{user: hi}, {assistant: {contains_any: [expected]}}]")
    provider = ScriptedProvider(
        [
            response
            for reply in replies
            for response in (
                [tool_call("read", "read", json.dumps({"path": WORKSPACE_SCHEDULE}))],
                [TextDelta(reply), ResponseEnd("stop")],
            )
        ]
    )
    factory = FakeSandboxFactory()
    output_dir = tmp_path / "transcripts"
    passed = asyncio.run(run_cases([case], provider, settings(), factory, diagnostic_attempts=3, output_dir=output_dir))
    assert passed is (replies[0] == "expected")
    assert len(factory.created) == len(replies)
    assert all(sandbox.closed for sandbox in factory.created)
    assert all(sum(message["role"] == "user" for message in request) == 1 for request in provider.requests)
    log = capsys.readouterr().out
    assert log.count("## Turn 1") == sum(reply != "expected" for reply in replies)
    for attempt, reply in enumerate(replies, start=1):
        assert f"Attempt {attempt}:" in log
        assert f"| case | {attempt} | {'PASS' if reply == 'expected' else 'FAIL'} |" in log
    assert f"| case | {sum(reply != 'expected' for reply in replies)}/{len(replies)} |" in log
    transcripts = sorted((output_dir / "case").glob("attempt-*.md"))
    assert len(transcripts) == len(replies)
    for path, reply in zip(transcripts, replies, strict=True):
        assert reply in path.read_text(encoding="utf-8")


def test_parallel_repetitions_bound_concurrency_and_retain_failed_attempts(tmp_path, monkeypatch):
    from tests.ai import runner

    case = definition(tmp_path, "steps: [{user: hi}]")
    paths = []
    active = peak = 0

    async def exercise():
        release = asyncio.Event()
        running = set()

        async def attempt(case, *args, transcript_path, **kwargs):
            nonlocal active, peak
            assert kwargs["judge_attempts"] == 3
            repetition = transcript_path.parent.name
            assert repetition not in running
            running.add(repetition)
            active += 1
            peak = max(peak, active)
            if active == 4:
                release.set()
            await release.wait()
            await asyncio.sleep(0)
            paths.append(transcript_path)
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text("Conversation\n", encoding="utf-8")
            running.remove(repetition)
            active -= 1
            return repetition != "run-2" or transcript_path.name != "attempt-1.md"

        monkeypatch.setattr(runner, "run_case", attempt)
        return await asyncio.wait_for(
            run_cases([case], None, settings(), None, diagnostic_attempts=3, jobs=4, repeat=12, output_dir=tmp_path),
            timeout=5,
        )

    assert not asyncio.run(exercise())
    assert peak == 4 and active == 0
    assert len(paths) == len(set(paths)) == 14
    assert len({path.parent for path in paths}) == 12
    assert len(list((tmp_path / "case" / "run-2").glob("attempt-*.md"))) == 3


@pytest.mark.parametrize(
    ("limit", "requested", "repeat", "expected"),
    [(4, None, 12, 4), (8, 2, 12, 2), (40, None, 30, 20), (0, None, 12, None)],
)
def test_cli_discovers_capacity_and_bounds_parallel_repetitions(
    tmp_path, monkeypatch, limit, requested, repeat, expected
):
    from nurse_scheduling.ai.litellm_concurrency import ProviderCapacity
    from tests.ai import runner

    case = definition(tmp_path, "steps: [{user: hi}]")
    monkeypatch.setattr(AiSettings, "from_env", settings)
    monkeypatch.setattr(runner, "TRANSCRIPTS", tmp_path / "transcripts")
    monkeypatch.setattr(runner, "create_sandbox_factory", lambda *_: FakeSandboxFactory())
    calls = []

    def discover(*args):
        assert args == (settings().provider_base_url, settings().provider_api_key, settings().provider_model)
        return ProviderCapacity("test", (), limit, "test capacity")

    async def execute(*args, jobs, repeat, **kwargs):
        calls.append((jobs, repeat))
        return True

    monkeypatch.setattr(runner, "discover_capacity", discover)
    monkeypatch.setattr(runner, "run_cases", execute)
    argv = ["run", str(case.path), "--repeat", str(repeat)]
    if requested is not None:
        argv += ["--jobs", str(requested)]
    assert main(argv) == (0 if expected else 2)
    assert calls == ([(expected, repeat)] if expected else [])
    reports = list((tmp_path / "transcripts").glob("*/concurrency.json"))
    if expected:
        assert json.loads(reports[0].read_text(encoding="utf-8"))["jobs"] == expected
    else:
        assert not reports


@pytest.mark.parametrize("passed", [True, False], ids=["passing-summary", "failed-conversation"])
def test_save_all_conversations_and_print_only_failures(tmp_path, capsys, passed):
    from nurse_scheduling.ai.provider import ReasoningDelta

    case = definition(
        tmp_path,
        "steps: [{user: Read the people.}, {user: Thanks.}, {assistant: {contains_any: ["
        + ("welcome" if passed else "missing")
        + "]}}]",
    )
    provider = ScriptedProvider(
        [
            [ReasoningDelta("Inspect the schedule."), tool_call("r", "read", json.dumps({"path": WORKSPACE_SCHEDULE}))],
            [TextDelta("No people."), ResponseEnd("stop")],
            [TextDelta("You're welcome."), ResponseEnd("stop")],
        ]
    )
    transcript = tmp_path / "transcripts" / "attempt-1.md"
    assert asyncio.run(run_case(case, provider, settings(), FakeSandboxFactory(), transcript_path=transcript)) is passed
    saved = transcript.read_text(encoding="utf-8")
    assert all(
        text in saved
        for text in [
            "Read the people.",
            "Inspect the schedule.",
            "You're welcome.",
            "Schedule before",
            "Schedule after",
        ]
    )
    assert ("# case.yaml: PASS" if passed else "# case.yaml: FAIL") in saved
    log = capsys.readouterr().out
    if passed:
        assert log == f"PASS {case.path} (2 turns); transcript: {transcript}\n"
        return
    assert log.count("## Turn ") == 2
    assert all(
        text in log
        for text in [
            "Read the people.",
            "Inspect the schedule.",
            "No people.",
            "Thanks.",
            "You're welcome.",
            "Tool Result",
            "people:",
            "Schedule before",
            "Schedule after",
        ]
    )
    assert str(transcript) in log


@pytest.mark.parametrize(
    ("reply", "verdict", "expected"),
    [("你好！可以協助您排班。", True, True), ("English reply.", False, False), ("", True, False)],
)
def test_judge_only_assistant_assertions(tmp_path, reply, verdict, expected):
    case = definition(tmp_path, "steps: [{user: hi}, {assistant: {judge: Reply in Traditional Chinese.}}]")
    provider = ScriptedProvider([[TextDelta(reply), ResponseEnd("stop")]])
    judge = ScriptedProvider(
        [[TextDelta(json.dumps({"passed": verdict, "reason": "Language checked."})), ResponseEnd("stop")]]
    )
    assert asyncio.run(run_case(case, provider, settings(), FakeSandboxFactory(), judge_provider=judge)) is expected
    assert len(judge.requests) == 1


@pytest.mark.parametrize(
    "assertion", ["{}", "{judge: '', case_sensitive: true}", "{judge: Reply in English., case_sensitive: false}"]
)
def test_invalid_judge_only_assertions(tmp_path, assertion):
    with pytest.raises(DefinitionError):
        definition(tmp_path, "steps: [{user: hi}, {assistant: " + assertion + "}]")


@pytest.mark.parametrize("rubric", ["", None, True, {"contains": "here"}], ids=["empty", "null", "boolean", "mapping"])
def test_invalid_judge_rubrics_fail_without_credentials(tmp_path, rubric):
    text = json.dumps({"steps": [{"user": "hi"}, {"assistant": {"contains_any": ["hi"], "judge": rubric}}]})
    with pytest.raises(DefinitionError, match="judge must be a nonempty rubric"):
        definition(tmp_path, text)


@pytest.mark.parametrize("count", [True, False, 0, -1, 1.5, "12", [], {}])
def test_invalid_judge_point_counts(tmp_path, count):
    text = json.dumps({"steps": [{"user": "hi"}, {"assistant": {"judge": "Cover both points.", "count": count}}]})
    with pytest.raises(DefinitionError, match="count must be a positive integer or null"):
        definition(tmp_path, text)


@pytest.mark.parametrize("count", [None, 2])
def test_judge_point_count_requires_judge(tmp_path, count):
    text = json.dumps({"steps": [{"user": "hi"}, {"assistant": {"contains_any": ["hi"], "count": count}}]})
    with pytest.raises(DefinitionError, match="count requires judge"):
        definition(tmp_path, text)


@pytest.mark.parametrize("count", [None, 12])
def test_judge_point_count_reports_missing_points_in_transcript(tmp_path, count):
    rubric = "Ask for the scheduling information."
    case = definition(
        tmp_path,
        json.dumps({"steps": [{"user": "hi"}, {"assistant": {"judge": rubric, "count": count}}]}),
    )
    reason = "10/12. Points (3) and (4) are missing." if count else "Scheduling information is missing."
    provider = ScriptedProvider([[TextDelta("What dates should I schedule?"), ResponseEnd("stop")]])
    judge = ScriptedProvider([[TextDelta(json.dumps({"passed": False, "reason": reason})), ResponseEnd("stop")]])
    transcript = tmp_path / "attempt.md"
    assert not asyncio.run(
        run_case(case, provider, settings(), FakeSandboxFactory(), judge_provider=judge, transcript_path=transcript)
    )
    request = json.loads(judge.requests[0][1]["content"])
    if count is None:
        assert request["rubric"] == rubric
    else:
        assert "N/12" in request["rubric"]
        assert "omitted or incomplete point by number" in request["rubric"]
    assert reason in transcript.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("reply", "judge_pass", "expected"),
    [
        ("You're already here.", True, True),
        ("You already know the menu. Go to Experimental AI.", False, False),
        ("You're speaking to the AI assistant right now.", True, False),
        ("Go to Experimental AI.", False, False),
    ],
    ids=["both-pass", "term-only", "judge-only", "both-fail"],
)
def test_identity_requires_terms_and_judge_and_always_runs_judge(tmp_path, capsys, reply, judge_pass, expected):
    case = load_case(TESTCASES / "basics" / "01_already-in-ai-chat.yaml")
    provider = ScriptedProvider([[TextDelta(reply), ResponseEnd("stop")]])
    judge = ScriptedProvider(
        [[TextDelta(json.dumps({"passed": judge_pass, "reason": "Semantic verdict."})), ResponseEnd("stop")]]
    )
    transcript = tmp_path / "attempt-1.md"
    assert (
        asyncio.run(
            run_case(case, provider, settings(), FakeSandboxFactory(), judge_provider=judge, transcript_path=transcript)
        )
        is expected
    )
    saved = transcript.read_text(encoding="utf-8")
    assert f"Verdict: **{'PASS' if judge_pass else 'FAIL'}**" in saved
    assert "Semantic verdict." in saved and "Judge request:" in saved
    log = capsys.readouterr().out
    if expected:
        assert log == f"PASS {case.path} (1 turns); transcript: {transcript}\n"
    else:
        assert f"Verdict: **{'PASS' if judge_pass else 'FAIL'}**" in log
        assert case.steps[2].value["judge"] in log
        assert "Semantic verdict." in log and "Judge request:" in log
    assert len(judge.requests) == 1
    assert all("current-schedule.yaml" not in str(message) for message in judge.requests[0])
    assert any(reply in message.get("content", "") for message in judge.requests[0])
    if not judge_pass:
        assert "(judge): Semantic verdict." in log


@pytest.mark.parametrize(
    "response",
    [
        "not JSON",
        '{"passed": "true", "reason": "wrong type"}',
        '{"passed": true}',
        '{"passed": true, "reason": ""}',
        '{"passed": true, "reason": "ok", "extra": 1}',
    ],
    ids=["invalid-json", "string-boolean", "missing-reason", "empty-reason", "unknown-field"],
)
def test_malformed_judge_responses_fail_and_keep_raw_evidence(response):
    provider = ScriptedProvider([[TextDelta(response), ResponseEnd("stop")]])
    result = asyncio.run(evaluate(provider, "Clearly acknowledge current chat.", [], "judge-model"))
    assert result["passed"] is False and result["error"]
    assert result["response"] == response and result["model"] == "judge-model"


@pytest.mark.parametrize("failure", ["provider", "length", "missing-end", "tool"], ids=str)
def test_judge_execution_failures_never_pass(failure):
    class Provider:
        async def stream_events(self, messages):
            yield TextDelta('{"passed": true, "reason": "ok"}')
            if failure == "provider":
                raise RuntimeError("provider-secret connection failed")
            if failure == "length":
                yield ResponseEnd("length")
            if failure == "tool":
                yield tool_call("r", "read", "{}")

    result = asyncio.run(evaluate(Provider(), "Current chat.", [], "test"))
    assert result["passed"] is False and result["error"]
    assert result["response"]


@pytest.mark.parametrize(
    "verdicts",
    [[True], [False, True, True], [False, False, False], [None, True, False]],
    ids=["first-pass", "later-pass", "all-fail", "first-error"],
)
def test_judge_diagnostics_preserve_initial_failure_without_replaying_agent(tmp_path, verdicts):
    case = definition(tmp_path, "steps: [{user: hi}, {assistant: {judge: Reply in English.}}]")
    provider = ScriptedProvider([[TextDelta("Hello."), ResponseEnd("stop")]])
    judge = ScriptedProvider(
        [
            [
                TextDelta("invalid" if passed is None else json.dumps({"passed": passed, "reason": "Checked."})),
                ResponseEnd("stop"),
            ]
            for passed in verdicts
        ]
    )
    transcript = tmp_path / "conversation.md"
    assert asyncio.run(
        run_case(
            case,
            provider,
            settings(),
            FakeSandboxFactory(),
            judge_provider=judge,
            judge_attempts=3,
            transcript_path=transcript,
        )
    ) is (verdicts[0] is True)
    assert len(provider.requests) == 1
    assert len(judge.requests) == len(verdicts)
    assert all(request == judge.requests[0] for request in judge.requests)
    saved = transcript.read_text(encoding="utf-8")
    assert saved.count("### Judge\n") == len(verdicts)
    for attempt, passed in enumerate(verdicts, 1):
        assert f"Judge attempt: {attempt}." in saved
        if passed is not True:
            assert f"(judge): attempt {attempt}:" in saved


def test_judge_still_runs_when_agent_execution_fails(capsys):
    case = load_case(TESTCASES / "basics" / "01_already-in-ai-chat.yaml")
    provider = ScriptedProvider([[TextDelta("Partial reply."), ResponseEnd("length")]])
    judge = ScriptedProvider(
        [[TextDelta('{"passed": false, "reason": "Incomplete acknowledgement."}'), ResponseEnd("stop")]]
    )
    assert not asyncio.run(run_case(case, provider, settings(), FakeSandboxFactory(), judge_provider=judge))
    log = capsys.readouterr().out
    assert "(execution):" in log and "Partial reply." in log
    assert "Verdict: **FAIL**" in log
    assert len(judge.requests) == 1


def test_judge_timeout_keeps_partial_reply_and_closes_stream(monkeypatch):
    from tests.ai import judge

    monkeypatch.setattr(judge, "TIMEOUT_SECONDS", 0.01)

    class Provider:
        closed = False

        async def stream_events(self, messages):
            try:
                yield TextDelta("partial verdict")
                await asyncio.Event().wait()
            finally:
                self.closed = True

    provider = Provider()
    result = asyncio.run(evaluate(provider, "Current chat.", [], "test"))
    assert result["passed"] is False and result["error"].startswith("TimeoutError:")
    assert result["response"] == "partial verdict" and provider.closed


def test_cli_run_saves_successful_conversation_by_default(tmp_path, monkeypatch, capsys):
    from tests.ai import runner

    case = definition(tmp_path, "steps: [{user: hi}]")
    provider = ScriptedProvider([[TextDelta("Successful local reply."), ResponseEnd("stop")]])
    output_dir = tmp_path / "transcripts"
    from nurse_scheduling.ai.litellm_concurrency import ProviderCapacity

    monkeypatch.setattr(runner, "discover_capacity", lambda *_: ProviderCapacity("test", (), 4, "test capacity"))
    monkeypatch.setattr(runner, "TRANSCRIPTS", output_dir)
    monkeypatch.setattr(AiSettings, "from_env", settings)
    monkeypatch.setattr(runner, "OpenAiCompatibleProvider", lambda *args, **kwargs: provider)
    monkeypatch.setattr(runner, "create_sandbox_factory", lambda *_: FakeSandboxFactory())
    assert main(["run", str(case.path)]) == 0
    transcripts = list(output_dir.glob("*/case/attempt-1.md"))
    assert len(transcripts) == 1
    assert "Successful local reply." in transcripts[0].read_text(encoding="utf-8")
    log = capsys.readouterr().out
    assert str(transcripts[0]) in log and "Successful local reply." not in log
