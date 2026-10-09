"""Tests for typed conversation retention and provider context."""

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

import pytest

from nurse_scheduling.ai.context import (
    ABORTED_RESPONSE_HISTORY,
    PROPOSAL_APPROVED_HISTORY,
    SCHEDULE_CHANGED_EVENT,
    build_provider_messages,
    cap_transcript,
    entries_from_legacy_history,
    history_chars,
    interrupted_entries,
    prepare_provider_request,
    project_history,
    projected_history,
    retained_entries,
)
from nurse_scheduling.ai.sessions import SessionStore
from nurse_scheduling.ai.transcript import (
    AppEventEntry,
    AssistantMessage,
    ProposalDecisionEntry,
    ToolCall,
    ToolResultImage,
    ToolResultMessage,
    UserMessage,
    entry_from_record,
    entry_record,
)

from .test_ai_basic import make_settings, schedule_yaml


@pytest.mark.parametrize("reason", ["aborted", "error"])
def test_interrupted_run_preserves_questions_and_steering_without_discarded_claims(reason):
    entries = interrupted_entries(
        [
            UserMessage("Edit P1"),
            AssistantMessage("Changed P1"),
            UserMessage("Also P2"),
            AssistantMessage("Changed P2"),
        ],
        reason,
    )
    assert projected_history(retained_entries(entries)) == [
        {"role": "user", "content": "Edit P1"},
        {"role": "assistant", "content": ABORTED_RESPONSE_HISTORY},
        {"role": "user", "content": "Also P2"},
        {"role": "assistant", "content": ABORTED_RESPONSE_HISTORY},
    ]


def test_later_context_joins_responses_and_excludes_reasoning_tools_and_images():
    call = ToolCall("read-1", "read", "{}")
    entries = [
        UserMessage("Read it"),
        AssistantMessage("Checking. ", "tool_use", "private reasoning", (call,)),
        ToolResultMessage(call.id, call.name, "large tool result", True, ToolResultImage("image/png", b"image")),
        AssistantMessage("Done."),
    ]
    retained = retained_entries(entries)
    assert retained == [UserMessage("Read it"), AssistantMessage("Checking. ", "tool_use"), AssistantMessage("Done.")]
    assert projected_history(retained) == [
        {"role": "user", "content": "Read it"},
        {"role": "assistant", "content": "Checking. Done."},
    ]


def test_provider_receives_all_tool_replies_before_images_and_steering():
    calls = (ToolCall("one", "read", "{}"), ToolCall("two", "read", "{}"))
    entries = [AssistantMessage("", "tool_use", tool_calls=calls)]
    entries.extend(
        ToolResultMessage(call.id, call.name, call.id, True, ToolResultImage("image/png", b"x")) for call in calls
    )
    entries.append(UserMessage("Now compare them"))
    request = prepare_provider_request([], entries)
    assert [message["role"] for message in request] == ["assistant", "tool", "tool", "user", "user", "user"]
    assert [message["tool_call_id"] for message in request[1:3]] == ["one", "two"]
    assert request[-1]["content"] == "Now compare them"
    assert all(message["content"][-1]["type"] == "image_url" for message in request[3:5])


@pytest.mark.parametrize("tail", [AssistantMessage("orphan answer"), ProposalDecisionEntry("approved")])
def test_history_budget_drops_an_answer_or_decision_without_its_prompt(tail):
    entries = [UserMessage("q" * 300), tail]
    selected = project_history(entries, history_chars(projected_history([tail])))
    assert selected.messages == []
    assert selected.used_chars == 0
    assert selected.dropped_messages == 2


def test_history_budget_starts_at_an_app_event_and_counts_serialized_unicode():
    entries = [
        UserMessage("old"),
        AssistantMessage("old answer"),
        AppEventEntry(SCHEDULE_CHANGED_EVENT),
        UserMessage("新問題"),
    ]
    expected = projected_history(entries[2:])
    selected = project_history(entries, history_chars(expected))
    assert selected.messages == expected
    assert selected.used_chars == history_chars(expected)
    assert selected.dropped_messages == 2


def test_retention_keeps_the_whole_newest_run_including_steering():
    newest = [UserMessage("edit"), AssistantMessage("first"), UserMessage("steer"), AssistantMessage("last")]
    transcript = [UserMessage("old"), AssistantMessage("old answer"), ProposalDecisionEntry("rejected"), *newest]
    assert cap_transcript(transcript, 2, 1, len(newest)) == 3
    assert transcript == newest


