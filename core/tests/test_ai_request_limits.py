"""Check AI authentication and byte limits before request bodies are buffered."""

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
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from nurse_scheduling.ai.app import OWNER_COOKIE, create_app
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.sandbox.fake import FakeSandboxFactory

TOKEN = "local-request-limit-test-key"


def make_app(*, authenticated=True):
    return create_app(
        settings=AiSettings(
            provider_base_url="http://127.0.0.1:9/v1",
            provider_api_key="stub",
            provider_model="stub",
            auth_token=TOKEN if authenticated else None,
            max_schedule_bytes=32,
            max_message_chars=16,
            max_attachment_bytes=8,
            max_attachment_files=2,
        ),
        sandbox_factory=FakeSandboxFactory(),
    )


def request(app, chunks, headers=(), path="/sessions"):
    async def run():
        received = 0
        messages = []
        iterator = iter(chunks)

        async def receive():
            nonlocal received
            body, more = next(iterator)
            received += len(body)
            return {"type": "http.request", "body": body, "more_body": more}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": list(headers),
            "client": ("127.0.0.1", 9001),
            "server": ("127.0.0.1", 9002),
        }
        await app(scope, receive, send)
        status = next(message["status"] for message in messages if message["type"] == "http.response.start")
        return status, received

    return asyncio.run(run())


@pytest.mark.parametrize("credential", [None, "wrong-key"])
def test_invalid_authentication_does_not_read_the_body(credential):
    body = json.dumps({"schedule_yaml": "x" * 100_000}).encode()
    headers = [(b"content-type", b"application/json")]
    if credential:
        headers.append((b"authorization", f"Bearer {credential}".encode()))

    status, received = request(make_app(), [(body, False)], headers)

    assert status == 401
    assert received == 0


def test_declared_oversize_json_is_rejected_without_reading_it():
    headers = [(b"content-type", b"application/json"), (b"content-length", b"100000")]
    status, received = request(make_app(authenticated=False), [(b"x" * 100_000, False)], headers)
    assert status == 413
    assert received == 0


@pytest.mark.parametrize("multipart", [False, True])
def test_streamed_bodies_stop_at_the_limit(multipart):
    def chunks():
        yield b"x" * 40_000, True
        yield b"x" * 40_000, True
        pytest.fail("The application read more body data after exceeding the limit")

    headers = [(b"authorization", f"Bearer {TOKEN}".encode())]
    if multipart:
        app = make_app()
        owner = str(uuid4())
        session_id = app.state.session_store.create(owner, "x").id
        cookie = f"{OWNER_COOKIE}={owner}"
        headers.extend([(b"cookie", cookie.encode()), (b"content-type", b"multipart/form-data; boundary=scan")])
        path = f"/sessions/{session_id}/uploads"

        def chunks():
            yield b'--scan\r\nContent-Disposition: form-data; name="files"; filename="x"\r\n\r\n' + b"x" * 40_000, True
            yield b"x" * 40_000, True
            pytest.fail("The multipart parser read more data after exceeding the limit")
    else:
        app, path = make_app(), "/sessions"
        headers.append((b"content-type", b"application/json"))
    status, received = request(app, chunks(), headers, path)
    assert status == 413
    assert received < 81_000


def test_valid_escaped_json_public_routes_and_preflights_still_work():
    app = make_app()
    with TestClient(app) as client:
        response = client.post(
            "/sessions", headers={"Authorization": f"Bearer {TOKEN}"}, json={"schedule_yaml": "\x01" * 32}
        )
        assert response.status_code == 201
        assert client.get("/health").status_code == 200
        assert (
            client.options(
                "/sessions", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}
            ).status_code
            == 200
        )
