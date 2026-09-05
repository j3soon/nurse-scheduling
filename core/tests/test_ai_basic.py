"""Tests for the experimental AI service."""

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
import json
from collections.abc import AsyncIterator, Sequence
from unittest.mock import ANY

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from nurse_scheduling.ai.app import (
    CANDIDATE_VALIDATION_ERROR,
    OWNER_COOKIE,
    PROPOSAL_APPROVED_HISTORY,
    PROPOSAL_INVALID_HISTORY,
    PROPOSAL_REJECTED_HISTORY,
    PROVIDER_ERROR,
    SANDBOX_TURN_TIMEOUT_ERROR,
    SERVICE_NAME,
    STALE_TURN_ERROR,
)
from nurse_scheduling.ai.app import create_app as create_ai_app
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.provider import ChatMessage, ProviderError, TextDelta, ToolCall, ToolCallRequest
from nurse_scheduling.ai.sandbox import CommandResult, SandboxError
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory
from nurse_scheduling.ai.sandbox_agent import WORKSPACE_SCHEDULE, SandboxTurnTimeoutError

from .ai_test_helper import SCHEDULE_BYTE_LIMIT, base_schedule_payload, schedule_yaml

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\xff\xd9"
WEBP_BYTES = b"RIFF\x04\x00\x00\x00WEBP"
AI_AUTH_TOKEN = "ai-shared-test-token"
AI_AUTH_HEADERS = {"Authorization": f"Bearer {AI_AUTH_TOKEN}"}


class AuthenticatedTestClient(TestClient):
    """Test client carrying the mandatory AI service credential by default."""

    def __init__(self, *args, **kwargs) -> None:
        headers = {**AI_AUTH_HEADERS, **kwargs.pop("headers", {})}
        super().__init__(*args, headers=headers, **kwargs)