def test_legacy_recovery_preserves_the_next_provider_request_after_decisions_and_failure():
    store = SessionStore(make_settings())
    session = store.create("owner", schedule_yaml())
    snapshot = store.begin(session.id, "owner")
    entries = [
        UserMessage("Change it"),
        AssistantMessage("Proposal"),
        ProposalDecisionEntry("approved"),
        UserMessage("Next"),
        AssistantMessage("Provisional", "error"),
    ]
    store.finish(session.id, entries, snapshot=snapshot)
    expected = build_provider_messages(project_history(session.transcript), session.schedule_yaml, "Retry")
    owner, expires, state = store.recovery_state(session.id)
    assert set(state) == {"schedule_yaml", "pending_proposal", "dropped_history_messages", "dropped_entries"}
    records = [entry_record(entry) for entry in session.transcript]
    assert ("proposal_decision", {"decision": "approved"}) in records
    recovered = SessionStore(make_settings())
    recovered.restore(
        session.id,
        owner,
        state,
        expires,
        entries=[entry_from_record(*entry_record(entry)) for entry in session.transcript],
        next_entry_seq=session.next_entry_seq,
    )
    restored = recovered._sessions[session.id]
    assert build_provider_messages(project_history(restored.transcript), restored.schedule_yaml, "Retry") == expected
    assert entries == restored.transcript


@pytest.mark.parametrize(
    "question",
    [PROPOSAL_APPROVED_HISTORY, SCHEDULE_CHANGED_EVENT, "Ordinary question"],
    ids=["decision-text", "app-event-text", "ordinary"],
)
def test_typed_recovery_preserves_user_origin_and_interrupted_output(question):
    store = SessionStore(make_settings())
    session = store.create("owner", schedule_yaml())
    snapshot = store.begin(session.id, "owner")
    entries = [UserMessage(question), AssistantMessage("Discarded edit claim", "error")]
    store.finish(session.id, entries, snapshot=snapshot)
    owner, expires, state = store.recovery_state(session.id)
    recovered = SessionStore(make_settings())
    recovered.restore(
        session.id,
        owner,
        state,
        expires,
        entries=[entry_from_record(*entry_record(entry)) for entry in session.transcript],
        next_entry_seq=session.next_entry_seq,
    )
    restored = recovered._sessions[session.id]
    assert restored.transcript == entries
    assert restored.history == session.history
    assert recovered._session_bytes[session.id] == store._session_bytes[session.id]


def test_typed_entry_storage_preserves_tool_calls_and_excludes_image_bytes():
    import json

    call = ToolCall("read-1", "read", '{"path":"schedule.yaml"}')
    entries = [
        UserMessage("Question"),
        AssistantMessage("Checking", "tool_use", "Reasoning", (call,)),
        ToolResultMessage(call.id, call.name, "Result", True, ToolResultImage("image/png", b"private bytes")),
        ProposalDecisionEntry("approved"),
        AppEventEntry("Upload event"),
    ]
    records = json.loads(json.dumps([entry_record(entry) for entry in entries]))
    assert "private bytes" not in repr(records)
    assert [entry_from_record(kind, payload) for kind, payload in records] == [
        *entries[:2],
        ToolResultMessage(call.id, call.name, "Result", True),
        *entries[3:],
    ]


def test_legacy_text_history_converts_to_typed_entries():
    legacy = [{"role": "user", "content": "Question"}, {"role": "assistant", "content": "Answer"}]
    assert entries_from_legacy_history(legacy) == [UserMessage("Question"), AssistantMessage("Answer")]


def test_retained_byte_budget_counts_partial_text_hidden_from_model_context():
    store = SessionStore(make_settings(max_session_bytes=1000))
    session = store.create("owner", "schedule")
    snapshot = store.begin(session.id, "owner")
    store.finish(
        session.id,
        [UserMessage("q"), AssistantMessage("新" * 2000, "aborted")],
        snapshot=snapshot,
    )
    assert store.retained_bytes == len(b"scheduleq") + len(("新" * 2000).encode())
    assert session.history[-1]["content"] == ABORTED_RESPONSE_HISTORY
    # A later exchange releases the oversized failed turn and its accounted bytes.
    store.finish(session.id, [UserMessage("next"), AssistantMessage("done")], snapshot=store.begin(session.id, "owner"))
    assert store.retained_bytes == len(b"schedulenextdone")
