"""Reconnect, retried message, and named Stop checks for AI chat sessions."""

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
import time
from typing import Any, cast

import httpx

from nurse_scheduling.ai.provider import TextDelta
from nurse_scheduling.ai.session_event_stream import RESTORE_CURSOR_GAP, SessionEvent, SessionEventStream
from nurse_scheduling.ai.transcript import UserMessage

from . import test_ai_basic as basic

JSON_HEADERS = {"Accept": "application/json"}


def test_repeated_message_id_after_lost_acknowledgement_does_not_repeat_the_question():
    provider = basic.FakeProvider([["Saved answer"], ["Duplicate answer"]])
    app = basic.create_test_app(settings=basic.make_settings(), provider=provider)
    with basic.AuthenticatedTestClient(app, headers=JSON_HEADERS) as client:
        session = basic.create_session(client)
        request = {"message": "Original question", "message_id": "client-message"}
        first = client.post(f"/sessions/{session}/messages", json=request)
        while app.state.runs.busy(session):
            time.sleep(0.01)
        repeated = client.post(f"/sessions/{session}/messages", json=request)
        changed = client.post(f"/sessions/{session}/messages", json={**request, "message": "Another question"})
    assert first.status_code == repeated.status_code == 202
    assert repeated.json() == first.json()
    assert changed.status_code == 409
    assert len(provider.calls) == 1
    transcript = app.state.session_store._sessions[session].transcript
    assert transcript.count(UserMessage("Original question")) == 1


def test_stop_before_message_arrives_prevents_provider_execution():
    provider = basic.FakeProvider([["This must not be sent"]])
    app = basic.create_test_app(settings=basic.make_settings(), provider=provider)
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        request = {"message": "Original question", "message_id": "stopped-request"}
        assert client.post(f"/sessions/{session}/stop", json={"message_id": request["message_id"]}).status_code == 202
        result = client.post(f"/sessions/{session}/messages", json=request)
        assert basic.parse_sse(result.text)[-1][0] == "stopped"
        assert provider.calls == []
        # The question never ran, so later context does not include it.
        assert app.state.session_store._sessions[session].transcript == []


def test_stop_before_an_accepted_run_begins_publishes_its_stopped_outcome():
    async def exercise():
        app = basic.create_test_app(settings=basic.make_settings(), provider=basic.FakeProvider([["Must not run"]]))
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers=basic.AI_AUTH_HEADERS,
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            session = app.state.session_store.get(session_id)
            published = []
            session.subscribe(published.append)
            accepting = asyncio.create_task(
                session.accept_message(
                    "Question",
                    None,
                    # The run never begins, so it never reads the runtime.
                    runtime=cast(Any, None),
                    runs=app.state.runs,
                    owner=session.owner_token,
                    credential_id=None,
                )
            )
            # The run task exists but has not begun when Stop arrives.
            await asyncio.sleep(0)
            await session.stop(None, runtime=cast(Any, None), runs=app.state.runs)
            return await accepting, published

    receipt, published = asyncio.run(exercise())
    assert receipt.run is None
    assert published == [{"type": "stopped", "run_id": receipt.run_id}]


def test_stop_for_an_earlier_message_leaves_the_active_run_running():
    async def exercise():
        started = asyncio.Event()
        release = asyncio.Event()

        class Provider:
            async def stream_events(self, _messages, tools=None):
                started.set()
                await release.wait()
                yield TextDelta("Current answer")

        app = basic.create_test_app(settings=basic.make_settings(), provider=Provider())
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers=basic.AI_AUTH_HEADERS,
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            run = asyncio.create_task(
                client.post(f"/sessions/{session_id}/messages", json={"message": "Current", "message_id": "current"})
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            stop = await client.post(f"/sessions/{session_id}/stop", json={"message_id": "earlier"})
            assert stop.status_code == 202
            release.set()
            response = await asyncio.wait_for(run, timeout=2)
            return basic.parse_sse(response.text)[-1][0]

    assert asyncio.run(exercise()) == "done"


def test_named_stop_cancels_its_own_active_run():
    async def exercise():
        started = asyncio.Event()

        class Provider:
            async def stream_events(self, _messages, tools=None):
                yield TextDelta("Partial")
                started.set()
                await asyncio.Event().wait()

        app = basic.create_test_app(settings=basic.make_settings(), provider=Provider())
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                headers=basic.AI_AUTH_HEADERS,
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            run = asyncio.create_task(
                client.post(f"/sessions/{session_id}/messages", json={"message": "Current", "message_id": "current"})
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            assert (
                await client.post(f"/sessions/{session_id}/stop", json={"message_id": "current"})
            ).status_code == 202
            response = await asyncio.wait_for(run, timeout=2)
            return basic.parse_sse(response.text)[-1][0]

    assert asyncio.run(exercise()) == "stopped"


def test_reset_recovers_all_text_after_more_than_one_thousand_fragments():
    async def exercise():
        stream = SessionEventStream()
        stream.publish("session", {"type": "run_start", "trigger": "user", "run_id": "run"})
        for text in ["First", *[" middle" for _ in range(1200)], " last"]:
            stream.publish("session", {"type": "delta", "text": text, "run_id": "run"})
        stream.publish("session", {"type": "done", "run_id": "run"})
        reader = stream.stream("session", 0)
        event = await anext(reader)
        await reader.aclose()
        return event

    event = asyncio.run(exercise())
    assert event.type == "session_reset"
    deltas = [item["data"]["text"] for item in event.data["events"] if item["type"] == "delta"]
    assert deltas == ["First" + " middle" * 1200 + " last"]
    assert event.data["events"][-1]["type"] == "done"
    assert event.data["incomplete"] is False


def test_restored_stream_replaces_output_for_a_cursor_ahead_of_storage():
    async def exercise():
        stream = SessionEventStream()
        requested = []

        async def load_recovery(session_id, after_id):
            requested.append(after_id)
            return stream.cursor(session_id), [SessionEvent(5, "delta", {"text": "Stored", "run_id": "run"})]

        stream.load_recovery = load_recovery
        stream.restore("session", 5)
        stream.publish("session", {"type": "error", "message": "Restarted", "run_id": "run"})
        # The browser saw two events of the previous process that storage never received.
        reader = stream.stream("session", 7)
        reset = await anext(reader)
        assert reset.type == "session_reset"
        assert reset.id == 5 + RESTORE_CURSOR_GAP + 1
        await reader.aclose()
        return requested, reset

    requested, reset = asyncio.run(exercise())
    # The newest stored run is replaced as well, since the browser may show more of it.
    assert requested == [4]
    assert reset.data == {
        "events": [{"id": 5, "type": "delta", "data": {"text": "Stored", "run_id": "run"}}],
        "incomplete": False,
    }
