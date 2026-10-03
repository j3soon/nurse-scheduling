"""Tests for bounded session event replay and recovery."""

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

from nurse_scheduling.ai.session_event_stream import SessionEventStream


def test_replay_gap_recovers_text_and_tool_identity():
    async def scenario():
        stream = SessionEventStream(max_events_per_session=2)
        for text in ["one", "two", "three"]:
            stream.publish("s", "delta", {"run_id": "r", "text": text})
        stream.publish("s", "tool", {"run_id": "r", "tool_call_id": "t", "result": "read"})
        reader = stream.stream("s", 0)
        reset = await anext(reader)
        assert reset.type == "session_reset"
        assert reset.id == 4
        assert reset.data["events"][0]["data"]["text"] == "onetwothree"
        assert reset.data["events"][1]["data"]["tool_call_id"] == "t"
        assert not reset.data["incomplete"]
        await reader.aclose()

    asyncio.run(scenario())


def test_progress_replacement_does_not_create_a_required_replay_gap():
    async def scenario():
        stream = SessionEventStream()
        stream.publish("s", "run_start", {"run_id": "r"})
        for score in range(10):
            stream.publish("s", "optimization_progress", {"job_id": "j", "score": score})
        stream.publish("s", "done", {"run_id": "r"})
        reader = stream.stream("s", 1)
        progress = await anext(reader)
        assert progress.type == "optimization_progress"
        assert progress.data["score"] == 9
        assert (await anext(reader)).type == "done"
        await reader.aclose()

    asyncio.run(scenario())


def test_serialized_byte_limits_include_multibyte_payloads_and_recovery():
    stream = SessionEventStream(max_bytes_per_session=200, max_total_bytes=300)
    for session in ["a", "b"]:
        stream.publish(session, "delta", {"run_id": session, "text": "護" * 30})
        stream.publish(session, "done", {"run_id": session})
    assert stream._retained_bytes <= 300
    for replay in stream._sessions.values():
        assert sum(event.bytes for event in replay.events) <= 200
        assert sum(event.bytes for event in replay.recovery) <= 200
    stream.forget_session("a")
    stream.forget_session("b")
    assert stream._retained_bytes == 0


def test_slow_subscriber_receives_reset_after_critical_events_expire():
    async def scenario():
        stream = SessionEventStream(max_events_per_session=2)
        stream.publish("s", "run_start", {"run_id": "r"})
        reader = stream.stream("s", 0)
        assert (await anext(reader)).type == "run_start"
        for number in range(5):
            stream.publish("s", "tool", {"run_id": "r", "tool_call_id": str(number)})
        stream.publish("s", "done", {"run_id": "r"})
        reset = await anext(reader)
        assert reset.type == "session_reset"
        assert reset.data["incomplete"]
        assert reset.data["events"][-1]["type"] == "done"
        await reader.aclose()

    asyncio.run(scenario())


def test_replay_pressure_prefers_completed_output_over_an_active_run():
    stream = SessionEventStream(max_events_per_session=4)
    stream.publish("s", "run_start", {"run_id": "old"})
    stream.publish("s", "delta", {"run_id": "old", "text": "old answer"})
    stream.publish("s", "done", {"run_id": "old"})
    stream.publish("s", "run_start", {"run_id": "new"})
    stream.publish("s", "tool_start", {"run_id": "new", "tool_call_id": "t"})
    events = stream.events_after("s")
    assert any(e.type == "tool_start" for e in events)
    assert any(e.type == "done" for e in events)
