"""Check ordered, timely publication of projected agent output."""

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

from nurse_scheduling.ai.session_event_projection import RunEvents
from nurse_scheduling.ai.session_events import AgentSessionEvent


def test_batched_output_keeps_reasoning_text_tools_and_terminal_in_order() -> None:
    async def scenario() -> None:
        published: list[AgentSessionEvent] = []
        events = RunEvents("run", published.append)
        events.emit({"type": "reasoning", "text": "Check "})
        events.emit({"type": "reasoning", "text": "Monday."})
        events.emit({"type": "delta", "text": "Reading."})
        events.emit({"type": "tool_start", "tool_call_id": "call", "name": "read", "arguments": "{}"})
        events.emit({"type": "delta", "text": "Partial answer."})
        events.emit({"type": "stopped"})

        assert published == [
            {"type": "reasoning", "text": "Check Monday.", "run_id": "run"},
            {"type": "delta", "text": "Reading.", "run_id": "run"},
            {"type": "tool_start", "tool_call_id": "call", "name": "read", "arguments": "{}", "run_id": "run"},
        ]
        events.finish()
        assert published[-2:] == [
            {"type": "delta", "text": "Partial answer.", "run_id": "run"},
            {"type": "stopped", "run_id": "run"},
        ]
        events.finish()
        assert len(published) == 5

    asyncio.run(scenario())


def test_partial_text_is_published_while_the_run_is_still_waiting() -> None:
    async def scenario() -> None:
        received = asyncio.Event()
        published: list[AgentSessionEvent] = []

        def publish(event: AgentSessionEvent) -> None:
            published.append(event)
            received.set()

        events = RunEvents("run", publish)
        events.emit({"type": "delta", "text": "Still working."})
        await asyncio.wait_for(received.wait(), timeout=1)
        assert published == [{"type": "delta", "text": "Still working.", "run_id": "run"}]

        events.emit({"type": "done"})
        assert len(published) == 1
        events.finish()
        assert published[-1] == {"type": "done", "run_id": "run"}

    asyncio.run(scenario())
