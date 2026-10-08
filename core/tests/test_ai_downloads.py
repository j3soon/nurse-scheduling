"""Bound generated archives and deliver them after the disposable sandbox closes."""

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
import io
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient

from nurse_scheduling.ai.app import SessionStore
from nurse_scheduling.ai.background import SessionEventBroker, build_provider_messages, run_background_turn
from nurse_scheduling.ai.downloads import WORKSPACE_DOWNLOAD, validate_download_zip
from nurse_scheduling.ai.lifecycle import Turn
from nurse_scheduling.ai.provider import TextDelta, ToolCall, ToolCallRequest
from nurse_scheduling.ai.sandbox import CommandResult
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory

from .test_ai_basic import AuthenticatedTestClient, ScriptedToolProvider, create_session, create_test_app, make_settings


def archive_bytes(value: bytes = b"name,date\nAlex,2026-10-01\n", name: str = "requests.csv") -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(name, value)
    return output.getvalue()


@pytest.mark.parametrize("name", ["../escape.csv", "/absolute.csv", "..\\escape.csv"])
def test_zip_rejects_paths_outside_the_download_directory(name):
    with pytest.raises(ValueError, match="relative file paths"):
        validate_download_zip(archive_bytes(name=name), 1000)


def test_zip_checks_actual_contents_and_compressed_limit():
    valid = archive_bytes()
    validate_download_zip(valid, 1000)
    with pytest.raises(ValueError, match="download size"):
        validate_download_zip(valid, len(valid) - 1)
    with pytest.raises(ValueError, match="uncompressed"):
        validate_download_zip(archive_bytes(b"a" * 10000), 1000)
    with pytest.raises(ValueError, match="readable ZIP"):
        validate_download_zip(b"not a ZIP", 1000)
    corrupt = bytearray(valid)
    corrupt[45] ^= 255
    with pytest.raises(ValueError):
        validate_download_zip(bytes(corrupt), 1000)


def test_prompt_names_the_captured_path_and_the_configured_limit():
    messages = build_provider_messages([], "description: schedule\n", "Make a CSV.", max_download_bytes=1234)
    system = messages[0]["content"]

    assert f"`{WORKSPACE_DOWNLOAD}`" in system
    assert "Download size limit: 1234 bytes." in system


def test_generated_zip_is_downloadable_after_sandbox_cleanup_and_is_owned():
    content = archive_bytes()

    def generate(command, timeout, sandbox):
        sandbox.files[WORKSPACE_DOWNLOAD] = content
        return CommandResult("created", "", 0)

    provider = ScriptedToolProvider(
        [ToolCallRequest((ToolCall("zip", "bash", json.dumps({"command": "create ZIP"})),))],
        [TextDelta("Your files are ready.")],
    )
    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=generate))
    app = create_test_app(settings=make_settings(), provider=provider, sandbox_factory=factory)
    with AuthenticatedTestClient(app) as client:
        session_id = create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "Download the CSV."})
        assert "event: download" in response.text
        assert factory.created[0].closed
        download_id = next(
            json.loads(line[6:])["download_id"]
            for line in response.text.splitlines()
            if line.startswith("data: ") and '"download_id"' in line
        )
        path = f"/sessions/{session_id}/downloads/{download_id}"
        download = client.get(path)
        assert download.content == content
        assert download.headers["content-type"] == "application/zip"
        assert client.get(f"/sessions/{session_id}/downloads/missing").status_code == 404
        with AuthenticatedTestClient(app) as other:
            assert other.get(path).status_code == 404
            assert other.delete(path).status_code == 404
        with TestClient(app) as anonymous:
            assert anonymous.get(path).status_code == 401
            assert anonymous.delete(path).status_code == 401
        before_removal = app.state.session_store.retained_bytes
        assert client.delete(path).status_code == 204
        assert app.state.session_store.retained_bytes == before_removal - len(content)
        assert client.get(path).status_code == 404
        assert client.delete(path).status_code == 404


def test_generated_bytes_share_session_budget_and_are_reclaimed():
    store = SessionStore(make_settings(max_session_bytes=1000))
    session = store.create("owner", "description: test")
    original = store.retained_bytes
    assert store.save_download(session.id, "zip1", b"x" * 100)
    assert store.retained_bytes == original + 100
    assert not store.save_download(session.id, "zip2", b"x" * 1000)
    session.expires_at = 0
    store._prune_expired()
    assert store.retained_bytes == 0


def test_removing_old_zip_allows_a_new_download_without_dropping_other_files():
    store = SessionStore(make_settings(max_session_bytes=1000))
    session = store.create("owner", "description: test")
    original = store.retained_bytes
    content = b"x" * ((1000 - original) // 2)
    assert store.save_download(session.id, "zip1", content)
    assert store.save_download(session.id, "zip2", content)
    assert not store.save_download(session.id, "zip3", content)

    store.remove_download(session.id, "owner", "zip1")

    assert store.retained_bytes == original + len(content)
    assert store.download(session.id, "owner", "zip2") == content
    assert store.save_download(session.id, "zip3", content)
    assert store.download(session.id, "owner", "zip3") == content
    session.expires_at = 0
    store._prune_expired()
    assert store.retained_bytes == 0


@pytest.mark.parametrize("background", [False, True], ids=["foreground", "background"])
def test_download_memory_failure_keeps_the_completed_turn(background):
    def generate(command, timeout, sandbox):
        sandbox.files[WORKSPACE_DOWNLOAD] = archive_bytes()
        return CommandResult("created", "", 0)

    provider = ScriptedToolProvider(
        [ToolCallRequest((ToolCall("zip", "bash", json.dumps({"command": "create ZIP"})),))],
        [TextDelta("Your files are ready.")],
    )
    settings = make_settings(max_session_bytes=100)
    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=generate))
    app = create_test_app(settings=settings, provider=provider, sandbox_factory=factory)
    store = app.state.session_store
    if background:
        session_id = store.create("owner", "description: test").id
        broker = SessionEventBroker()

        async def review():
            await run_background_turn(
                session_id,
                "Download the CSV.",
                None,
                settings=settings,
                store=store,
                event_broker=broker,
                turn=Turn(),
                concurrency_limit=asyncio.Semaphore(1),
                history_log=None,
                provider=provider,
                sandbox_factory=factory,
                session_optimizer=app.state.session_optimizer,
            )

        asyncio.run(review())
        event_types = [event.type for event in broker.events_after(session_id)]
    else:
        with AuthenticatedTestClient(app) as client:
            session_id = create_session(client)
            response = client.post(f"/sessions/{session_id}/messages", json={"message": "Download the CSV."})
            event_types = [line[7:] for line in response.text.splitlines() if line.startswith("event: ")]

    assert "warning" in event_types
    assert "error" not in event_types
    assert event_types[-1] == "done"
    assert store._sessions[session_id].history[-1]["content"] == "Your files are ready."
    assert store._sessions[session_id].downloads == {}
    assert factory.created[0].closed
