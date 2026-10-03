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

import io
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient

from nurse_scheduling.ai.app import SessionStore
from nurse_scheduling.ai.downloads import WORKSPACE_DOWNLOAD, validate_download_zip
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
        with TestClient(app) as anonymous:
            assert anonymous.get(path).status_code == 401


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
