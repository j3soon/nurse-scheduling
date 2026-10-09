"""Retain bounded uploads across fresh VMs and allow owned removal."""

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

import json

import pytest
from fastapi import HTTPException

from nurse_scheduling.ai.context import removal_event, upload_event
from nurse_scheduling.ai.provider import TextDelta, ToolCall, ToolCallRequest
from nurse_scheduling.ai.sandbox.fake import FakeSandboxFactory
from nurse_scheduling.ai.sessions import SessionStore, _unique_filename
from nurse_scheduling.ai.workspace import SandboxAttachment

from .test_ai_basic import AuthenticatedTestClient, ScriptedToolProvider, create_session, create_test_app, make_settings


def test_followup_hydrates_retained_upload_and_removal_stops_hydration():
    # The fake sandbox starts only when a tool runs, so each turn reads one file.
    read = [ToolCallRequest((ToolCall("read", "read", json.dumps({"path": "/workspace/schedule.yaml"})),))]
    provider = ScriptedToolProvider(
        read, [TextDelta("Read")], read, [TextDelta("Read again")], read, [TextDelta("Removed")]
    )
    factory = FakeSandboxFactory()
    app = create_test_app(settings=make_settings(), provider=provider, sandbox_factory=factory)
    with AuthenticatedTestClient(app) as client:
        session = create_session(client)
        uploaded = client.post(
            f"/sessions/{session}/uploads", files={"files": ("notes.txt", b"ward handover", "text/plain")}
        )
        assert uploaded.status_code == 201
        other = AuthenticatedTestClient(app)
        assert other.post(f"/sessions/{session}/uploads", files={"files": ("x.txt", b"x")}).status_code == 404
        files = client.get(f"/sessions/{session}/uploads").json()
        assert files == uploaded.json()
        assert len(files) == 1 and files[0]["filename"] == "notes.txt" and files[0]["bytes"] == 13
        client.post(f"/sessions/{session}/messages", json={"message": "Read"})
        client.post(f"/sessions/{session}/messages", json={"message": "Read again"})
        path = f"/workspace/attachments/{files[0]['id']}-notes.txt"
        upload = provider.calls[0][1]
        assert path in upload["content"]
        assert provider.calls[0][-1]["content"] == "Read"
        assert provider.calls[2][1] == upload
        assert provider.calls[2][-1]["content"] == "Read again"
        assert factory.created[0].files[path] == factory.created[1].files[path] == b"ward handover"
        assert factory.created[0].closed and factory.created[1].closed
        assert other.delete(f"/sessions/{session}/uploads/{files[0]['id']}").status_code == 404
        other.close()
        assert client.delete(f"/sessions/{session}/uploads/{files[0]['id']}").status_code == 204
        assert client.get(f"/sessions/{session}/uploads").json() == []
        client.post(f"/sessions/{session}/messages", json={"message": "Check removed file"})
        assert provider.calls[4][-2]["content"].startswith("[App event] The user removed a file")
        assert path in provider.calls[4][-2]["content"]
        assert provider.calls[4][-1]["content"] == "Check removed file"
        assert not any(name.startswith("/workspace/attachments/") for name in factory.created[2].files)
        preflight = client.options(
            f"/sessions/{session}/uploads/example",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "DELETE"},
        )
        assert preflight.status_code == 200


def test_duplicate_filename_is_numbered_instead_of_replaced():
    taken = {"ward.csv", "ward (1).csv", "README", ".env", "a.tar.gz"}
    assert _unique_filename("new.csv", taken) == "new.csv"
    assert _unique_filename("ward.csv", taken) == "ward (2).csv"
    assert _unique_filename("README", taken) == "README (1)"
    assert _unique_filename(".env", taken) == ".env (1)"
    assert _unique_filename("a.tar.gz", taken) == "a.tar (1).gz"


def test_upload_history_is_charged_before_retaining_files():
    store = SessionStore(make_settings(max_session_bytes=500))
    session = store.create("owner", "description: test")
    original = store.retained_bytes

    with pytest.raises(HTTPException) as error:
        store.retain_uploads(session.id, "owner", [SandboxAttachment("ward.csv", "text/csv", b"x" * 400)])

    assert error.value.status_code == 429
    assert store.retained_bytes == original
    assert store.attachments(session.id, session.owner_token) == ()
    assert session.history == []
    assert store.retain_uploads(session.id, "owner", [SandboxAttachment("ward.csv", "text/csv", b"x")])
    assert store.retained_bytes <= 500


def test_upload_limits_removal_and_expiry_reclaim_bytes():
    store = SessionStore(make_settings(max_attachment_files=3, max_session_bytes=2000))
    session = store.create("owner", "description: test")
    original = store.retained_bytes
    first = store.retain_uploads(session.id, "owner", [SandboxAttachment("ward.csv", "text/csv", b"abc")])[0]
    second, third = store.retain_uploads(
        session.id,
        "owner",
        [SandboxAttachment("ward.csv", "text/csv", b"12345"), SandboxAttachment("ward.csv", "text/csv", b"6")],
    )
    assert [first.filename, second.filename, third.filename] == ["ward.csv", "ward (1).csv", "ward (2).csv"]
    assert len({first.id, second.id, third.id}) == 3
    assert store.attachments(session.id, session.owner_token) == (first, second, third)
    events = store._sessions[session.id].history
    assert [event["content"] for event in events] == [upload_event([first]), upload_event([second, third], 2)]
    assert store.retained_bytes == original + 9 + sum(len(event["content"]) for event in events)
    with pytest.raises(HTTPException) as error:
        store.retain_uploads(session.id, "owner", [SandboxAttachment("other", "text/plain", b"x")])
    assert error.value.status_code == 413
    store.remove_upload(session.id, "owner", second.id)
    with pytest.raises(HTTPException) as error:
        store.retain_uploads(session.id, "owner", [SandboxAttachment("note", "text/plain", b"x" * 2000)])
    assert error.value.status_code == 429
    assert store.attachments(session.id, session.owner_token) == (first, third)
    store.begin(session.id, "owner")
    with pytest.raises(HTTPException) as error:
        store.remove_upload(session.id, "owner", first.id)
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        store.retain_uploads(session.id, "owner", [SandboxAttachment("note", "text/plain", b"x")])
    assert error.value.status_code == 409
    store.abort(session.id, store._sessions[session.id].snapshot)
    reused = store.retain_uploads(session.id, "owner", [SandboxAttachment("ward.csv", "text/csv", b"new")])[0]
    assert reused.filename == "ward (1).csv" and reused.id != second.id
    assert store.attachments(session.id, session.owner_token) == (first, third, reused)
    store.remove_upload(session.id, "owner", first.id)
    store.remove_upload(session.id, "owner", third.id)
    store.remove_upload(session.id, "owner", reused.id)
    # File bytes are reclaimed. The upload and removal events stay in history.
    history_bytes = sum(len(event["content"]) for event in store._sessions[session.id].history)
    assert store.retained_bytes == original + history_bytes
    assert store._sessions[session.id].history[-1]["content"] == removal_event(reused, 3)
    store.retain_uploads(session.id, "owner", [first])
    session.expires_at = 0
    with pytest.raises(HTTPException) as error:
        store.attachments(session.id, session.owner_token)
    assert error.value.status_code == 404
    assert store.retained_bytes == 0
