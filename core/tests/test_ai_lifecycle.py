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


@pytest.mark.parametrize("decision", ["reject", "stale-approval"])
def test_discarding_a_proposal_revokes_a_turn_that_was_using_it(decision):
    store = SessionStore(make_settings())
    session = store.create("owner", schedule_yaml())
    first = store.begin(session.id, "owner")
    proposal = (schedule_yaml() + "\n", "proposal diff")
    assert store.finish(session.id, "Edit", "Proposal", proposal, snapshot=first).proposal_saved
    revising = store.begin(session.id, "owner")
    if decision == "reject":
        store.discard_proposal(session.id, "owner")
    else:
        with pytest.raises(HTTPException) as stale:
            store.adopt_proposal(session.id, "owner", "0" * 64)
        assert stale.value.status_code == 409
    assert not store.finish(session.id, "Revise", "Revised", proposal, snapshot=revising).turn_saved
    assert session.proposal_yaml == ""


@pytest.mark.parametrize("background", [False, True], ids=["foreground", "background"])
def test_stop_during_recovery_admission_waits_for_the_write_and_skips_execution(monkeypatch, background):
    from nurse_scheduling.ai.history import ChatHistory

    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        records = []

        async def write(_self, operation, *args):
            if operation == "start_recovery_turn":
                entered.set()
                await release.wait()
            records.append((operation, args))
            return True

        monkeypatch.setattr(ChatHistory, "write", write)
        provider = FakeProvider()
        app = create_test_app(settings=make_settings(history_postgres_url="test"), provider=provider)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=AI_AUTH_HEADERS
        ) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": schedule_yaml()})).json()["id"]
            if background:
                running = asyncio.create_task(app.state.session_optimizer._on_completion(session_id, "Review", None))
            else:
                running = asyncio.create_task(client.post(f"/sessions/{session_id}/messages", json={"message": "Ask"}))
            await asyncio.wait_for(entered.wait(), timeout=1)
            assert (await client.post(f"/sessions/{session_id}/stop")).status_code == 202
            assert (await client.post(f"/sessions/{session_id}/stop")).status_code == 202
            assert app.state.turns.busy(session_id)
            release.set()
            await asyncio.wait_for(asyncio.gather(running, return_exceptions=True), timeout=1)
            assert not app.state.turns.busy(session_id)
            assert not app.state.session_store._sessions[session_id].active
            assert provider.calls == []
            operations = [operation for operation, _ in records]
            assert operations.count("start_recovery_turn") == 1
            assert operations.count("finish_recovery_turn") == 1
            terminal = next(args for operation, args in records if operation == "finish_recovery_turn")
            assert terminal[6] == "stopped"

    asyncio.run(exercise())


def test_stop_during_completed_recovery_write_preserves_the_completed_outcome(monkeypatch):
    from nurse_scheduling.ai.history import ChatHistory

    async def exercise():
        finalizing, release = asyncio.Event(), asyncio.Event()
        terminals = []

        async def write(_self, operation, *args):
            if operation == "finish_recovery_turn":
                finalizing.set()
                await release.wait()
                terminals.append(args[6])
            return True

        async def read(_self, _operation, *_args):
            return None

        monkeypatch.setattr(ChatHistory, "write", write)
        monkeypatch.setattr(ChatHistory, "read", read)
        app = create_test_app(settings=make_settings(history_postgres_url="test"), provider=FakeProvider())
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=AI_AUTH_HEADERS
        ) as client:
            session_id = (await client.post("/sessions", json={"schedule_yaml": schedule_yaml()})).json()["id"]
            running = asyncio.create_task(client.post(f"/sessions/{session_id}/messages", json={"message": "Ask"}))
            await asyncio.wait_for(finalizing.wait(), timeout=1)
            assert app.state.turns.busy(session_id)
            assert (await client.post(f"/sessions/{session_id}/stop")).status_code == 202
            assert (await client.post(f"/sessions/{session_id}/stop")).status_code == 202
            assert not running.done()
            assert (await client.post(f"/sessions/{session_id}/messages", json={"message": "Next"})).status_code == 409
            release.set()
            response = await asyncio.wait_for(running, timeout=1)
            assert "event: done" in response.text
            assert "event: stopped" not in response.text
            assert terminals == ["done"]
            assert not app.state.turns.busy(session_id)

    asyncio.run(exercise())


def test_retirement_during_an_event_write_does_not_recreate_replay_state():
    from nurse_scheduling.ai.background import SessionEventBroker

    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        broker = SessionEventBroker()

        async def write(*_args):
            entered.set()
            await release.wait()

        broker.on_publish = write
        publishing = asyncio.create_task(broker.emit("session", "delta", {"text": "old output"}))
        await asyncio.wait_for(entered.wait(), timeout=1)
        queued = asyncio.create_task(broker.emit("session", "done", {"message_id": "old turn"}))
        await asyncio.sleep(0)
        broker.forget_session("session")
        release.set()
        await asyncio.wait_for(asyncio.gather(publishing, queued), timeout=1)
        assert broker.events_after("session") == ()
        assert "session" not in broker._signals
        assert "session" not in broker._publish_locks

    asyncio.run(exercise())
