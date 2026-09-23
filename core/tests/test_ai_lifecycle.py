"""Replayable events and agent turns triggered by background work."""

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

import httpx
import pytest
from fastapi import HTTPException

from nurse_scheduling.ai.app import SessionStore
from nurse_scheduling.ai.lifecycle import SessionTurns

from .ai_test_helper import schedule_yaml
from .test_ai_basic import AI_AUTH_HEADERS, FakeProvider, create_test_app, make_settings


def test_setup_failure_releases_admission_and_the_next_request_can_run(monkeypatch):
    async def exercise():
        app = create_test_app(settings=make_settings(), provider=FakeProvider())
        original = app.state.session_optimizer.latest_result_artifact

        async def fail(_session_id):
            raise RuntimeError("artifact setup failed")

        monkeypatch.setattr(app.state.session_optimizer, "latest_result_artifact", fail)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=AI_AUTH_HEADERS
        ) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": schedule_yaml()})).json()["id"]
            response = await client.post(f"/sessions/{session_id}/messages", json={"message": "Question"})
            assert "event: error" in response.text
            assert not app.state.turns.busy(session_id)
            assert not app.state.session_store._sessions[session_id].active
            monkeypatch.setattr(app.state.session_optimizer, "latest_result_artifact", original)
            response = await client.post(f"/sessions/{session_id}/messages", json={"message": "Retry"})
            assert "event: done" in response.text

    asyncio.run(exercise())


def test_retirement_cancels_the_owner_and_queued_followups_without_recreating_events():
    async def exercise():
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class Provider:
            async def stream_events(self, _messages, tools=None):
                try:
                    started.set()
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
                yield

        app = create_test_app(settings=make_settings(), provider=Provider())
        store = app.state.session_store
        session = store.create("owner", schedule_yaml())
        callback = app.state.session_optimizer._on_completion
        active = asyncio.create_task(callback(session.id, "Review", None))
        await started.wait()
        queued = asyncio.create_task(callback(session.id, "Another result", None))
        await asyncio.sleep(0)
        session.expires_at = 0
        with pytest.raises(HTTPException):
            store.require_owned(session.id, "owner")
        await asyncio.gather(active, queued, return_exceptions=True)
        assert cancelled.is_set()
        assert not app.state.turns.busy(session.id)
        assert app.state.session_event_broker.events_after(session.id) == ()
        assert session.id not in app.state.session_event_broker._signals

    asyncio.run(exercise())


def test_cancelling_a_queued_turn_does_not_let_its_successor_overtake_the_owner():
    async def exercise():
        turns = SessionTurns()
        release = asyncio.Event()
        started = []

        async def first(_turn):
            started.append("first")
            await release.wait()

        async def queued(turn):
            started.append(turn.id)

        first_turn = turns.start("session", first)
        middle = turns.start("session", queued, background=True)
        last = turns.start("session", queued, background=True)
        await asyncio.sleep(0)
        middle.cancel()
        await middle.done
        await asyncio.sleep(0)
        assert started == ["first"]
        release.set()
        await last.wait()
        await first_turn.wait()
        assert started == ["first", last.id]
        assert not turns.busy("session")
        await turns.close()

    asyncio.run(exercise())


def test_stop_is_idempotent_through_cleanup_and_cancels_all_admitted_turns():
    async def exercise():
        turns = SessionTurns()
        started = asyncio.Event()
        cleaning = asyncio.Event()
        release = asyncio.Event()
        queued_ran = False

        async def run(_turn):
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()

        async def queued(_turn):
            nonlocal queued_ran
            queued_ran = True

        active = turns.start("session", run)
        waiting = turns.start("session", queued, background=True)
        await started.wait()
        turns.stop("session")
        await cleaning.wait()
        turns.stop("session")
        assert turns.busy("session")
        with pytest.raises(HTTPException) as conflict:
            turns.start("session", queued)
        assert conflict.value.status_code == 409
        release.set()
        await asyncio.gather(active.done, waiting.done)
        assert not queued_ran
        assert not turns.busy("session")
        # A later optimizer completion is a new operation and may wake the agent.
        await turns.start("session", queued, background=True).wait()
        assert queued_ran
        await turns.close()

    asyncio.run(exercise())


def test_shutdown_joins_cleanup_and_closes_admission():
    async def exercise():
        turns = SessionTurns()
        started = asyncio.Event()
        cleaning = asyncio.Event()
        release = asyncio.Event()

        async def run(_turn):
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                cleaning.set()
                await release.wait()

        turns.start("session", run)
        await started.wait()
        closing = asyncio.create_task(turns.close())
        await cleaning.wait()
        assert not closing.done()
        with pytest.raises(HTTPException) as unavailable:
            turns.start("other", run)
        assert unavailable.value.status_code == 503
        release.set()
        await closing
        assert turns._turns == {}

    asyncio.run(exercise())


def test_stale_turn_cannot_release_or_commit_over_its_successor():
    store = SessionStore(make_settings())
    session = store.create("owner", schedule_yaml())
    old = store.begin(session.id, "owner")
    store.abort(session.id, old)
    new = store.begin(session.id, "owner")
    assert not store.finish(session.id, "old", "old", snapshot=old).turn_saved
    store.abort(session.id, old)
    assert session.turn is new
    assert store.finish(session.id, "new", "new", snapshot=new).turn_saved
    assert [message["content"] for message in session.history] == ["new", "new"]


def test_schedule_round_trip_invalidates_an_in_flight_snapshot():
    store = SessionStore(make_settings())
    original = schedule_yaml()
    session = store.create("owner", original)
    turn = store.begin(session.id, "owner")
    store.update_schedule(session.id, "owner", original + "\n")
    store.update_schedule(session.id, "owner", original)
    assert not store.finish(session.id, "question", "answer", snapshot=turn).turn_saved
    assert session.history == []
