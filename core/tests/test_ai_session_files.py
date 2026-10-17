"""Archive session files through removal, restart, and expiry."""

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
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from nurse_scheduling.ai.downloads import WORKSPACE_DOWNLOAD
from nurse_scheduling.ai.history import ChatHistory, _migrate_legacy_transcripts
from nurse_scheduling.ai.optimizer import OptimizerArtifact, OptimizerJobPayload, SessionOptimization
from nurse_scheduling.ai.provider import TextDelta, ToolCall, ToolCallRequest
from nurse_scheduling.ai.sandbox import CommandResult
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory
from nurse_scheduling.ai.sessions import SessionStore
from nurse_scheduling.ai.workspace import SandboxAttachment

from . import test_ai_basic as basic
from .test_ai_downloads import archive_bytes
from .test_ai_history import postgres_history, unavailable, uninitialized_postgres_history

__all__ = ["postgres_history", "uninitialized_postgres_history"]


@pytest.mark.parametrize("history_url", ["", "test"], ids=["memory", "postgres"])
def test_pending_downloads_share_the_retained_byte_budget(history_url):
    store = SessionStore(
        basic.make_settings(history_postgres_url=history_url, max_session_bytes=10_000, max_download_bytes=8000)
    )
    session = store.create(str(uuid4()), "schedule")
    assert store.save_download(session.id, "first", b"a" * 7000)
    retained = store.retained_bytes
    assert not store.save_download(session.id, "second", b"b" * 4000)
    assert store.retained_bytes == retained
    assert "second" not in session.downloads
    store.release_saved_downloads(session.id, dict(session.downloads))
    assert store.save_download(session.id, "second", b"b" * 4000)
    assert store.retained_bytes < 10_000


@pytest.mark.parametrize("history_url", ["", "test"], ids=["memory", "postgres"])
def test_stored_file_limit_counts_removed_files_of_every_kind(history_url):
    store = SessionStore(basic.make_settings(history_postgres_url=history_url, max_archive_bytes=10_000))
    session = store.create("owner", "schedule")
    upload = SandboxAttachment("roster.xlsx", "application/octet-stream", b"a" * 6000)
    upload_id = str(uuid4())
    (retained,) = store.retain_uploads(session.id, "owner", [upload], upload_id=upload_id)
    # A retried upload stores nothing new.
    assert store.retain_uploads(session.id, "owner", [upload], upload_id=upload_id) == (retained,)
    store.remove_upload(session.id, "owner", retained.id)
    workbook = {"kind": "optimizer-workbook", "source_id": "job", "filename": "result.xlsx"}
    workbook |= {"media_type": "application/octet-stream", "data": b"w" * 5000}
    if history_url:
        # Recovery storage keeps the removed upload, so these files would exceed the limit.
        with pytest.raises(HTTPException) as refused:
            store.retain_uploads(session.id, "owner", [upload])
        assert refused.value.status_code == 413
        assert not store.save_download(session.id, "run", b"z" * 5000)
        with pytest.raises(HTTPException):
            store.retain_archive_files(session.id, [workbook])
        assert store.save_download(session.id, "run", b"z" * 4000)
        assert session.archive_bytes == 10_000
    else:
        store.retain_uploads(session.id, "owner", [upload])
        assert store.save_download(session.id, "run", b"z" * 5000)
        store.retain_archive_files(session.id, [workbook])


def test_generated_download_survives_restart_and_removal(postgres_history):
    content = archive_bytes()

    def generate(_command, _timeout, sandbox):
        sandbox.files[WORKSPACE_DOWNLOAD] = content
        return CommandResult("created", "", 0)

    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=generate))
    provider = basic.ScriptedToolProvider(
        [ToolCallRequest((ToolCall("zip", "bash", json.dumps({"command": "create ZIP"})),))],
        [TextDelta("Ready")],
    )
    settings = basic.make_settings(history_postgres_url="test")
    app = basic.create_test_app(settings=settings, provider=provider, sandbox_factory=factory)
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        response = client.post(f"/sessions/{session}/messages", json={"message": "Create files"})
        download_id = next(data["download_id"] for kind, data in basic.parse_sse(response.text) if kind == "download")
        assert app.state.session_store.get(session).downloads[download_id] is None
        assert client.get(f"/sessions/{session}/downloads/{download_id}").content == content
        cookies = dict(client.cookies)
    restarted = basic.create_test_app(settings=settings, provider=basic.FakeProvider())
    with basic.AuthenticatedTestClient(restarted) as client:
        assert client.get(f"/sessions/{session}/downloads/{download_id}").status_code == 404
        client.cookies.update(cookies)
        assert client.get(f"/sessions/{session}/downloads/{download_id}").content == content
        assert client.delete(f"/sessions/{session}/downloads/{download_id}").status_code == 204
        assert client.get(f"/sessions/{session}/downloads/{download_id}").status_code == 404
        # The removed ZIP still counts toward the per-session stored file limit after a restart.
        assert restarted.state.session_store.get(session).archive_bytes == len(content)
        owner = cookies[basic.OWNER_COOKIE]
    assert postgres_history.load_file(session, owner, "download", download_id) is None
    assert postgres_history.load_file(session, owner, "download", download_id, True) == content
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT removed_at IS NOT NULL FROM chat_files").fetchone() == (True,)
        connection.execute("UPDATE chat_sessions SET expires_at = now() - interval '1 second'")
    postgres_history.prune()
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT count(*) FROM chat_files").fetchone() == (0,)


