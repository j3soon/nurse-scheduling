"""Verify complete, consistent ZIP exports with bounded attachment reads."""

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
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

import pytest
from psycopg.conninfo import make_conninfo
from starlette.requests import ClientDisconnect

from nurse_scheduling.ai import chat_archive
from nurse_scheduling.ai.chat_archive import FILE_CHUNK_BYTES, ChatArchiveResponse, create_chat_archive
from nurse_scheduling.ai.chat_export import build_saved_chat_export
from nurse_scheduling.ai.sessions import SessionStore
from nurse_scheduling.ai.workspace import SandboxAttachment
from nurse_scheduling.server.auth import create_stream_token

from . import test_ai_basic as basic
from .test_ai_history import postgres_history, uninitialized_postgres_history

__all__ = ["postgres_history", "uninitialized_postgres_history"]


def seed_files(history):
    store = SessionStore(basic.make_settings())
    session = store.create(str(uuid4()), basic.schedule_yaml())
    payload = b"all original bytes\x00" * (FILE_CHUNK_BYTES // 5)
    uploads = store.retain_uploads(
        session.id, session.owner_token, [SandboxAttachment("../../原始 [data].txt", "text/plain", payload)]
    )
    history.save_session(session.id, store.recovery_state(session.id), uploads=uploads)
    store.remove_upload(session.id, session.owner_token, uploads[0].id)
    history.save_session(session.id, store.recovery_state(session.id))
    files = [
        {
            "kind": "download",
            "source_id": "generated",
            "run_id": "run",
            "filename": "download.zip",
            "media_type": "application/zip",
            "data": b"generated ZIP",
        },
        {
            "kind": "optimizer-workbook",
            "source_id": "job",
            "filename": "optimized-schedule.xlsx",
            "media_type": "application/xlsx",
            "data": b"workbook",
        },
    ]
    # The generated download is detached too. Every version still belongs in the archive.
    history.save_session(session.id, store.recovery_state(session.id), files=files)
    return session, payload


def test_zip_contains_documents_state_and_every_archived_file(postgres_history):
    session, payload = seed_files(postgres_history)
    with create_chat_archive(postgres_history, session.id, owner=session.owner_token) as output:
        assert not isinstance(output, io.BytesIO)
        with ZipFile(output) as archive:
            assert {"chat.html", "chat.md", "chat.json", "schedule.yaml", "manifest.json"} <= set(archive.namelist())
            manifest = json.loads(archive.read("manifest.json"))
            assert {file["kind"] for file in manifest["files"]} == {"upload", "download", "optimizer-workbook"}
            assert archive.read("schedule.yaml").decode() == session.schedule_yaml
            snapshot = json.loads(archive.read("chat.json"))
            assert snapshot["session_state"]["uploads"] == []
            assert snapshot["session_id"] == session.id
            assert snapshot["snapshot_at"] == manifest["snapshot_at"]
            html, markdown = archive.read("chat.html").decode(), archive.read("chat.md").decode()
            for file in manifest["files"]:
                data = archive.read(file["path"])
                assert len(data) == file["bytes"]
                assert hashlib.sha256(data).hexdigest() == file["sha256"]
                assert file["path"].startswith("attachments/")
                assert ".." not in Path(file["path"]).parts
                if file["kind"] == "upload":
                    assert data == payload and file["removed_at"] is not None
                    assert "原始" in file["path"]
                if file["kind"] == "download":
                    assert file["removed_at"] is not None
            assert "Session files" in html and "## Session files" in markdown
            assert "%E5%8E%9F%E5%A7%8B" in html and "%E5%8E%9F%E5%A7%8B" in markdown


def test_zip_reads_one_repeatable_snapshot_in_bounded_chunks(postgres_history, monkeypatch):
    session, payload = seed_files(postgres_history)
    original = chat_archive.read_file_chunk
    chunks = []
    changed = False

    def read(connection, session_id, file_id, offset, length):
        nonlocal changed
        data = original(connection, session_id, file_id, offset, length)
        chunks.append(len(data))
        if not changed:
            changed = True
            with postgres_history._connect() as writer:
                writer.execute("UPDATE chat_files SET data = %s WHERE id = %s", (b"replacement", file_id))
                writer.execute(
                    "UPDATE chat_sessions SET state = jsonb_set(state, '{schedule_yaml}', '\"description: changed\"') WHERE id = %s",
                    (session_id,),
                )
        return data

    monkeypatch.setattr(chat_archive, "read_file_chunk", read)
    with create_chat_archive(postgres_history, session.id) as output, ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        uploaded = next(file for file in manifest["files"] if file["kind"] == "upload")
        assert archive.read(uploaded["path"]) == payload
        assert archive.read("schedule.yaml").decode() == session.schedule_yaml
    assert len(chunks) > len(manifest["files"])
    assert max(chunks) <= FILE_CHUNK_BYTES


def test_zip_checks_owner_and_expiry_and_closes_failed_output(postgres_history, monkeypatch):
    session, _payload = seed_files(postgres_history)
    outputs = []
    temporary_file = tempfile.TemporaryFile

    def temporary(*args, **kwargs):
        output = temporary_file(*args, **kwargs)
        outputs.append(output)
        return output

    monkeypatch.setattr(chat_archive.tempfile, "TemporaryFile", temporary)
    with pytest.raises(LookupError):
        create_chat_archive(postgres_history, session.id, owner=str(uuid4()))
    assert outputs[-1].closed
    with postgres_history._connect() as connection:
        connection.execute("UPDATE chat_sessions SET expires_at = now() - interval '1 second'")
    with pytest.raises(LookupError):
        create_chat_archive(postgres_history, session.id)
    assert outputs[-1].closed


@pytest.mark.parametrize("disconnect", [False, True], ids=["complete", "disconnect"])
def test_zip_response_closes_disk_file(disconnect):
    output = tempfile.TemporaryFile()  # noqa: SIM115 - response cleanup is the behavior under test.
    output.write(b"archive")
    response = ChatArchiveResponse(output, "chat.zip")
    sent = []

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        if disconnect:
            raise OSError("client disconnected")
        sent.append(message)

    async def run():
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)

    if disconnect:
        with pytest.raises(ClientDisconnect):
            asyncio.run(run())
    else:
        asyncio.run(run())
        assert b"".join(item.get("body", b"") for item in sent) == b"archive"
    assert output.closed