@pytest.fixture(autouse=True)
def configured_sandbox_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give positive environment parsing tests the required sandbox settings."""
    monkeypatch.setenv("AI_AUTH_TOKEN", AI_AUTH_TOKEN)
    monkeypatch.delenv("AI_AUTH_REQUIRED", raising=False)
    monkeypatch.setenv("AI_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "test-e2b-key")


class FakeProvider:
    """Record prompts and return deterministic streamed responses."""

    def __init__(self, responses: list[list[str | Exception] | Exception] | None = None) -> None:
        self.responses = responses or [["Hello", " from AI"]]
        self.calls: list[list[ChatMessage]] = []
        self.offered_tools: object = None

    async def stream_events(self, messages: Sequence[ChatMessage], tools=None) -> AsyncIterator[TextDelta]:
        self.calls.append(list(messages))
        self.offered_tools = tools
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        for delta in response:
            if isinstance(delta, Exception):
                raise delta
            yield TextDelta(delta)


def make_settings(**overrides: object) -> AiSettings:
    """Create isolated settings with small test-friendly limits."""
    values = {
        "provider_base_url": "https://provider.example/v1",
        "provider_api_key": "test-token",
        "provider_model": "test-model",
        "auth_token": AI_AUTH_TOKEN,
        "max_sessions": 10,
        "max_history_messages": 20,
        "max_message_chars": 100,
        "max_schedule_bytes": 1000,
        "max_concurrent_requests": 2,
        "cookie_secure": False,
    }
    values.update(overrides)
    return AiSettings(**values)


def create_test_app(*, settings: AiSettings, provider, sandbox_factory=None):
    """Create the app with a fake disposable sandbox unless a test supplies one."""
    return create_ai_app(
        settings=settings,
        provider=provider,
        sandbox_factory=sandbox_factory or FakeSandboxFactory(),
    )


def test_application_initializes_sentry_for_ai_service(monkeypatch):
    calls = []
    monkeypatch.setattr("nurse_scheduling.ai.app.init_sentry", lambda version, *, app: calls.append((version, app)))

    create_test_app(settings=make_settings(), provider=FakeProvider())

    assert calls == [("0.2.0", "ai-backend")]


def test_application_lifespan_runs_sandbox_cleanup_supervision():
    class LifecycleFactory(FakeSandboxFactory):
        starts = 0
        stops = 0

        async def start_cleanup(self) -> None:
            self.starts += 1

        async def stop_cleanup(self) -> None:
            self.stops += 1

    factory = LifecycleFactory()
    with AuthenticatedTestClient(
        create_test_app(settings=make_settings(), provider=FakeProvider(), sandbox_factory=factory)
    ) as client:
        assert client.get("/health").status_code == 200
        assert factory.starts == 1

    assert factory.stops == 1


def test_ai_authentication_discovery_and_healthchecks_stay_public() -> None:
    client = TestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))

    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    capabilities = client.get("/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["auth"] == {"required": True, "scheme": "bearer"}


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", "/sessions", {"schedule_yaml": "description: test"}),
        ("post", "/sessions/missing/messages", {"message": "Hello"}),
        ("put", "/sessions/missing/schedule", {"schedule_yaml": "description: changed"}),
        ("post", "/sessions/missing/proposal/approve", {"base_sha256": "0" * 64}),
        ("post", "/sessions/missing/proposal/reject", None),
    ],
)
def test_ai_session_routes_require_authentication(method: str, path: str, json_body: dict | None) -> None:
    client = TestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))

    response = client.request(method, path, json=json_body)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "Backend credentials are required."


def test_ai_session_routes_reject_invalid_credentials_and_accept_the_configured_token() -> None:
    client = TestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))

    rejected = client.post(
        "/sessions",
        headers={"Authorization": "Bearer wrong-ai-token"},
        json={"schedule_yaml": "description: test"},
    )
    accepted = client.post(
        "/sessions",
        headers=AI_AUTH_HEADERS,
        json={"schedule_yaml": "description: test"},
    )

    assert rejected.status_code == 401
    assert rejected.json()["detail"] == "Backend credentials are invalid."
    assert accepted.status_code == 201


def test_ai_cors_preflight_allows_the_authorization_header() -> None:
    client = TestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))

    response = client.options(
        "/sessions",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed


def test_ai_generated_api_docs_are_disabled() -> None:
    client = TestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))

    for path in ("/openapi.json", "/docs", "/redoc"):
        assert client.get(path, headers=AI_AUTH_HEADERS).status_code == 404


def create_session(client: TestClient, schedule_yaml: str = "description: test") -> str:
    """Create a session and return its public UUID."""
    response = client.post("/sessions", json={"schedule_yaml": schedule_yaml})
    assert response.status_code == 201
    return response.json()["id"]


def test_secure_ai_owner_cookie_allows_cross_site_frontends() -> None:
    client = TestClient(
        create_test_app(settings=make_settings(cookie_secure=True), provider=FakeProvider()),
        base_url="https://testserver",
    )

    response = client.post("/sessions", json={"schedule_yaml": "description: test"}, headers=AI_AUTH_HEADERS)

    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=none" in cookie
    assert "Secure" in cookie


def test_insecure_local_ai_owner_cookie_stays_same_site() -> None:
    client = TestClient(create_test_app(settings=make_settings(cookie_secure=False), provider=FakeProvider()))

    response = client.post("/sessions", json={"schedule_yaml": "description: test"}, headers=AI_AUTH_HEADERS)

    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert "SameSite=strict" in cookie
    assert "Secure" not in cookie


def parse_sse(response_text: str) -> list[tuple[str, dict[str, str]]]:
    """Parse the small SSE subset emitted by the service."""
    events: list[tuple[str, dict[str, str]]] = []
    for block in response_text.strip().split("\n\n"):
        lines = block.splitlines()
        event_type = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        data = next(json.loads(line.removeprefix("data: ")) for line in lines if line.startswith("data: "))
        events.append((event_type, data))
    return events


@pytest.mark.parametrize("wait_stage", ["provider", "command"])
def test_client_disconnect_cancels_the_turn_and_closes_its_sandbox(wait_stage: str) -> None:
    async def exercise() -> tuple[FakeSandboxBackend, bool, bool, list[ChatMessage]]:
        operation_started = asyncio.Event()
        operation_cancelled = asyncio.Event()

        async def wait_until_cancelled() -> None:
            operation_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                operation_cancelled.set()
                raise

        class WaitingProvider:
            async def stream_events(self, _messages, tools=None):
                if wait_stage == "provider":
                    await wait_until_cancelled()
                    return
                yield ToolCallRequest((ToolCall("call-1", BASH_TOOL, '{"command":"sleep 30"}'),))

        async def command_handler(*_args) -> CommandResult:
            await wait_until_cancelled()
            return CommandResult("", "", 0)

        factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=command_handler))
        app = create_test_app(settings=make_settings(), provider=WaitingProvider(), sandbox_factory=factory)
        session = app.state.session_store.create("browser-owner", schedule_yaml())
        request_events: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        await request_events.put(
            {
                "type": "http.request",
                "body": json.dumps({"message": "Wait for me"}).encode(),
                "more_body": False,
            }
        )
        response_started = asyncio.Event()

        async def receive() -> dict[str, object]:
            return await request_events.get()

        async def send(message: dict[str, object]) -> None:
            if message["type"] == "http.response.start":
                response_started.set()

        path = f"/sessions/{session.id}/messages"
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"authorization", f"Bearer {AI_AUTH_TOKEN}".encode()),
                (b"content-type", b"application/json"),
                (b"cookie", f"{OWNER_COOKIE}=browser-owner".encode()),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
        request_task = asyncio.create_task(app(scope, receive, send))
        await asyncio.wait_for(operation_started.wait(), timeout=1)
        await asyncio.wait_for(response_started.wait(), timeout=1)
        await request_events.put({"type": "http.disconnect"})
        await asyncio.wait_for(request_task, timeout=1)

        backend = factory.created[0]
        return backend, operation_cancelled.is_set(), session.active, list(session.history)

    backend, operation_cancelled, session_active, history = asyncio.run(exercise())

    assert operation_cancelled
    assert backend.closed
    assert backend.close_calls == 1
    assert not session_active
    assert history == []


def test_disconnect_before_stream_iteration_releases_the_session() -> None:
    async def exercise() -> bool:
        app = create_test_app(settings=make_settings(), provider=FakeProvider())
        session = app.state.session_store.create("browser-owner", schedule_yaml())
        request_events: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        await request_events.put(
            {
                "type": "http.request",
                "body": json.dumps({"message": "Do not start"}).encode(),
                "more_body": False,
            }
        )
        await request_events.put({"type": "http.disconnect"})

        async def receive() -> dict[str, object]:
            return await request_events.get()

        async def send(_message: dict[str, object]) -> None:
            pass

        path = f"/sessions/{session.id}/messages"
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"authorization", f"Bearer {AI_AUTH_TOKEN}".encode()),
                (b"content-type", b"application/json"),
                (b"cookie", f"{OWNER_COOKIE}=browser-owner".encode()),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }

        await app(scope, receive, send)
        return session.active

    assert not asyncio.run(exercise())


def test_health_and_streamed_schedule_question() -> None:
    provider = FakeProvider()
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=provider))

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service_name"] == SERVICE_NAME

    session_id = create_session(client, "people:\n  - id: Alice\n")
    response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Who works Monday?"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert parse_sse(response.text) == [
        ("delta", {"text": "Hello"}),
        ("delta", {"text": " from AI"}),
        ("done", {"message_id": ANY}),
    ]
    prompt = provider.calls[0]
    assert prompt[-1] == {"role": "user", "content": "Who works Monday?"}
    # The schedule itself is read with the view tool, so only its shape is sent.
    assert "Alice" not in prompt[0]["content"]
    assert "schedule.yaml is 2 lines" in prompt[0]["content"]
    assert "untrusted data" in prompt[0]["content"]


def test_existing_owner_cookie_is_not_reflected_in_create_response() -> None:
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))
    client.cookies.set(OWNER_COOKIE, "browser-supplied-owner")

    response = client.post("/sessions", json={"schedule_yaml": "description: test"})

    assert response.status_code == 201
    assert OWNER_COOKIE not in response.headers.get("set-cookie", "")


def test_capabilities_report_configured_attachment_limits() -> None:
    client = AuthenticatedTestClient(
        create_test_app(
            settings=make_settings(
                attachment_mode="images",
                max_image_files=2,
                max_image_bytes=1234,
                document_attachment_mode="text",
                max_document_files=3,
                max_document_bytes=4321,
            ),
            provider=FakeProvider(),
        )
    )

    response = client.get("/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "image_attachments": {
            "enabled": True,
            "accepted_media_types": ["image/jpeg", "image/png", "image/webp"],
            "max_files": 2,
            "max_bytes_per_file": 1234,
        },
        "document_attachments": {
            "enabled": True,
            "accepted_extensions": [".txt", ".md", ".csv", ".pdf", ".xlsx"],
            "max_files": 3,
            "max_bytes_per_file": 4321,
        },
        "auth": {"required": True, "scheme": "bearer"},
    }


def test_image_is_sent_to_provider_but_not_retained_in_history() -> None:
    provider = FakeProvider([["Image answer"], ["Follow-up answer"]])
    client = AuthenticatedTestClient(
        create_test_app(settings=make_settings(attachment_mode="images"), provider=provider)
    )
    session_id = create_session(client)

    image_response = client.post(
        f"/sessions/{session_id}/messages",
        data={"message": "What is shown?"},
        files={"images": ("ward.png", PNG_BYTES, "image/png")},
    )
    follow_up_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Summarize your answer."},
    )

    assert image_response.status_code == 200
    assert follow_up_response.status_code == 200
    image_content = provider.calls[0][-1]["content"]
    assert image_content == [
        {"type": "text", "text": "What is shown?"},
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{base64.b64encode(PNG_BYTES).decode('ascii')}"},
        },
    ]
    follow_up_prompt = json.dumps(provider.calls[1])
    assert "Images were attached to this message" in follow_up_prompt
    assert "data:image/png;base64" not in follow_up_prompt


@pytest.mark.parametrize(
    ("filename", "media_type", "data"),
    [
        ("ward.jpg", "image/jpeg", JPEG_BYTES),
        ("ward-trailing-data.jpg", "image/jpeg", JPEG_BYTES + b"trailing metadata"),
        ("ward.webp", "image/webp", WEBP_BYTES),
    ],
)
def test_supported_image_signatures_are_sent_to_provider(filename: str, media_type: str, data: bytes) -> None:
    provider = FakeProvider()
    client = AuthenticatedTestClient(
        create_test_app(settings=make_settings(attachment_mode="images"), provider=provider)
    )
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        data={"message": "What is shown?"},
        files={"images": (filename, data, media_type)},
    )

    assert response.status_code == 200
    content = provider.calls[0][-1]["content"]
    assert isinstance(content, list)
    assert content[1]["image_url"]["url"].startswith(f"data:{media_type};base64,")


def test_documents_are_sent_to_provider_but_contents_are_not_retained() -> None:
    provider = FakeProvider([["Document answer"], ["Follow-up answer"]])
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=provider))
    session_id = create_session(client)

    document_response = client.post(
        f"/sessions/{session_id}/messages",
        data={"message": "Compare these files."},
        files=[
            ("documents", ("notes.md", b"# Private marker 8462", "text/markdown")),
            ("documents", ("staff.csv", b"name,shift\nAlice,day\n", "text/csv")),
        ],
    )
    follow_up_response = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Summarize your answer."},
    )

    assert document_response.status_code == 200
    assert follow_up_response.status_code == 200
    document_content = provider.calls[0][-1]["content"]
    assert isinstance(document_content, str)
    assert document_content.startswith("Compare these files.")
    assert '"filename": "notes.md"' in document_content
    assert "Private marker 8462" in document_content
    assert "Alice,day" in document_content
    follow_up_prompt = json.dumps(provider.calls[1])
    assert "Documents were attached" in follow_up_prompt
    assert "notes.md" in follow_up_prompt
    assert "Private marker 8462" not in follow_up_prompt
    assert "Alice,day" not in follow_up_prompt


@pytest.mark.parametrize(
    ("filename", "media_type"),
    [
        ("notes.md", "text/plain"),
        ("staff.csv", "application/csv"),
        ("staff.csv", "application/vnd.ms-excel"),
        ("staff.csv", "text/plain"),
    ],
)
def test_text_documents_accept_each_advertised_media_type(filename: str, media_type: str) -> None:
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        data={"message": "Read the file."},
        files={"documents": (filename, b"Alice works Monday.", media_type)},
    )

    assert response.status_code == 200


def test_images_and_documents_share_one_provider_user_message() -> None:
    provider = FakeProvider()
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=provider))
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        data={"message": "Use both attachments."},
        files=[
            ("images", ("ward.png", PNG_BYTES, "image/png")),
            ("documents", ("notes.txt", b"Alice works Monday.", "text/plain")),
        ],
    )

    assert response.status_code == 200
    content = provider.calls[0][-1]["content"]
    assert isinstance(content, list)
    assert "Alice works Monday" in content[0]["text"]
    assert content[1]["type"] == "image_url"


@pytest.mark.parametrize(
    ("settings", "files", "expected_status", "expected_detail"),
    [
        (
            {"attachment_mode": "none"},
            [("images", ("ward.png", PNG_BYTES, "image/png"))],
            422,
            "Image attachments are disabled.",
        ),
        (
            {"attachment_mode": "images"},
            [("images", ("ward.png", b"not an image", "image/png"))],
            415,
            "Image content does not match its type.",
        ),
        (
            {"attachment_mode": "images", "max_image_bytes": 8},
            [("images", ("ward.png", PNG_BYTES, "image/png"))],
            413,
            "Image attachment is too large.",
        ),
        (
            {"attachment_mode": "images", "max_image_files": 1},
            [
                ("images", ("first.png", PNG_BYTES, "image/png")),
                ("images", ("second.png", PNG_BYTES, "image/png")),
            ],
            413,
            "Too many image attachments.",
        ),
    ],
)
def test_image_attachment_limits(
    settings: dict[str, object],
    files: list[tuple[str, tuple[str, bytes, str]]],
    expected_status: int,
    expected_detail: str,
) -> None:
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(**settings), provider=FakeProvider()))
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        data={"message": "Question"},
        files=files,
    )

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail


@pytest.mark.parametrize(
    ("settings", "files", "expected_status", "expected_detail"),
    [
        (
            {"document_attachment_mode": "none"},
            [("documents", ("notes.txt", b"hello", "text/plain"))],
            422,
            "Document attachments are disabled.",
        ),
        (
            {},
            [("documents", ("notes.pdf", b"hello", "application/pdf"))],
            415,
            "PDF content does not match its filename.",
        ),
        (
            {},
            [("documents", ("notes.docx", b"hello", "application/octet-stream"))],
            415,
            "Unsupported document type.",
        ),
        (
            {},
            [("documents", ("notes.txt", b"hello", "image/png"))],
            415,
            "Document type does not match its filename.",
        ),
        (
            {},
            [("documents", ("notes.txt", b"\xff", "text/plain"))],
            415,
            "Text document attachment must be UTF-8.",
        ),
        (
            {},
            [("documents", ("notes.txt", b"hello\x00hidden", "text/plain"))],
            415,
            "Text document attachment must be UTF-8.",
        ),
        (
            {},
            [("documents", ("notes.pdf", b"%PDF-1.4", "text/plain"))],
            415,
            "Document type does not match its filename.",
        ),
        (
            {},
            [("documents", ("notes.xlsx", b"PK\x03\x04", "application/zip"))],
            415,
            "Document type does not match its filename.",
        ),
        (
            {"max_document_bytes": 4},
            [("documents", ("notes.txt", b"hello", "text/plain"))],
            413,
            "Document attachment is too large.",
        ),
        (
            {"max_document_files": 1},
            [
                ("documents", ("first.txt", b"one", "text/plain")),
                ("documents", ("second.txt", b"two", "text/plain")),
            ],
            413,
            "Too many document attachments.",
        ),
    ],
)
def test_document_attachment_limits(
    settings: dict[str, object],
    files: list[tuple[str, tuple[str, bytes, str]]],
    expected_status: int,
    expected_detail: str,
) -> None:
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(**settings), provider=FakeProvider()))
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        data={"message": "Question"},
        files=files,
    )

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail


def test_second_turn_keeps_only_system_message_at_beginning() -> None:
    provider = FakeProvider([["First answer"], ["Second answer"]])
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=provider))
    session_id = create_session(client, "description: current")

    first = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "First question"},
    )
    second = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Follow up"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert {"role": "user", "content": "First question"} in provider.calls[1]
    assert {"role": "assistant", "content": "First answer"} in provider.calls[1]
    assert "Current schedule summary:" in provider.calls[1][0]["content"]
    assert provider.calls[1][0]["role"] == "system"
    assert all(message["role"] != "system" for message in provider.calls[1][1:])


def test_private_container_origin_can_call_ai_backend_directly() -> None:
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))

    response = client.options(
        "/capabilities",
        headers={
            "Origin": "http://192.168.0.117:3005",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://192.168.0.117:3005"


def test_session_uuid_alone_does_not_bypass_browser_ownership() -> None:
    app = create_test_app(settings=make_settings(), provider=FakeProvider())
    owner_client = AuthenticatedTestClient(app)
    other_client = AuthenticatedTestClient(app)
    session_id = create_session(owner_client)
    create_session(other_client)

    response = other_client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Try another session"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat session not found."


def test_provider_failure_is_streamed_without_recording_a_turn() -> None:
    private_error = "Traceback from /srv/provider.py: secret-token"
    provider = FakeProvider([["Provisional answer.", ProviderError(private_error)], ["Recovered"]])
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=provider))
    session_id = create_session(client)

    failed = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Failed question"},
    )
    recovered = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Retry"},
    )

    assert parse_sse(failed.text) == [
        ("delta", {"text": "Provisional answer."}),
        ("error", {"message": PROVIDER_ERROR}),
    ]
    assert private_error not in failed.text
    assert recovered.status_code == 200
    recovered_prompt = json.dumps(provider.calls[1])
    assert "Failed question" not in recovered_prompt
    assert "Provisional answer." not in recovered_prompt


def test_turn_is_reported_stale_when_its_schedule_changes_during_streaming() -> None:
    class ScheduleUpdatingProvider(FakeProvider):
        update_schedule = lambda self: None

        async def stream_events(self, messages, tools=None):
            async for event in super().stream_events(messages, tools):
                yield event
            self.update_schedule()

    provider = ScheduleUpdatingProvider([["Obsolete answer."]])
    app = create_test_app(settings=make_settings(), provider=provider)
    client = AuthenticatedTestClient(app)
    session_id = create_session(client)
    owner = client.cookies[OWNER_COOKIE]
    provider.update_schedule = lambda: app.state.session_store.update_schedule(
        session_id,
        owner,
        "description: updated concurrently",
    )

    response = client.post(f"/sessions/{session_id}/messages", json={"message": "Edit it"})

    assert parse_sse(response.text) == [
        ("delta", {"text": "Obsolete answer."}),
        ("stale", {"message": STALE_TURN_ERROR}),
    ]


def test_sandbox_timeout_does_not_expose_exception_details() -> None:
    private_error = "Traceback from /srv/sandbox.py: internal-host"
    provider = FakeProvider([[SandboxTurnTimeoutError(private_error)]])
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=provider))
    session_id = create_session(client)

    response = client.post(f"/sessions/{session_id}/messages", json={"message": "Wait"})

    assert parse_sse(response.text) == [("error", {"message": SANDBOX_TURN_TIMEOUT_ERROR})]
    assert private_error not in response.text


def test_request_limits_are_enforced() -> None:
    client = AuthenticatedTestClient(
        create_test_app(
            settings=make_settings(max_message_chars=5, max_schedule_bytes=5),
            provider=FakeProvider(),
        )
    )
    schedule_response = client.post("/sessions", json={"schedule_yaml": "123456"})
    session_id = create_session(client, "ok")
    message_response = client.post(f"/sessions/{session_id}/messages", json={"message": "123456"})

    assert schedule_response.status_code == 413
    assert schedule_response.json()["detail"] == "Schedule is too large."
    assert message_response.status_code == 413
    assert message_response.json()["detail"] == "Message is too large."


def test_environment_configuration_requires_a_provider_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_PROVIDER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="AI_PROVIDER_API_KEY is required"):
        AiSettings.from_env()


def test_environment_configuration_allows_local_ai_without_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.delenv("AI_AUTH_TOKEN", raising=False)

    settings = AiSettings.from_env()
    client = TestClient(create_test_app(settings=settings, provider=FakeProvider()))

    assert settings.auth_required is False
    assert client.get("/capabilities").json()["auth"] == {"required": False, "scheme": "bearer"}
    assert client.post("/sessions", json={"schedule_yaml": "description: test"}).status_code == 201
    assert client.get("/docs").status_code == 200


@pytest.mark.parametrize("token", ["short", "   "])
def test_required_ai_auth_rejects_an_unsafe_token(token: str) -> None:
    with pytest.raises(ValueError, match="AI_AUTH_TOKEN must"):
        create_test_app(settings=make_settings(auth_token=token, auth_required=True), provider=FakeProvider())


def test_required_ai_auth_rejects_a_missing_token() -> None:
    with pytest.raises(ValueError, match="AI_AUTH_REQUIRED is set, so AI_AUTH_TOKEN must not be empty"):
        create_test_app(settings=make_settings(auth_token=None, auth_required=True), provider=FakeProvider())


def test_optional_short_ai_auth_token_still_enables_authentication(caplog: pytest.LogCaptureFixture) -> None:
    client = TestClient(create_test_app(settings=make_settings(auth_token="short"), provider=FakeProvider()))

    assert client.get("/capabilities").json()["auth"] == {"required": True, "scheme": "bearer"}
    assert client.post("/sessions", json={"schedule_yaml": "description: test"}).status_code == 401
    assert "AI_AUTH_TOKEN is shorter than 16 characters" in caplog.text


@pytest.mark.parametrize("raw_value, expected", [("true", True), ("1", True), ("false", False), ("0", False)])
def test_environment_configuration_reads_ai_auth_required(
    monkeypatch: pytest.MonkeyPatch, raw_value: str, expected: bool
) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_AUTH_REQUIRED", raw_value)

    assert AiSettings.from_env().auth_required is expected


def test_environment_configuration_rejects_invalid_ai_auth_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_AUTH_REQUIRED", "maybe")

    with pytest.raises(ValueError, match="AI_AUTH_REQUIRED must be a boolean"):
        AiSettings.from_env()


def test_environment_configuration_rejects_a_non_ascii_ai_auth_token() -> None:
    with pytest.raises(ValueError, match="AI_AUTH_TOKEN must contain only ASCII characters"):
        create_test_app(settings=make_settings(auth_token="long-enough-auth-token-密"), provider=FakeProvider())


def test_environment_configuration_enables_images_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.delenv("AI_ATTACHMENT_MODE", raising=False)
    monkeypatch.delenv("AI_DOCUMENT_ATTACHMENT_MODE", raising=False)

    assert AiSettings.from_env().attachment_mode == "images"
    assert AiSettings.from_env().document_attachment_mode == "text"


def test_environment_configuration_reads_provider_retry_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "e2b-key")
    monkeypatch.setenv("AI_PROVIDER_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("AI_PROVIDER_RETRY_BACKOFF_SECONDS", "0.25")

    settings = AiSettings.from_env()

    assert settings.provider_max_attempts == 4
    assert settings.provider_retry_backoff_seconds == 0.25


def test_environment_configuration_defaults_to_three_provider_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "e2b-key")
    monkeypatch.delenv("AI_PROVIDER_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("AI_PROVIDER_RETRY_BACKOFF_SECONDS", raising=False)

    settings = AiSettings.from_env()

    assert settings.provider_max_attempts == 3
    assert settings.provider_retry_backoff_seconds == 1.0


def test_environment_configuration_rejects_unknown_attachment_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_ATTACHMENT_MODE", "documents")

    with pytest.raises(ValueError, match="AI_ATTACHMENT_MODE must be one of: none, images"):
        AiSettings.from_env()


def test_environment_configuration_rejects_unknown_document_attachment_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_DOCUMENT_ATTACHMENT_MODE", "pdf")

    with pytest.raises(ValueError, match="AI_DOCUMENT_ATTACHMENT_MODE must be one of: none, text"):
        AiSettings.from_env()


def test_environment_configuration_reads_document_extraction_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_MAX_DOCUMENT_BYTES", "6000000")
    monkeypatch.setenv("AI_MAX_DOCUMENT_TEXT_CHARS", "60000")
    monkeypatch.setenv("AI_MAX_PDF_PAGES", "60")
    monkeypatch.setenv("AI_MAX_XLSX_SHEETS", "6")
    monkeypatch.setenv("AI_MAX_XLSX_CELLS", "6000")
    monkeypatch.setenv("AI_MAX_XLSX_UNCOMPRESSED_BYTES", "60000000")

    settings = AiSettings.from_env()

    assert settings.max_document_bytes == 6_000_000
    assert settings.max_document_text_chars == 60_000
    assert settings.max_pdf_pages == 60
    assert settings.max_xlsx_sheets == 6
    assert settings.max_xlsx_cells == 6_000
    assert settings.max_xlsx_uncompressed_bytes == 60_000_000


def test_environment_configuration_requires_e2b_key_when_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_SANDBOX_BACKEND", "e2b")
    monkeypatch.delenv("E2B_API_KEY", raising=False)

    with pytest.raises(ValueError, match="E2B_API_KEY is required"):
        AiSettings.from_env()


def test_environment_configuration_defaults_to_a_fifteen_minute_sandbox_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "e2b-key")
    monkeypatch.delenv("AI_SANDBOX_TURN_TIMEOUT_SECONDS", raising=False)

    assert AiSettings.from_env().sandbox_turn_timeout_seconds == 900


def test_environment_configuration_reads_e2b_sandbox_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "e2b-key")
    monkeypatch.setenv("E2B_TEMPLATE", "test-template")
    monkeypatch.setenv("AI_SANDBOX_COMMAND_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("AI_SANDBOX_TURN_TIMEOUT_SECONDS", "90")
    monkeypatch.setenv("AI_SANDBOX_CLEANUP_TIMEOUT_SECONDS", "6")
    monkeypatch.setenv("AI_SANDBOX_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("AI_SANDBOX_RETRY_BACKOFF_SECONDS", "0.25")
    monkeypatch.setenv("AI_SANDBOX_PAUSE_REQUEST_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("AI_SANDBOX_CONTROL_REQUEST_TIMEOUT_SECONDS", "1.5")
    monkeypatch.setenv("AI_SANDBOX_REAPER_INTERVAL_SECONDS", "45")

    settings = AiSettings.from_env()

    assert settings.sandbox_backend == "e2b"
    assert settings.e2b_api_key == "e2b-key"
    assert settings.e2b_template == "test-template"
    assert settings.sandbox_command_timeout_seconds == 4.5
    assert settings.sandbox_turn_timeout_seconds == 90
    assert settings.sandbox_cleanup_timeout_seconds == 6
    assert settings.sandbox_max_attempts == 4
    assert settings.sandbox_retry_backoff_seconds == 0.25
    assert settings.sandbox_pause_request_timeout_seconds == 4.5
    assert settings.sandbox_control_request_timeout_seconds == 1.5
    assert settings.sandbox_reaper_interval_seconds == 45


def test_environment_configuration_requires_a_sandbox_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_SANDBOX_BACKEND", "none")

    with pytest.raises(ValueError, match="AI_SANDBOX_BACKEND must be configured"):
        AiSettings.from_env()


class ScriptedToolProvider:
    """Return a scripted tool call, then a text answer."""

    def __init__(self, *turns) -> None:
        self._turns = list(turns)
        self.calls: list[list[ChatMessage]] = []

    async def stream_events(self, messages: Sequence[ChatMessage], tools=None) -> AsyncIterator[object]:
        self.calls.append(list(messages))
        turn = self._turns[min(len(self.calls) - 1, len(self._turns) - 1)]
        if isinstance(turn, BaseException):
            raise turn
        for event in turn:
            if isinstance(event, BaseException):
                raise event
            yield event


def rename_call() -> list[object]:
    """Ask Bash to give the first person a description."""
    arguments = json.dumps({"command": "python3 -c 'set P1 description to Head'"})
    return [ToolCallRequest((ToolCall("call_0", BASH_TOOL, arguments),))]


def rename_factory() -> FakeSandboxFactory:
    """Return a fake sandbox that applies the scripted description change."""

    def rename(_command: str, _timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
        current = backend.files[WORKSPACE_SCHEDULE].decode()
        backend.files[WORKSPACE_SCHEDULE] = current.replace(
            "  - id: P1\n    description: ''",
            "  - id: P1\n    description: Head",
            1,
        ).encode()
        return CommandResult("updated\n", "", 0)

    return FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=rename))


def proposing_client() -> tuple[TestClient, str, str]:
    """Run one proposing turn and return the client, session, and base revision."""
    provider = ScriptedToolProvider(rename_call(), [TextDelta("Renamed P1.")])
    client = AuthenticatedTestClient(
        create_test_app(
            settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT),
            provider=provider,
            sandbox_factory=rename_factory(),
        )
    )
    schedule = schedule_yaml()
    session_id = create_session(client, schedule)
    response = client.post(f"/sessions/{session_id}/messages", json={"message": "Rename P1."})
    assert response.status_code == 200
    return client, session_id, hashlib.sha256(schedule.encode("utf-8")).hexdigest()


def proposal_decision_context() -> tuple[
    TestClient,
    str,
    str,
    ScriptedToolProvider,
    FakeSandboxFactory,
]:
    """Create a proposal and expose the provider and sandboxes for a follow-up turn."""
    provider = ScriptedToolProvider(
        rename_call(),
        [TextDelta("Renamed P1.")],
        [TextDelta("Decision acknowledged.")],
    )
    factory = rename_factory()
    client = AuthenticatedTestClient(
        create_test_app(
            settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT),
            provider=provider,
            sandbox_factory=factory,
        )
    )
    schedule = schedule_yaml()
    session_id = create_session(client, schedule)
    response = client.post(f"/sessions/{session_id}/messages", json={"message": "Rename P1."})
    assert response.status_code == 200
    return client, session_id, hashlib.sha256(schedule.encode("utf-8")).hexdigest(), provider, factory


def test_a_tool_run_streams_tool_use_and_a_proposal() -> None:
    provider = ScriptedToolProvider(rename_call(), [TextDelta("Renamed P1.")])
    client = AuthenticatedTestClient(
        create_test_app(
            settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT),
            provider=provider,
            sandbox_factory=rename_factory(),
        )
    )
    session_id = create_session(client, schedule_yaml())

    response = client.post(f"/sessions/{session_id}/messages", json={"message": "Rename P1."})

    events = parse_sse(response.text)
    tool = next(data for name, data in events if name == "tool")
    assert tool["name"] == BASH_TOOL
    assert tool["ok"] is True
    assert "Head" in tool["arguments"]
    assert "passed trusted server-side validation" in tool["result"]
    schedule_change = next(data for name, data in events if name == "schedule_change")
    assert "description: Head" in schedule_change["schedule_yaml"]
    proposal = next(data for name, data in events if name == "proposal")
    assert "people.items[0].description" in proposal["diff"]
    assert not any(name == "proposal" and "schedule" in data for name, data in events)


def test_sandbox_cleanup_failure_does_not_commit_provisional_turn_or_proposal() -> None:
    provider = ScriptedToolProvider(
        rename_call(),
        [TextDelta("Provisional answer.")],
        [TextDelta("Recovered.")],
    )

    def rename(_command: str, _timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
        current = backend.files[WORKSPACE_SCHEDULE].decode()
        backend.files[WORKSPACE_SCHEDULE] = current.replace(
            "  - id: P1\n    description: ''",
            "  - id: P1\n    description: Head",
            1,
        ).encode()
        return CommandResult("updated\n", "", 0)

    def backend_factory(sandbox_id: str) -> FakeSandboxBackend:
        close_error = SandboxError("E2B cleanup failed") if sandbox_id == "fake-1" else None
        return FakeSandboxBackend(sandbox_id, command_handler=rename, close_error=close_error)

    factory = FakeSandboxFactory(backend_factory)
    client = AuthenticatedTestClient(
        create_test_app(
            settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT),
            provider=provider,
            sandbox_factory=factory,
        )
    )
    schedule = schedule_yaml()
    session_id = create_session(client, schedule)

    failed = client.post(f"/sessions/{session_id}/messages", json={"message": "Failed edit"})

    events = parse_sse(failed.text)
    assert [name for name, _ in events] == ["tool_start", "tool", "schedule_change", "delta", "error"]
    assert events[-1][1]["message"] == "The temporary AI sandbox failed. Please try again."
    revision = hashlib.sha256(schedule.encode("utf-8")).hexdigest()
    approval = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})
    assert approval.status_code == 404

    recovered = client.post(f"/sessions/{session_id}/messages", json={"message": "Retry"})

    assert ("delta", {"text": "Recovered."}) in parse_sse(recovered.text)
    recovered_prompt = json.dumps(provider.calls[2])
    assert "Failed edit" not in recovered_prompt
    assert "Provisional answer." not in recovered_prompt


def test_sandbox_command_failure_still_streams_the_requested_command() -> None:
    provider = ScriptedToolProvider(rename_call())

    def fail_command(*_args) -> CommandResult:
        raise SandboxError("E2B command failed")

    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=fail_command))
    client = AuthenticatedTestClient(
        create_test_app(
            settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT),
            provider=provider,
            sandbox_factory=factory,
        )
    )
    session_id = create_session(client, schedule_yaml())

    failed = client.post(f"/sessions/{session_id}/messages", json={"message": "Run an edit"})

    events = parse_sse(failed.text)
    assert [name for name, _ in events] == ["tool_start", "error"]
    assert events[0][1] == {
        "name": BASH_TOOL,
        "arguments": json.dumps({"command": "python3 -c 'set P1 description to Head'"}),
    }


def test_final_validation_failure_discards_the_turn_without_a_history_note() -> None:
    provider = ScriptedToolProvider(
        rename_call(),
        [TextDelta("Provisional invalid answer.")],
        [TextDelta("Recovered.")],
    )

    def invalidate(_command: str, _timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
        backend.files[WORKSPACE_SCHEDULE] = b"not: [valid"
        return CommandResult("updated\n", "", 0)

    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=invalidate))
    client = AuthenticatedTestClient(
        create_test_app(
            settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT),
            provider=provider,
            sandbox_factory=factory,
        )
    )
    schedule = schedule_yaml()
    session_id = create_session(client, schedule)

    failed = client.post(f"/sessions/{session_id}/messages", json={"message": "Invalid edit"})

    events = parse_sse(failed.text)
    assert [name for name, _ in events] == ["tool_start", "tool", "delta", "error"]
    assert events[1][1]["ok"] is False
    assert events[-1][1]["message"] == CANDIDATE_VALIDATION_ERROR

    recovered = client.post(f"/sessions/{session_id}/messages", json={"message": "Retry"})

    assert ("delta", {"text": "Recovered."}) in parse_sse(recovered.text)
    recovered_prompt = json.dumps(provider.calls[2])
    assert "Invalid edit" not in recovered_prompt
    assert "Provisional invalid answer." not in recovered_prompt
    assert factory.created[1].files[WORKSPACE_SCHEDULE] == schedule.encode()


def test_one_message_routes_through_a_fresh_backend_and_trusted_proposal() -> None:
    command = json.dumps(
        {
            "command": (
                "python3 - <<'PY'\n"
                "from pathlib import Path\n"
                "path = Path('/workspace/schedule.yaml')\n"
                "text = path.read_text()\n"
                'path.write_text(text.replace("description: \'\'", "description: Head", 1))\n'
                "PY"
            )
        }
    )
    provider = ScriptedToolProvider(
        [ToolCallRequest((ToolCall("call_0", BASH_TOOL, command),))],
        [TextDelta("I propose the description.")],
    )

    def edit(_command: str, _timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
        current = backend.files[WORKSPACE_SCHEDULE].decode()
        backend.files[WORKSPACE_SCHEDULE] = current.replace("description: ''", "description: Head", 1).encode()
        return CommandResult("updated\n", "", 0)

    factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, command_handler=edit))
    settings = make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT)
    client = AuthenticatedTestClient(create_test_app(settings=settings, provider=provider, sandbox_factory=factory))
    schedule = schedule_yaml()
    session_id = create_session(client, schedule)

    response = client.post(f"/sessions/{session_id}/messages", json={"message": "Set the description."})

    events = parse_sse(response.text)
    assert next(data for name, data in events if name == "tool")["name"] == BASH_TOOL
    assert "description: Head" in next(data for name, data in events if name == "schedule_change")["schedule_yaml"]
    assert next(data for name, data in events if name == "proposal")["diff"] == '- description: "" -> "Head"'
    assert factory.created[0].closed
    assert "`/workspace/schedule.yaml`" in provider.calls[0][0]["content"]
    assert "E2B" not in provider.calls[0][0]["content"]
    revision = hashlib.sha256(schedule.encode()).hexdigest()
    approved = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})
    assert approved.status_code == 200
    assert "description: Head" in approved.json()["schedule_yaml"]


def test_approval_returns_the_proposed_schedule_once() -> None:
    client, session_id, revision = proposing_client()

    approved = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})
    repeated = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})

    assert approved.status_code == 200
    assert "description: Head" in approved.json()["schedule_yaml"]
    assert repeated.status_code == 404


def test_approval_is_recorded_for_the_next_fresh_turn() -> None:
    client, session_id, revision, provider, factory = proposal_decision_context()

    approved = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})
    follow_up = client.post(f"/sessions/{session_id}/messages", json={"message": "Continue"})

    assert approved.status_code == 200
    assert follow_up.status_code == 200
    assert {"role": "user", "content": PROPOSAL_APPROVED_HISTORY} in provider.calls[2]
    assert b"description: Head" in factory.created[1].files[WORKSPACE_SCHEDULE]


def test_approval_is_refused_when_the_browser_holds_another_revision() -> None:
    client, session_id, _ = proposing_client()

    stale = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": "0" * 64})
    retried = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": "0" * 64})

    assert stale.status_code == 409
    assert "changed after this proposal" in stale.json()["detail"]
    assert retried.status_code == 404


def test_rejection_drops_the_proposal() -> None:
    client, session_id, revision, provider, factory = proposal_decision_context()

    rejected = client.post(f"/sessions/{session_id}/proposal/reject")
    repeated = client.post(f"/sessions/{session_id}/proposal/reject")
    approved = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})
    follow_up = client.post(f"/sessions/{session_id}/messages", json={"message": "Continue"})

    assert rejected.status_code == 204
    assert repeated.status_code == 204
    assert approved.status_code == 404
    assert follow_up.status_code == 200
    assert provider.calls[2].count({"role": "user", "content": PROPOSAL_REJECTED_HISTORY}) == 1
    assert factory.created[1].files[WORKSPACE_SCHEDULE] == schedule_yaml().encode()


def test_a_proposal_that_fails_revalidation_never_becomes_the_session_schedule() -> None:
    provider = FakeProvider([["Acknowledged."]])
    factory = FakeSandboxFactory()
    app = create_test_app(
        settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT),
        provider=provider,
        sandbox_factory=factory,
    )
    client = AuthenticatedTestClient(app)
    store = app.state.session_store
    schedule = schedule_yaml()
    session_id = create_session(client, schedule)
    revision = hashlib.sha256(schedule.encode("utf-8")).hexdigest()
    owner = client.cookies[OWNER_COOKIE]
    broken_payload = base_schedule_payload()
    broken_payload["preferences"][1]["person"] = ["P9"]
    _, _, base_revision = store.begin(session_id, owner)
    assert store.finish(
        session_id,
        "Break it",
        "Broken proposal",
        (schedule_yaml(broken_payload), "broken diff"),
        base_revision=base_revision,
    ).proposal_saved

    approved = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})
    retried = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})
    follow_up = client.post(f"/sessions/{session_id}/messages", json={"message": "Continue"})

    assert approved.status_code == 409
    assert "no longer valid" in approved.json()["detail"]
    assert retried.status_code == 404
    assert follow_up.status_code == 200
    assert factory.created[0].files[WORKSPACE_SCHEDULE] == schedule.encode()
    assert {"role": "user", "content": PROPOSAL_INVALID_HISTORY} in provider.calls[0]


def test_a_newer_schedule_replaces_the_snapshot_and_the_proposal() -> None:
    client, session_id, revision = proposing_client()
    payload = base_schedule_payload()
    payload["description"] = "Ward A"

    updated = client.put(f"/sessions/{session_id}/schedule", json={"schedule_yaml": schedule_yaml(payload)})
    approved = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})

    assert updated.status_code == 204
    assert approved.status_code == 404


def test_active_turn_cannot_save_a_proposal_after_another_proposal_is_approved() -> None:
    app = create_test_app(settings=make_settings(), provider=FakeProvider())
    store = app.state.session_store
    original = schedule_yaml()
    first_proposal = original.replace("description: ''", "description: First", 1)
    stale_proposal = original.replace("description: ''", "description: Stale", 1)
    session = store.create("browser-owner", original)
    _, _, original_revision = store.begin(session.id, "browser-owner")
    assert store.finish(
        session.id,
        "First edit",
        "First proposal",
        (first_proposal, "first diff"),
        base_revision=original_revision,
    ).proposal_saved
    _, _, active_turn_revision = store.begin(session.id, "browser-owner")

    store.adopt_proposal(session.id, "browser-owner", original_revision)
    completion = store.finish(
        session.id,
        "Stale edit",
        "Stale proposal",
        (stale_proposal, "stale diff"),
        base_revision=active_turn_revision,
    )

    assert not completion.turn_saved
    assert session.history == [
        ChatMessage(role="user", content="First edit"),
        ChatMessage(role="assistant", content="First proposal"),
        ChatMessage(role="user", content=PROPOSAL_APPROVED_HISTORY),
    ]
    with pytest.raises(HTTPException) as exc_info:
        store.adopt_proposal(session.id, "browser-owner", active_turn_revision)
    assert exc_info.value.status_code == 404


def test_sessions_are_private_to_their_browser() -> None:
    _, session_id, revision = proposing_client()
    other = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))

    assert other.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision}).status_code == 404
    assert other.put(f"/sessions/{session_id}/schedule", json={"schedule_yaml": "a: 1"}).status_code == 404


def test_approval_allows_a_schedule_the_user_had_not_finished() -> None:
    payload = base_schedule_payload()
    payload["preferences"] = []
    provider = ScriptedToolProvider(rename_call(), [TextDelta("Renamed P1.")])
    client = AuthenticatedTestClient(
        create_test_app(
            settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT),
            provider=provider,
            sandbox_factory=rename_factory(),
        )
    )
    schedule = schedule_yaml(payload)
    session_id = create_session(client, schedule)
    client.post(f"/sessions/{session_id}/messages", json={"message": "Rename P1."})

    approved = client.post(
        f"/sessions/{session_id}/proposal/approve",
        json={"base_sha256": hashlib.sha256(schedule.encode("utf-8")).hexdigest()},
    )

    assert approved.status_code == 200
    assert "description: Head" in approved.json()["schedule_yaml"]


def test_the_prompt_summarizes_the_schedule_instead_of_sending_it() -> None:
    provider = FakeProvider()
    client = AuthenticatedTestClient(
        create_test_app(settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT), provider=provider)
    )
    schedule = schedule_yaml()
    session_id = create_session(client, schedule)

    client.post(f"/sessions/{session_id}/messages", json={"message": "How many people?"})

    system_prompt = provider.calls[0][0]["content"]
    normalized_prompt = " ".join(system_prompt.split())
    assert "2 people, 2 shift types, 2 preferences" in normalized_prompt
    assert "Group ids: people PEOPLE" in normalized_prompt
    assert "Dates run from 2026-01-01 to 2026-01-02" in normalized_prompt
    assert "Your tools are `read`, `bash`, `edit`, and `write`" in normalized_prompt
    assert "Use `read` to examine files" in normalized_prompt
    assert "Use `edit` for precise changes with unique exact text" in normalized_prompt
    assert "multiple disjoint replacements" in normalized_prompt
    assert "Use `write` only for new files or complete rewrites" in normalized_prompt
    assert "It overwrites the whole target file" in normalized_prompt
    assert "read one task-sized document" in normalized_prompt
    assert "`/reference/schema-core.md`" in normalized_prompt
    assert "`/reference/schema-preferences.md`" in normalized_prompt
    assert "`/reference/schema-export.md`" in normalized_prompt
    assert "not the PyYAML `yaml` module" in normalized_prompt
    assert "Preserve existing fields" in normalized_prompt
    assert "exact selectors" in normalized_prompt
    assert "trusted validation status" in normalized_prompt
    assert "explicit user approval" in normalized_prompt
    assert "say it does not exist and make no change" in normalized_prompt
    assert "cannot run the scheduling optimizer" in normalized_prompt
    assert "do not probe installed programs" in normalized_prompt
    summary = system_prompt.split("Current schedule summary:\n")[1]
    assert len(summary) < len(schedule) / 2


def test_a_browser_may_send_the_newer_schedule_across_origins() -> None:
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))

    preflight = client.options(
        "/sessions/any/schedule",
        headers={
            "Origin": "http://localhost:3005",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert preflight.status_code == 200
    assert "PUT" in preflight.headers["access-control-allow-methods"]