def test_optimizer_files_survive_restart_without_cached_workbooks(postgres_history):
    backend = basic.BackgroundTestOptimizer()
    provider = basic.ScriptedToolProvider(
        [ToolCallRequest((ToolCall("start", "optimizer", json.dumps({"action": "start"})),))],
        [TextDelta("Started")],
        [TextDelta("Reviewed")],
    )
    settings = basic.make_settings(history_postgres_url="test", optimizer_poll_interval_seconds=0.001)
    app = basic.create_test_app(settings=settings, provider=provider, optimizer_backend=backend)
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client, basic.schedule_yaml())
        assert client.post(f"/sessions/{session}/messages", json={"message": "Optimize"}).status_code == 200
        job = next(iter(app.state.session_optimizer._jobs.values()))
        original_schedule = job.schedule_yaml
        backend.release.set()

        async def finish():
            async with asyncio.timeout(10):
                await asyncio.gather(*tuple(app.state.session_optimizer._tasks))

        client.portal.call(finish)
        job = next(iter(app.state.session_optimizer._jobs.values()))
        assert job.artifact is None and job.artifact_saved
        assert app.state.session_optimizer._cached_artifact_bytes == 0
        response = client.get(f"/sessions/{session}/optimizations/{job.id}/xlsx")
        assert response.status_code == 200
        workbook = response.content
        cookies = dict(client.cookies)
    factory = FakeSandboxFactory()
    restarted = basic.create_test_app(
        settings=settings,
        provider=basic.ScriptedToolProvider(
            [ToolCallRequest((ToolCall("read", "read", json.dumps({"path": "/workspace/schedule.yaml"})),))],
            [TextDelta("Inspected")],
        ),
        sandbox_factory=factory,
    )
    with basic.AuthenticatedTestClient(restarted) as client:
        client.cookies.update(cookies)
        assert client.get(f"/sessions/{session}/optimizations/{job.id}/xlsx").content == workbook
        assert (
            client.post(f"/sessions/{session}/messages", json={"message": "Inspect the previous result"}).status_code
            == 200
        )
        assert factory.created[0].files["/workspace/optimizer-results/optimized-schedule.xlsx"] == workbook
        with postgres_history._connect() as connection:
            files = dict(connection.execute("SELECT kind, data FROM chat_files"))
        assert set(files) == {
            "optimizer-workbook",
            "optimizer-schedule",
            "optimizer-context",
            "optimizer-status",
            "optimizer-input",
        }
        assert files["optimizer-schedule"].decode() == original_schedule
        assert files["optimizer-input"].decode() == backend.submitted_yaml
        assert files["optimizer-workbook"] == workbook
        # A later failed optimization must not make an older workbook look current.
        failed = replace(
            job,
            id="failed-job",
            payload=OptimizerJobPayload(
                id="remote-failed",
                state="failed",
                terminal=True,
                links={"events": "/optimize/remote-failed/events?token=1.signed"},
            ),
            schedule_yaml=backend.submitted_yaml,
        )
        assert client.portal.call(restarted.state.recovery.save_optimizer_result, failed, None) is None
        assert client.portal.call(restarted.state.session_optimizer.latest_result_artifact, session) is None
        with postgres_history._connect() as connection:
            (status,) = connection.execute(
                "SELECT data FROM chat_files WHERE kind = 'optimizer-status' AND source_id = 'failed-job'"
            ).fetchone()
        # Exports include this file, so it must not carry signed optimizer stream tokens.
        assert "links" not in json.loads(status) and b"token" not in status
    with postgres_history._connect() as connection:
        connection.execute("UPDATE chat_sessions SET expires_at = now() - interval '1 second'")
    postgres_history.prune()
    with postgres_history._connect() as connection:
        assert connection.execute("SELECT count(*) FROM chat_files").fetchone() == (0,)