def test_zip_cli_matches_the_shared_writer_and_preserves_output_on_error(postgres_history, tmp_path):
    session, _payload = seed_files(postgres_history)
    with postgres_history._connect() as connection:
        database_url = connection.info.dsn
        if connection.info.password:
            database_url = make_conninfo(database_url, password=connection.info.password)
    destination = tmp_path / "chat.zip"
    environment = {**os.environ, "AI_HISTORY_POSTGRES_URL": database_url}
    result = subprocess.run(
        [sys.executable, "-m", "nurse_scheduling.ai.export_chat", session.id, str(destination)],
        env=environment,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    with create_chat_archive(postgres_history, session.id) as expected:
        assert destination.read_bytes() == expected.read()
    before = destination.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "nurse_scheduling.ai.export_chat", str(uuid4()), str(destination)],
        env=environment,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 1
    assert destination.read_bytes() == before
    assert not list(tmp_path.glob(".chat-export-*"))


def test_native_download_link_is_scoped_to_the_session_and_expires(postgres_history):
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test"), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        owner = client.cookies[basic.OWNER_COOKIE]
        prepared = client.post(f"/sessions/{session}/export")
        assert prepared.status_code == 200 and prepared.headers["cache-control"] == "no-store"
        token = prepared.json()["download_token"]
        assert token and basic.AI_AUTH_TOKEN not in token and owner not in token
        url = f"/sessions/{session}/export?token={token}"
        downloaded = client.get(url, headers={"Authorization": ""})
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"] == "application/zip"
        assert downloaded.headers["cache-control"] == "no-store"
        with create_chat_archive(postgres_history, session, owner=owner) as expected:
            assert downloaded.content == expected.read()
        other_session = basic.create_session(client)
        assert (
            client.get(f"/sessions/{other_session}/export?token={token}", headers={"Authorization": ""}).status_code
            == 401
        )
        other = basic.AuthenticatedTestClient(app)
        # A browser that does not send the owner cookie can still redeem the link.
        other_downloaded = other.get(url, headers={"Authorization": ""})
        assert other_downloaded.status_code == 200 and other_downloaded.content == downloaded.content
        # Minting still requires the browser ownership cookie.
        assert other.post(f"/sessions/{session}/export").status_code == 404
        other.close()
        expired = create_stream_token(
            basic.AI_AUTH_TOKEN,
            f"ai-chat-export:{session}",
            ttl_seconds=300,
            now=datetime.now(UTC) - timedelta(seconds=600),
        )
        for bad in (expired, "invalid"):
            rejected = client.get(f"/sessions/{session}/export?token={bad}", headers={"Authorization": ""})
            assert rejected.status_code == 401
            assert rejected.json()["detail"] == "The export download link is invalid or has expired."
        assert client.get(f"/sessions/{session}/export", headers={"Authorization": ""}).status_code == 401
        assert client.post(url, headers={"Authorization": ""}).status_code == 401
        assert (
            client.post(
                f"/sessions/{session}/messages?token={token}",
                headers={"Authorization": ""},
                json={"message": "This token must not authorize chat messages."},
            ).status_code
            == 401
        )
        stream_token = create_stream_token(basic.AI_AUTH_TOKEN, session, ttl_seconds=300)
        assert (
            client.get(f"/sessions/{session}/export?token={stream_token}", headers={"Authorization": ""}).status_code
            == 401
        )


def test_native_export_without_shared_auth_still_requires_owner(postgres_history):
    app = basic.create_test_app(
        settings=basic.make_settings(history_postgres_url="test", auth_token=None), provider=basic.FakeProvider()
    )
    with basic.AuthenticatedTestClient(app) as client:
        session = basic.create_session(client)
        assert client.post(f"/sessions/{session}/export").json() == {"download_token": None}
        assert client.get(f"/sessions/{session}/export").status_code == 200


def test_browser_archive_fixture_uses_the_current_python_documents():
    reference = json.loads((Path(__file__).parent / "ai_fixtures/chat-export-archive.json").read_text(encoding="utf-8"))
    with ZipFile(io.BytesIO(base64.b64decode(reference["zip_base64"]))) as archive:
        snapshot = json.loads(archive.read("chat.json"))
        manifest = json.loads(archive.read("manifest.json"))
        html, markdown = chat_archive._documents(snapshot, manifest["files"])
        assert archive.read("chat.html").decode() == html == reference["html"]
        assert archive.read("chat.md").decode() == markdown
        for file in manifest["files"]:
            assert hashlib.sha256(archive.read(file["path"])).hexdigest() == file["sha256"]


def test_archive_documents_link_uploaded_files_without_touching_the_snapshot():
    reference = json.loads((Path(__file__).parent / "ai_fixtures/chat-export-archive.json").read_text(encoding="utf-8"))
    with ZipFile(io.BytesIO(base64.b64decode(reference["zip_base64"]))) as archive:
        snapshot = json.loads(archive.read("chat.json"))
        manifest = json.loads(archive.read("manifest.json"))
        html, markdown = chat_archive._documents(snapshot, manifest["files"])
    uploads = [file for file in manifest["files"] if file["kind"] == "upload"]
    assert uploads, "the golden archive should bundle uploaded files"
    for file in uploads:
        url = file["path"]
        # Each uploaded-file entry links to its copy inside the ZIP in a new tab.
        assert f'<a href="{url}" target="_blank" rel="noopener noreferrer">{file["filename"]} (' in html
        assert f"]({url})" in markdown
    # chat.json keeps the untouched snapshot, and snapshot-only exports stay plain.
    assert "file_urls" not in snapshot.get("metadata", {})
    solo_html = build_saved_chat_export(snapshot, "html")
    solo_markdown = build_saved_chat_export(snapshot, "markdown")
    assert '<a href="attachments/upload/' not in solo_html
    assert "](attachments/upload/" not in solo_markdown