def test_failed_optimizer_file_write_is_retained_and_retried(postgres_history, monkeypatch):
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        job = SessionOptimization(
            id="job",
            session_id=session,
            remote_id="remote",
            source_sha256="hash",
            payload=OptimizerJobPayload(id="remote", state="completed"),
            original_id_by_anonymized_id={},
            people_count=0,
            schedule_yaml="description: original",
            submitted_yaml="description: submitted",
            request={"solver": "test"},
        )
        artifact = OptimizerArtifact(b"workbook", "optimized-schedule.xlsx", "application/xlsx", b"{}")
        app.state.session_optimizer._jobs[job.id] = job
        with monkeypatch.context() as patch:
            patch.setattr(ChatHistory, "save_session", unavailable)
            assert client.portal.call(app.state.recovery.save_optimizer_result, job, artifact) is not None
        live = app.state.session_store.get(session)
        assert len(live.pending_archive_files) == 5
        assert not app.state.recovery.evictable(session)
        pending_bytes = sum(len(file["data"]) for file in live.pending_archive_files.values())
        before = app.state.session_store.retained_bytes
        assert client.portal.call(app.state.recovery.save, session)
        assert live.pending_archive_files == {}
        assert app.state.session_store.retained_bytes == before - pending_bytes
        loaded = client.portal.call(app.state.recovery.load_optimizer_result, session, job.id)
        assert loaded.content == b"workbook" and loaded.schedule_context == b"{}"
        assert not job.artifact_saved
        latest = client.portal.call(app.state.session_optimizer.latest_result_artifact, session)
        assert latest == loaded


@pytest.mark.parametrize("operation", ["latest_optimizer", "load_file"])
def test_optional_optimizer_read_failure_still_finishes_the_chat(postgres_history, monkeypatch, operation):
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        live = app.state.session_store.get(session)
        postgres_history.save_session(
            session,
            app.state.session_store.recovery_state(session),
            files=[
                {
                    "kind": kind,
                    "source_id": "job",
                    "filename": kind,
                    "media_type": "application/octet-stream",
                    "data": data,
                }
                for kind, data in [("optimizer-status", b"{}"), ("optimizer-workbook", b"workbook")]
            ],
        )
        monkeypatch.setattr(ChatHistory, operation, unavailable)
        response = client.post(
            f"/sessions/{session}/messages",
            headers={"Accept": "application/json"},
            json={"message": "Continue the chat"},
        )

        async def finish():
            async with asyncio.timeout(5):
                while app.state.runs.busy(session):
                    await asyncio.sleep(0.001)

        client.portal.call(finish)
        events = app.state.session_event_stream.events_after(session)
        assert response.status_code == 202
        assert [event.type for event in events if event.type in {"done", "error", "stopped"}] == ["done"]
        assert not live.active
        if operation == "load_file":
            assert client.get(f"/sessions/{session}/optimizations/job/xlsx").status_code == 503


def test_upgrade_keeps_existing_upload_bytes_and_metadata(uninitialized_postgres_history):
    history = uninitialized_postgres_history
    migrations = Path(__file__).parents[1] / "nurse_scheduling/ai/migrations"
    session, owner, upload_id = (str(uuid4()) for _ in range(3))
    state = {
        "schedule_yaml": "description: original",
        "dropped_entries": 0,
        "dropped_history_messages": 0,
        "uploads": [
            {"id": upload_id, "filename": "原始.csv", "media_type": "text/csv", "size_bytes": 4, "request_sha256": None}
        ],
    }
    with history._connect() as connection:
        connection.execute("CREATE TABLE ai_history_migrations (version text PRIMARY KEY)")
        for migration in sorted(migrations.glob("*.sql")):
            if migration.name.startswith("007"):
                break
            connection.execute(migration.read_text(encoding="utf-8"))
            if migration.name.startswith("004"):
                _migrate_legacy_transcripts(connection)
            connection.execute("INSERT INTO ai_history_migrations VALUES (%s)", (migration.name,))
        connection.execute(
            "INSERT INTO chat_sessions (id, owner_hash, expires_at, state) VALUES (%s, %s, to_timestamp(%s), %s)",
            (session, hashlib.sha256(owner.encode()).hexdigest(), time.time() + 3600, json.dumps(state)),
        )
        connection.execute(
            "INSERT INTO chat_uploads (session_id, id, data) VALUES (%s, %s, %s)", (session, upload_id, b"data")
        )
    history.initialize()
    assert history.load_upload(session, owner, upload_id, 4) == b"data"
    with history._connect() as connection:
        assert connection.execute(
            "SELECT kind, source_id, filename, media_type, removed_at FROM chat_files"
        ).fetchone() == ("upload", upload_id, "原始.csv", "text/csv", None)
