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
import io
import json
import logging
import subprocess
import threading
import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from unittest.mock import ANY, AsyncMock
from uuid import uuid4

import httpx
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
    configure_request_logging,
    request_logger,
)
from nurse_scheduling.ai.app import create_app as create_ai_app
from nurse_scheduling.ai.background import build_provider_messages
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.history import ChatHistory
from nurse_scheduling.ai.optimizer import OPTIMIZER_TOOL, OptimizerArtifact, OptimizerJobPayload
from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.pi.read import READ_TOOL
from nurse_scheduling.ai.provider import ChatMessage, ProviderError, TextDelta, ToolCall, ToolCallRequest
from nurse_scheduling.ai.sandbox import CommandResult, SandboxError
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory
from nurse_scheduling.ai.sandbox_agent import (
    WORKSPACE_PENDING_DIFF,
    WORKSPACE_PENDING_PROPOSAL,
    WORKSPACE_SCHEDULE,
    SandboxTurnTimeoutError,
)
from nurse_scheduling.server.auth import AuthCredential

from .ai_test_helper import (
    SCHEDULE_BYTE_LIMIT,
    base_schedule_payload,
    optimizer_workbook_bytes,
    parse_schedule,
    schedule_yaml,
)

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
AI_AUTH_TOKEN = "ai-shared-test-token"
AI_AUTH_HEADERS = {"Authorization": f"Bearer {AI_AUTH_TOKEN}"}
AI_AUTH_TOKENS = (
    AuthCredential(id="institution-a", token="institution-a-ai-token"),
    AuthCredential(id="person_b", token="person-b-ai-token"),
)


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


def create_test_app(*, settings: AiSettings, provider, sandbox_factory=None, optimizer_backend=None):
    """Create the app with a fake disposable sandbox unless a test supplies one."""
    return create_ai_app(
        settings=settings,
        provider=provider,
        sandbox_factory=sandbox_factory or FakeSandboxFactory(),
        optimizer_backend=optimizer_backend,
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


def test_e2b_template_is_built_before_ai_server_is_ready(monkeypatch):
    calls = []
    monkeypatch.setattr("nurse_scheduling.ai.sandbox.e2b.E2BSandboxFactory.start_cleanup", AsyncMock())
    monkeypatch.setattr("nurse_scheduling.ai.sandbox.e2b.E2BSandboxFactory.stop_cleanup", AsyncMock())
    monkeypatch.setattr(
        "nurse_scheduling.ai.sandbox.e2b.subprocess.run", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    settings = make_settings(sandbox_backend="e2b", e2b_api_key="test-e2b-key", e2b_template="test-template")
    with AuthenticatedTestClient(create_ai_app(settings=settings, provider=FakeProvider())) as client:
        assert client.get("/ready").status_code == 200

    assert len(calls) == 1
    args, kwargs = calls[0]
    build_script = Path(args[0][1])
    assert build_script.name == "build_template.py"
    assert build_script.parent.name == "e2b"
    assert build_script.parent.parent.name == "docker"
    assert kwargs["check"] is True
    assert kwargs["env"]["E2B_API_KEY"] == "test-e2b-key"
    assert kwargs["env"]["E2B_TEMPLATE"] == "test-template"


def test_e2b_template_build_failure_prevents_startup(monkeypatch):
    monkeypatch.setattr("nurse_scheduling.ai.sandbox.e2b.E2BSandboxFactory.start_cleanup", AsyncMock())
    monkeypatch.setattr("nurse_scheduling.ai.sandbox.e2b.E2BSandboxFactory.stop_cleanup", AsyncMock())

    def fail_build(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, "build_template.py")

    monkeypatch.setattr("nurse_scheduling.ai.sandbox.e2b.subprocess.run", fail_build)
    settings = make_settings(sandbox_backend="e2b", e2b_api_key="test-e2b-key")
    with (
        pytest.raises(subprocess.CalledProcessError),
        AuthenticatedTestClient(create_ai_app(settings=settings, provider=FakeProvider())),
    ):
        pass


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
        ("get", "/sessions/missing/events", None),
        ("post", "/sessions/missing/stop", None),
        ("get", "/sessions/missing/optimizations/opt-missing/xlsx", None),
        ("post", "/sessions/missing/messages/queue", {"message_id": "queued-1", "message": "Hello"}),
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


def test_ai_cors_preflight_allows_resuming_background_events() -> None:
    client = TestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))

    response = client.options(
        "/sessions/example/events",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,last-event-id",
        },
    )

    assert response.status_code == 200
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed
    assert "last-event-id" in allowed


def test_ai_generated_api_docs_are_disabled() -> None:
    client = TestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))

    for path in ("/openapi.json", "/docs", "/redoc"):
        assert client.get(path, headers=AI_AUTH_HEADERS).status_code == 404


def create_session(client: TestClient, schedule_yaml: str = "description: test") -> str:
    """Create a session and return its public UUID."""
    response = client.post("/sessions", json={"schedule_yaml": schedule_yaml})
    assert response.status_code == 201
    return response.json()["id"]


def test_active_session_drains_all_queued_steering_messages() -> None:
    app = create_test_app(settings=make_settings(), provider=FakeProvider())
    client = AuthenticatedTestClient(app)
    session_id = create_session(client)
    owner = client.cookies[OWNER_COOKIE]
    app.state.session_store.begin(session_id, owner)

    first_response = client.post(
        f"/sessions/{session_id}/messages/queue",
        json={"message_id": "queued-1", "message": "Focus on P2 instead."},
    )
    second_response = client.post(
        f"/sessions/{session_id}/messages/queue",
        json={"message_id": "queued-2", "message": "Also compare P3."},
    )

    assert first_response.status_code == second_response.status_code == 202
    assert app.state.session_store.take_steering(session_id, False) == [
        ("queued-1", "Focus on P2 instead."),
        ("queued-2", "Also compare P3."),
    ]
    app.state.session_store.abort(session_id)


def test_message_request_logs_question_to_stdout(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="nurse_scheduling.ai.requests")
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))
    session_id = create_session(client)

    response = client.post(f"/sessions/{session_id}/messages", json={"message": "Hello"})

    assert response.status_code == 200
    output = caplog.text
    assert f'AI request started session_id={session_id} question_chars=5 question="Hello" files=0' in output


def test_question_previews_can_be_turned_off_without_silencing_the_logger(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="nurse_scheduling.ai.requests")
    client = AuthenticatedTestClient(
        create_test_app(settings=make_settings(request_log_enabled=False), provider=FakeProvider())
    )
    session_id = create_session(client)

    response = client.post(f"/sessions/{session_id}/messages", json={"message": "Hello"})

    assert response.status_code == 200
    # Chat text must be suppressible, and the logger must stay usable for real problems.
    assert "Hello" not in caplog.text
    assert "AI request started" not in caplog.text
    request_logger.warning("still reported")
    assert "still reported" in caplog.text


def test_request_logging_leaves_an_operator_configured_root_alone() -> None:
    root_handler = logging.StreamHandler(io.StringIO())
    logging.getLogger().addHandler(root_handler)
    try:
        configure_request_logging(True)
        assert request_logger.handlers == []
        assert request_logger.level == logging.INFO
    finally:
        logging.getLogger().removeHandler(root_handler)


def test_message_request_log_flattens_and_truncates_long_questions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="nurse_scheduling.ai.requests")
    client = AuthenticatedTestClient(
        create_test_app(settings=make_settings(max_message_chars=500), provider=FakeProvider())
    )
    session_id = create_session(client)
    question = f"First line\n{'x' * 250}"

    response = client.post(f"/sessions/{session_id}/messages", json={"message": question})

    assert response.status_code == 200
    output = caplog.text
    assert "question_chars=261" in output
    assert 'question="First line ' in output
    assert "\\n" not in output
    assert f'{"x" * 186}..."' in output
    assert "x" * 187 not in output


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
def test_client_disconnect_cancels_the_turn_and_closes_its_sandbox(wait_stage: str, monkeypatch) -> None:
    saved = []
    monkeypatch.setattr(ChatHistory, "start_turn", lambda *_args: None)
    monkeypatch.setattr(ChatHistory, "finish_turn", lambda _self, *args: saved.append(args))

    async def exercise() -> tuple[FakeSandboxBackend | None, bool, bool, list[ChatMessage]]:
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
        app = create_test_app(
            settings=make_settings(history_postgres_url="test"),
            provider=WaitingProvider(),
            sandbox_factory=factory,
        )
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

        backend = factory.created[0] if factory.created else None
        return backend, operation_cancelled.is_set(), session.active, list(session.history)

    backend, operation_cancelled, session_active, history = asyncio.run(exercise())

    assert operation_cancelled
    if wait_stage == "provider":
        assert backend is None
    else:
        assert backend is not None
        assert backend.closed
        assert backend.close_calls == 1
    assert not session_active
    assert history == []
    assert len(saved) == 1
    assert saved[0][2] == "cancelled"


def test_stop_endpoint_cancels_an_active_assistant_turn() -> None:
    async def exercise() -> tuple[int, bool]:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class WaitingProvider:
            async def stream_events(self, _messages, tools=None):
                started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancelled.set()
                    raise
                yield TextDelta("unreachable")

        app = create_test_app(settings=make_settings(), provider=WaitingProvider())
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {AI_AUTH_TOKEN}"},
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": schedule_yaml()})).json()["id"]
            turn = asyncio.create_task(
                client.post(f"/sessions/{session_id}/messages", json={"message": "Keep working"})
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            stopped = await client.post(f"/sessions/{session_id}/stop")
            await asyncio.wait_for(cancelled.wait(), timeout=1)
            await asyncio.gather(turn, return_exceptions=True)
            return stopped.status_code, app.state.session_store._sessions[session_id].active

    status_code, session_active = asyncio.run(exercise())

    assert status_code == 202
    assert not session_active


def test_stop_cancels_background_turn_waiting_behind_foreground_turn() -> None:
    async def exercise() -> tuple[int, bool, int, bool]:
        foreground_started = asyncio.Event()
        foreground_cancelled = asyncio.Event()

        class WaitingProvider:
            def __init__(self) -> None:
                self.calls = 0

            async def stream_events(self, _messages, tools=None):
                self.calls += 1
                foreground_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    foreground_cancelled.set()
                    raise
                yield TextDelta("unreachable")

        provider = WaitingProvider()
        app = create_test_app(settings=make_settings(), provider=provider)
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {AI_AUTH_TOKEN}"},
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": schedule_yaml()})).json()["id"]
            foreground = asyncio.create_task(
                client.post(f"/sessions/{session_id}/messages", json={"message": "Keep working"})
            )
            await asyncio.wait_for(foreground_started.wait(), timeout=1)
            background = asyncio.create_task(
                app.state.session_optimizer._on_completion(session_id, "Optimizer finished", None)
            )
            await asyncio.sleep(0)

            stopped = await client.post(f"/sessions/{session_id}/stop")
            await asyncio.wait_for(foreground_cancelled.wait(), timeout=1)
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(background, timeout=1)
            await asyncio.gather(foreground, return_exceptions=True)
            return (
                stopped.status_code,
                app.state.session_store._sessions[session_id].active,
                provider.calls,
                app.state.turn_locks[session_id].locked(),
            )

    status_code, session_active, provider_calls, lock_held = asyncio.run(exercise())

    assert status_code == 202
    assert not session_active
    assert provider_calls == 1
    assert not lock_held


def test_stop_before_stream_registration_cancels_the_reserved_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    async def exercise() -> tuple[int, bool, int]:
        waiting_for_artifact = asyncio.Event()
        release_artifact = asyncio.Event()
        provider = FakeProvider()
        app = create_test_app(settings=make_settings(), provider=provider)

        async def delayed_artifact(_session_id: str) -> None:
            waiting_for_artifact.set()
            await release_artifact.wait()

        monkeypatch.setattr(app.state.session_optimizer, "latest_result_artifact", delayed_artifact)
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {AI_AUTH_TOKEN}"},
            ) as client,
        ):
            session_id = (await client.post("/sessions", json={"schedule_yaml": schedule_yaml()})).json()["id"]
            turn = asyncio.create_task(client.post(f"/sessions/{session_id}/messages", json={"message": "Stop now"}))
            await asyncio.wait_for(waiting_for_artifact.wait(), timeout=1)
            stopped = await client.post(f"/sessions/{session_id}/stop")
            release_artifact.set()
            await asyncio.gather(turn, return_exceptions=True)
            return stopped.status_code, app.state.session_store._sessions[session_id].active, len(provider.calls)

    status_code, session_active, provider_calls = asyncio.run(exercise())

    assert status_code == 202
    assert not session_active
    assert provider_calls == 0


def test_disconnect_before_stream_iteration_releases_the_session(monkeypatch) -> None:
    saved = []
    monkeypatch.setattr(ChatHistory, "start_turn", lambda *_args: None)
    monkeypatch.setattr(ChatHistory, "finish_turn", lambda _self, *args: saved.append(args))

    async def exercise() -> bool:
        app = create_test_app(settings=make_settings(history_postgres_url="test"), provider=FakeProvider())
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
            # Let the queued disconnect cancel response startup before iteration.
            await asyncio.sleep(0)

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
    assert len(saved) == 1
    assert saved[0][2] == "cancelled"


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
    # Schedule facts require a tool read.
    system_prompt = " ".join(prompt[0]["content"].split())
    assert "Alice" not in system_prompt
    assert "schedule.yaml is available at /workspace/schedule.yaml" in system_prompt
    assert "/workspace/optimizer-results/optimized-schedule.xlsx" in system_prompt


def test_valid_owner_cookie_lifetime_is_refreshed() -> None:
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))
    owner = "b6d00cf8-1c7b-49b6-ab06-e162a54de489"
    client.cookies.set(OWNER_COOKIE, owner)

    response = client.post("/sessions", json={"schedule_yaml": "description: test"})

    assert response.status_code == 201
    set_cookie = response.headers["set-cookie"]
    assert f"{OWNER_COOKIE}={owner}" in set_cookie
    assert "Max-Age=172800" in set_cookie


def test_invalid_owner_cookie_is_not_reflected() -> None:
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))
    client.cookies.set(OWNER_COOKIE, "browser-supplied-owner")

    response = client.post("/sessions", json={"schedule_yaml": "description: test"})

    assert response.status_code == 201
    set_cookie = response.headers["set-cookie"]
    assert "browser-supplied-owner" not in set_cookie
    assert "Max-Age=172800" in set_cookie


def test_capabilities_report_configured_attachment_limits() -> None:
    client = AuthenticatedTestClient(
        create_test_app(
            settings=make_settings(
                max_attachment_files=5,
                max_attachment_bytes=4321,
            ),
            provider=FakeProvider(),
        )
    )

    response = client.get("/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "file_attachments": {
            "enabled": True,
            "max_files": 5,
            "max_bytes_per_file": 4321,
        },
        "session_retention_seconds": 172800,
        "auth": {"required": True, "scheme": "bearer"},
    }


def test_session_status_reports_sliding_lifetime_without_refreshing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr("nurse_scheduling.ai.app.time.monotonic", lambda: now)
    client = AuthenticatedTestClient(
        create_test_app(settings=make_settings(session_ttl_seconds=20), provider=FakeProvider())
    )
    session_id = create_session(client)

    now = 105.0
    first = client.get(f"/sessions/{session_id}")
    now = 110.0
    second = client.get(f"/sessions/{session_id}")
    message = client.post(f"/sessions/{session_id}/messages", json={"message": "Keep this chat active."})

    assert first.json() == {"expires_in_seconds": 15}
    assert second.json() == {"expires_in_seconds": 10}
    assert message.status_code == 200
    assert "Max-Age=20" in message.headers["set-cookie"]

    now = 120.0
    assert client.get(f"/sessions/{session_id}").json() == {"expires_in_seconds": 10}

    now = 131.0
    expired = client.get(f"/sessions/{session_id}")
    assert expired.status_code == 404
    assert expired.json()["detail"] == "Chat session not found."


def test_expiring_a_session_releases_its_turn_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr("nurse_scheduling.ai.app.time.monotonic", lambda: now)
    app = create_test_app(settings=make_settings(session_ttl_seconds=20), provider=FakeProvider())
    client = AuthenticatedTestClient(app)
    session_id = create_session(client)

    active = client.post(f"/sessions/{session_id}/messages", json={"message": "Keep this chat active."})
    assert active.status_code == 200
    assert session_id in app.state.turn_locks

    now = 131.0
    assert client.get(f"/sessions/{session_id}").status_code == 404
    assert app.state.turn_locks == {}

    unknown = client.post(f"/sessions/{uuid4()}/messages", json={"message": "No such chat."})
    assert unknown.status_code == 404
    assert app.state.turn_locks == {}


def test_finishing_a_turn_keeps_the_deadline_set_when_it_started(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr("nurse_scheduling.ai.app.time.monotonic", lambda: now)
    app = create_test_app(settings=make_settings(session_ttl_seconds=20), provider=FakeProvider())
    store = app.state.session_store
    owner = "b6d00cf8-1c7b-49b6-ab06-e162a54de489"
    session = store.create(owner, schedule_yaml())

    now = 105.0
    _, _, revision, _, _ = store.begin(session.id, owner)
    assert session.expires_at == 125.0

    now = 115.0
    assert store.finish(session.id, "Question", "Answer", base_revision=revision).turn_saved
    assert session.expires_at == 125.0


def test_unchanged_schedule_renews_session_with_owner_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 100.0
    monkeypatch.setattr("nurse_scheduling.ai.app.time.monotonic", lambda: now)
    app = create_test_app(settings=make_settings(session_ttl_seconds=20), provider=FakeProvider())
    client = AuthenticatedTestClient(app)
    schedule = schedule_yaml()
    session_id = create_session(client, schedule)

    now = 110.0
    response = client.put(f"/sessions/{session_id}/schedule", json={"schedule_yaml": schedule})

    assert response.status_code == 204
    assert "Max-Age=20" in response.headers["set-cookie"]
    assert app.state.session_store.status(session_id, client.cookies.get(OWNER_COOKIE)) == 20


def test_legacy_attachment_fields_are_rejected() -> None:
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=FakeProvider()))
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        data={"message": "Question"},
        files={"images": ("ward.png", PNG_BYTES, "image/png")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unexpected multipart field."


def test_arbitrary_file_is_available_in_the_disposable_sandbox() -> None:
    read_manifest = [
        ToolCallRequest((ToolCall("call_0", READ_TOOL, json.dumps({"path": "/workspace/attachments/manifest.json"})),))
    ]
    provider = ScriptedToolProvider(read_manifest, [TextDelta("I inspected the custom file.")])
    factory = FakeSandboxFactory()
    client = AuthenticatedTestClient(
        create_test_app(settings=make_settings(), provider=provider, sandbox_factory=factory)
    )
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        data={"message": "Inspect this custom file."},
        files={"files": ("archive.custom", b"arbitrary bytes", "application/x-custom")},
    )

    assert response.status_code == 200
    assert "I inspected the custom file." in response.text
    backend = factory.created[0]
    manifest = json.loads(backend.files["/workspace/attachments/manifest.json"])
    uploaded = manifest["attachments"][0]
    assert uploaded["original_filename"] == "archive.custom"
    assert uploaded["media_type"] == "application/x-custom"
    assert backend.files[uploaded["path"]] == b"arbitrary bytes"
    assert "/workspace/attachments/manifest.json" in provider.calls[0][0]["content"]


@pytest.mark.parametrize(
    ("settings", "files", "expected_detail"),
    [
        (
            {"max_attachment_bytes": 3},
            [("files", ("archive.custom", b"data", "application/x-custom"))],
            "File attachment is too large.",
        ),
        (
            {"max_attachment_files": 2},
            [
                ("files", ("one.custom", b"1", "application/x-custom")),
                ("files", ("two.custom", b"2", "application/x-custom")),
                ("files", ("three.custom", b"3", "application/x-custom")),
            ],
            "Too many file attachments.",
        ),
    ],
)
def test_arbitrary_file_limits(
    settings: dict[str, object],
    files: list[tuple[str, tuple[str, bytes, str]]],
    expected_detail: str,
) -> None:
    client = AuthenticatedTestClient(create_test_app(settings=make_settings(**settings), provider=FakeProvider()))
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        data={"message": "Inspect these files."},
        files=files,
    )

    assert response.status_code == 413
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


def test_turn_is_reported_stale_when_its_schedule_changes_during_streaming(monkeypatch) -> None:
    saved = []
    monkeypatch.setattr(ChatHistory, "start_turn", lambda *_args: None)
    monkeypatch.setattr(ChatHistory, "finish_turn", lambda _self, *args: saved.append(args))

    class ScheduleUpdatingProvider(FakeProvider):
        update_schedule = lambda self: None

        async def stream_events(self, messages, tools=None):
            async for event in super().stream_events(messages, tools):
                yield event
            self.update_schedule()

    provider = ScheduleUpdatingProvider([["Obsolete answer."]])
    app = create_test_app(settings=make_settings(history_postgres_url="test"), provider=provider)
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
    assert len(saved) == 1
    assert saved[0][1:3] == ("Obsolete answer.", "stale")


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
    monkeypatch.delenv("AI_AUTH_TOKENS", raising=False)

    settings = AiSettings.from_env()
    client = TestClient(create_test_app(settings=settings, provider=FakeProvider()))

    assert settings.auth_required is False
    assert client.get("/capabilities").json()["auth"] == {"required": False, "scheme": "bearer"}
    assert client.post("/sessions", json={"schedule_yaml": "description: test"}).status_code == 201
    assert client.get("/docs").status_code == 200


@pytest.mark.parametrize(
    "token,error",
    [("short", "AI_AUTH_TOKEN must"), ("   ", "AI_AUTH_TOKEN or AI_AUTH_TOKENS")],
)
def test_required_ai_auth_rejects_an_unsafe_token(token: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        create_test_app(settings=make_settings(auth_token=token, auth_required=True), provider=FakeProvider())


def test_required_ai_auth_rejects_a_missing_token() -> None:
    with pytest.raises(ValueError, match="AI_AUTH_REQUIRED is set, so AI_AUTH_TOKEN or AI_AUTH_TOKENS"):
        create_test_app(settings=make_settings(auth_token=None, auth_required=True), provider=FakeProvider())


def test_ai_routes_accept_each_identified_token_without_a_legacy_token(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="nurse_scheduling.ai")
    client = TestClient(
        create_test_app(
            settings=make_settings(auth_token=None, auth_tokens=AI_AUTH_TOKENS, auth_required=True),
            provider=FakeProvider(),
        )
    )

    for credential in AI_AUTH_TOKENS:
        response = client.post(
            "/sessions",
            json={"schedule_yaml": "description: test"},
            headers={"Authorization": f"Bearer {credential.token}"},
        )
        assert response.status_code == 201
        assert client.app.state.auth_registry.authenticate(credential.token).id == credential.id

    assert (
        client.post(
            "/sessions",
            json={"schedule_yaml": "description: test"},
            headers={"Authorization": "Bearer revoked-ai-token"},
        ).status_code
        == 401
    )
    assert "auth_credential_id=institution-a" in caplog.text
    assert "auth_credential_id=person_b" in caplog.text


def test_environment_configuration_loads_identified_ai_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.delenv("AI_AUTH_TOKEN", raising=False)
    monkeypatch.setenv(
        "AI_AUTH_TOKENS",
        '{"institution-a":"institution-a-ai-token","person_b":"person-b-ai-token"}',
    )

    settings = AiSettings.from_env()

    assert settings.auth_tokens == AI_AUTH_TOKENS


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


def test_environment_configuration_reads_attachment_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "e2b-key")
    monkeypatch.setenv("AI_MAX_ATTACHMENT_FILES", "6")
    monkeypatch.setenv("AI_MAX_ATTACHMENT_BYTES", "6000000")

    settings = AiSettings.from_env()

    assert settings.max_attachment_files == 6
    assert settings.max_attachment_bytes == 6_000_000


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


def test_environment_configuration_defaults_to_two_day_session_retention(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "e2b-key")
    monkeypatch.delenv("AI_SESSION_TTL_SECONDS", raising=False)

    assert AiSettings.from_env().session_ttl_seconds == 48 * 60 * 60


def test_environment_configuration_reads_optimizer_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_OPTIMIZER_BASE_URL", "http://optimizer:8000/")
    monkeypatch.setenv("AI_OPTIMIZER_AUTH_TOKEN", "optimizer-token")
    monkeypatch.setenv("AI_OPTIMIZER_POLL_INTERVAL_SECONDS", "0.25")
    monkeypatch.setenv("AI_OPTIMIZER_REQUEST_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("AI_OPTIMIZER_DEFAULT_TIMEOUT_SECONDS", "420")
    monkeypatch.setenv("AI_OPTIMIZER_MAX_RUNS_PER_SESSION", "7")
    monkeypatch.setenv("AI_OPTIMIZER_MAX_RESULT_BYTES", "9000000")
    monkeypatch.setenv("AI_OPTIMIZER_RESULT_CACHE_BYTES", "80000000")

    settings = AiSettings.from_env()

    assert settings.optimizer_base_url == "http://optimizer:8000"
    assert settings.optimizer_auth_token == "optimizer-token"
    assert settings.optimizer_poll_interval_seconds == 0.25
    assert settings.optimizer_request_timeout_seconds == 12
    assert settings.optimizer_default_timeout_seconds == 420
    assert settings.optimizer_max_runs_per_session == 7
    assert settings.optimizer_max_result_bytes == 9_000_000
    assert settings.optimizer_result_cache_bytes == 80_000_000


def test_optimizer_defaults_are_always_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_OPTIMIZER_BASE_URL", "")
    monkeypatch.delenv("AI_OPTIMIZER_MAX_RUNS_PER_SESSION", raising=False)

    settings = AiSettings.from_env()

    assert settings.optimizer_base_url == "http://localhost:8000"
    assert settings.optimizer_max_runs_per_session == 50


def test_chat_history_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.delenv("AI_MAX_HISTORY_MESSAGES", raising=False)

    assert AiSettings.from_env().max_history_messages == 1000


def test_a_trimmed_prompt_history_is_reported_to_the_client() -> None:
    provider = FakeProvider([["First answer."], ["Second answer."], ["Third answer."]])
    settings = make_settings(max_history_chars=120)
    client = AuthenticatedTestClient(create_test_app(settings=settings, provider=provider))
    session_id = create_session(client)

    first = client.post(f"/sessions/{session_id}/messages", json={"message": "A" * 100})
    second = client.post(f"/sessions/{session_id}/messages", json={"message": "B" * 100})
    third = client.post(f"/sessions/{session_id}/messages", json={"message": "C" * 100})

    assert [event for event, _ in parse_sse(first.text) if event == "history_trimmed"] == []
    trimmed = [payload for event, payload in parse_sse(third.text) if event == "history_trimmed"]
    assert len(trimmed) == 1
    assert trimmed[0]["dropped"] > 0
    # The oldest exchange is dropped from the prompt while the newest survives.
    latest_prompt = json.dumps(provider.calls[-1])
    assert "A" * 100 not in latest_prompt
    assert "C" * 100 in latest_prompt
    assert second.status_code == 200


def test_history_prompt_budget_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.delenv("AI_MAX_HISTORY_CHARS", raising=False)

    assert AiSettings.from_env().max_history_chars == 200_000


def test_a_long_history_is_trimmed_to_the_newest_messages_that_fit_the_prompt() -> None:
    history = [ChatMessage(role="user", content=f"{index:03d} {'x' * 200}") for index in range(50)]

    messages = build_provider_messages(history, "description: schedule\n", "Latest question.", max_history_chars=1000)

    assert messages[0]["role"] == "system"
    assert messages[-1]["content"] == "Latest question."
    retained = messages[1:-1]
    assert 0 < len(retained) < len(history)
    # The newest messages survive so the model keeps the most relevant context.
    assert retained[-1]["content"] == history[-1]["content"]
    assert retained[0]["content"] == history[len(history) - len(retained)]["content"]
    assert sum(len(json.dumps(message, ensure_ascii=False)) for message in retained) <= 1000


def test_a_short_history_reaches_the_prompt_unchanged() -> None:
    history = [ChatMessage(role="user", content="Who works Monday?"), ChatMessage(role="assistant", content="Alice.")]

    messages = build_provider_messages(history, "description: schedule\n", "And Tuesday?")

    assert messages[1:-1] == history


def test_optimizer_tool_is_offered_without_an_availability_capability() -> None:
    provider = FakeProvider()
    with AuthenticatedTestClient(create_test_app(settings=make_settings(), provider=provider)) as client:
        session_id = create_session(client)
        response = client.post(f"/sessions/{session_id}/messages", json={"message": "What can you do?"})

    assert response.status_code == 200
    assert any(tool["function"]["name"] == OPTIMIZER_TOOL for tool in provider.offered_tools)


def test_environment_configuration_requires_e2b_key_when_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_SANDBOX_BACKEND", "e2b")
    monkeypatch.delenv("E2B_API_KEY", raising=False)

    with pytest.raises(ValueError, match="E2B_API_KEY is required"):
        AiSettings.from_env()


def test_environment_configuration_defaults_to_extended_sandbox_turn_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_SANDBOX_BACKEND", "e2b")
    monkeypatch.setenv("E2B_API_KEY", "e2b-key")
    monkeypatch.delenv("AI_PROVIDER_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("AI_SANDBOX_COMMAND_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("AI_SANDBOX_TURN_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("AI_AGENT_MAX_TOOL_ROUNDS", raising=False)
    monkeypatch.delenv("AI_AGENT_MAX_TOOL_CALLS", raising=False)

    settings = AiSettings.from_env()
    assert settings.provider_timeout_seconds == 180
    assert settings.sandbox_command_timeout_seconds == 30
    assert settings.sandbox_turn_timeout_seconds == 3600
    assert settings.agent_max_tool_rounds == 200
    assert settings.agent_max_tool_calls == 400


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
    monkeypatch.setenv("AI_AGENT_MAX_TOOL_ROUNDS", "7")
    monkeypatch.setenv("AI_AGENT_MAX_TOOL_CALLS", "12")

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
    assert settings.agent_max_tool_rounds == 7
    assert settings.agent_max_tool_calls == 12


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


class BackgroundTestOptimizer:
    """Hold a fake optimization open until a foreground follow-up completes."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.submitted_yaml = ""
        self.closed = False
        self.deleted: list[str] = []

    async def submit(self, schedule_yaml: str, _timeout_seconds: int | None) -> OptimizerJobPayload:
        self.submitted_yaml = schedule_yaml
        return OptimizerJobPayload(id="remote-background", state="running")

    async def get(self, job_id: str) -> OptimizerJobPayload:
        if not self.release.is_set():
            return OptimizerJobPayload(id=job_id, state="running")
        return OptimizerJobPayload(
            id=job_id,
            state="completed",
            terminal=True,
            result={"outcome": "feasible", "score": 23},
        )

    async def progress_events(self, _job_id: str) -> AsyncIterator[dict[str, object]]:
        yield {"currentBestScore": 23, "elapsedSeconds": 2}
        while not self.release.is_set():
            await asyncio.sleep(0.001)

    async def finish_now(self, job_id: str) -> OptimizerJobPayload:
        self.release.set()
        return OptimizerJobPayload(id=job_id, state="running")

    async def cancel(self, job_id: str) -> OptimizerJobPayload:
        return OptimizerJobPayload(id=job_id, state="cancelled", terminal=True)

    async def result_artifact(self, _job: OptimizerJobPayload) -> OptimizerArtifact:
        return OptimizerArtifact(
            optimizer_workbook_bytes(),
            "optimized-schedule.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    async def close(self) -> None:
        self.closed = True

    async def delete(self, job_id: str) -> None:
        self.deleted.append(job_id)


def rename_call() -> list[object]:
    """Ask Bash to give the first person a description."""
    arguments = json.dumps({"command": "python3 -c 'set P1 description to Head'"})
    return [ToolCallRequest((ToolCall("call_0", BASH_TOOL, arguments),))]


@pytest.mark.parametrize("history_enabled", [False, True], ids=["without-history", "with-history"])
def test_optimizer_runs_behind_chat_and_wakes_the_agent_on_completion(monkeypatch, history_enabled: bool) -> None:
    history_starts: list[tuple[str, str, str | None, str, str, int]] = []
    if history_enabled:
        monkeypatch.setattr(ChatHistory, "initialize", lambda _self: None)
        monkeypatch.setattr(ChatHistory, "finish_turn", lambda *_args: None)

        def record_start(
            _self: ChatHistory,
            turn_id: str,
            session_id: str,
            credential_id: str | None,
            question: str,
            model: str,
            attachment_count: int,
        ) -> None:
            history_starts.append((turn_id, session_id, credential_id, question, model, attachment_count))

        monkeypatch.setattr(ChatHistory, "start_turn", record_start)
    optimizer_call = [ToolCallRequest((ToolCall("optimizer-call", OPTIMIZER_TOOL, json.dumps({"action": "start"})),))]
    provider = ScriptedToolProvider(
        optimizer_call,
        [TextDelta("Optimization started. You can keep chatting.")],
        [TextDelta("Yes, I can answer while it runs.")],
        [
            ToolCallRequest(
                (
                    ToolCall(
                        "read-result",
                        READ_TOOL,
                        json.dumps({"path": "/workspace/optimizer-results/optimized-schedule.xlsx"}),
                    ),
                )
            )
        ],
        [TextDelta("The optimizer returned score 23.")],
        [
            ToolCallRequest(
                (
                    ToolCall(
                        "read-later-result",
                        READ_TOOL,
                        json.dumps({"path": "/workspace/optimizer-results/optimized-schedule.xlsx"}),
                    ),
                )
            )
        ],
        [TextDelta("I can still inspect the workbook.")],
    )
    optimizer = BackgroundTestOptimizer()
    factory = FakeSandboxFactory()
    app = create_test_app(
        settings=make_settings(
            max_schedule_bytes=SCHEDULE_BYTE_LIMIT,
            optimizer_poll_interval_seconds=0.001,
            history_postgres_url="test" if history_enabled else "",
        ),
        provider=provider,
        sandbox_factory=factory,
        optimizer_backend=optimizer,
    )

    with AuthenticatedTestClient(app) as client:
        session_id = create_session(client, schedule_yaml())
        assert "optimizer" not in client.get("/capabilities").json()
        started = client.post(f"/sessions/{session_id}/messages", json={"message": "Optimize this schedule."})
        follow_up = client.post(f"/sessions/{session_id}/messages", json={"message": "Can we still talk?"})

        assert started.status_code == 200
        assert follow_up.status_code == 200
        assert "Optimization started" in started.text
        assert "answer while it runs" in follow_up.text
        submitted = parse_schedule(optimizer.submitted_yaml)
        assert [person["id"] for person in submitted["people"]["items"]] == ["P1", "P2"]
        assert "description" not in submitted

        optimizer.release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            events = app.state.session_event_broker.events_after(session_id)
            if any(event.type == "done" for event in events):
                break
            time.sleep(0.01)

        assert [event.type for event in events] == [
            "optimization",
            "optimization_progress",
            "optimization",
            "turn_start",
            "tool_start",
            "tool",
            "delta",
            "done",
        ]
        assert events[0].data["state"] == "running"
        assert events[0].data["terminal"] is False
        assert events[1].data["progress"] == {"currentBestScore": 23, "elapsedSeconds": 2}
        assert events[2].data["state"] == "completed"
        assert events[2].data["downloadable"] is True
        assert events[6].data == {"text": "The optimizer returned score 23."}
        if history_enabled:
            assert len(history_starts) == 3
            assert history_starts[-1][1] == session_id
            assert history_starts[-1][4:] == ("test-model", 0)
        assert '"score": 23' in str(provider.calls[3][-1]["content"])
        assert "/workspace/optimizer-results/optimized-schedule.xlsx" in str(provider.calls[3][-1]["content"])
        background_sandbox = next(
            backend
            for backend in factory.created
            if "/workspace/optimizer-results/optimized-schedule.xlsx" in backend.files
        )
        assert "/workspace/attachments/manifest.json" not in background_sandbox.files
        assert background_sandbox.files["/workspace/optimizer-results/optimized-schedule.xlsx"].startswith(
            b"PK\x03\x04"
        )

        job_id = str(events[1].data["job_id"])
        download = client.get(f"/sessions/{session_id}/optimizations/{job_id}/xlsx")
        assert download.status_code == 200
        assert download.content.startswith(b"PK\x03\x04")
        assert download.headers["content-disposition"] == 'attachment; filename="optimized-schedule.xlsx"'

        later = client.post(
            f"/sessions/{session_id}/messages",
            data={"message": "Can you inspect the workbook again?"},
            files={"files": ("note.txt", b"note", "text/plain")},
        )
        assert later.status_code == 200
        assert "I can still inspect" in later.text
        later_sandbox = next(
            backend
            for backend in factory.created
            if "/workspace/optimizer-results/optimized-schedule.xlsx" in backend.files
            and "/workspace/attachments/manifest.json" in backend.files
        )
        later_manifest = json.loads(later_sandbox.files["/workspace/attachments/manifest.json"])
        assert [entry["original_filename"] for entry in later_manifest["attachments"]] == [
            "note.txt",
        ]
        assert later_sandbox.files["/workspace/optimizer-results/optimized-schedule.xlsx"] == download.content

    assert optimizer.closed
    assert optimizer.deleted == ["remote-background"]


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
        [ToolCallRequest((ToolCall("call_1", READ_TOOL, json.dumps({"path": "schedule.yaml"})),))],
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
    assert len(factory.created) == 1


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


def test_pending_proposal_is_available_to_the_next_fresh_turn() -> None:
    client, session_id, _, provider, factory = proposal_decision_context()

    follow_up = client.post(f"/sessions/{session_id}/messages", json={"message": "What is pending?"})

    assert follow_up.status_code == 200
    assert "A validated proposal is pending" in provider.calls[2][0]["content"]
    assert b"description: Head" in factory.created[1].files[WORKSPACE_PENDING_PROPOSAL]
    assert b"people.items[0].description" in factory.created[1].files[WORKSPACE_PENDING_DIFF]
    assert factory.created[1].files[WORKSPACE_SCHEDULE] == schedule_yaml().encode()


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
    _, _, base_revision, _, _ = store.begin(session_id, owner)
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
    assert factory.created == []
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
    _, _, original_revision, _, _ = store.begin(session.id, "browser-owner")
    assert store.finish(
        session.id,
        "First edit",
        "First proposal",
        (first_proposal, "first diff"),
        base_revision=original_revision,
    ).proposal_saved
    _, _, active_turn_revision, _, _ = store.begin(session.id, "browser-owner")

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


def test_session_store_queues_steering_once_and_retains_it_with_the_turn() -> None:
    app = create_test_app(settings=make_settings(), provider=FakeProvider())
    store = app.state.session_store
    session = store.create("browser-owner", schedule_yaml())
    _, _, revision, _, _ = store.begin(session.id, "browser-owner")

    store.queue_steering(session.id, "browser-owner", "queued-1", "Focus on P2 instead.")
    store.queue_steering(session.id, "browser-owner", "queued-1", "Focus on P2 instead.")

    assert store.take_steering(session.id, False) == [("queued-1", "Focus on P2 instead.")]
    assert store.finish(
        session.id,
        "Inspect P1.",
        "P2 is the better target.",
        base_revision=revision,
        turn_messages=[
            ChatMessage(role="user", content="Inspect P1."),
            ChatMessage(role="assistant", content="P1 needs review."),
            ChatMessage(role="user", content="Focus on P2 instead."),
            ChatMessage(role="assistant", content="P2 is the better target."),
        ],
    ).turn_saved
    assert session.history == [
        ChatMessage(role="user", content="Inspect P1."),
        ChatMessage(role="assistant", content="P1 needs review."),
        ChatMessage(role="user", content="Focus on P2 instead."),
        ChatMessage(role="assistant", content="P2 is the better target."),
    ]


def test_session_store_bounds_steering_across_a_whole_turn_not_the_drained_queue() -> None:
    settings = make_settings(max_history_messages=3)
    app = create_test_app(settings=settings, provider=FakeProvider())
    store = app.state.session_store
    session = store.create("browser-owner", schedule_yaml())
    store.begin(session.id, "browser-owner")

    for index in range(settings.max_history_messages):
        store.queue_steering(session.id, "browser-owner", f"queued-{index}", "Keep going.")
        # Draining empties the queue but keeps the IDs that make a retried POST idempotent.
        assert store.take_steering(session.id, False) == [(f"queued-{index}", "Keep going.")]

    with pytest.raises(HTTPException) as exc_info:
        store.queue_steering(session.id, "browser-owner", "one-too-many", "Keep going.")

    assert exc_info.value.status_code == 429
    assert len(session.steering_ids) == settings.max_history_messages

    # A fresh turn starts the budget over.
    store.abort(session.id)
    store.begin(session.id, "browser-owner")
    store.queue_steering(session.id, "browser-owner", "queued-0", "Keep going.")
    assert store.take_steering(session.id, False) == [("queued-0", "Keep going.")]


def test_session_store_rejects_steering_after_the_final_boundary() -> None:
    app = create_test_app(settings=make_settings(), provider=FakeProvider())
    store = app.state.session_store
    session = store.create("browser-owner", schedule_yaml())
    store.begin(session.id, "browser-owner")

    assert store.take_steering(session.id, True) == []
    with pytest.raises(HTTPException) as exc_info:
        store.queue_steering(session.id, "browser-owner", "too-late", "One more thing.")

    assert exc_info.value.status_code == 409


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


def test_the_prompt_points_to_the_schedule_without_disclosing_its_facts() -> None:
    provider = FakeProvider()
    client = AuthenticatedTestClient(
        create_test_app(settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT), provider=provider)
    )
    schedule = schedule_yaml()
    session_id = create_session(client, schedule)

    client.post(f"/sessions/{session_id}/messages", json={"message": "How many people?"})

    system_prompt = provider.calls[0][0]["content"]
    normalized_prompt = " ".join(system_prompt.split())
    assert "schedule.yaml is available at /workspace/schedule.yaml" in normalized_prompt
    assert "2 people" not in normalized_prompt
    assert "PEOPLE" not in normalized_prompt
    assert "2026-01-01" not in normalized_prompt
    assert "Your tools are `read`, `bash`, `edit`, `write`, and the server-side `optimizer`" in normalized_prompt
    assert "Prefer `read` for files and images" in normalized_prompt
    assert "`edit` for unique exact-text replacements" in normalized_prompt
    assert "`write` only for new files or complete rewrites" in normalized_prompt
    assert "`/reference/schema-core.md`" in normalized_prompt
    assert "`/reference/schema-preferences.md`" in normalized_prompt
    assert "Read the relevant reference before changing" in normalized_prompt
    assert "at most one focused verification" in normalized_prompt
    assert "`/reference/schema-export.md`" in normalized_prompt
    assert "Python has `ruamel.yaml`, not PyYAML" in normalized_prompt
    assert "Preserve all unrequested fields, selectors, and objects" in normalized_prompt
    assert "/workspace/optimizer-results/optimized-schedule.xlsx" in normalized_prompt
    assert "Repair any validation error before answering" in normalized_prompt
    assert "user must approve it before the canonical schedule changes" in normalized_prompt
    assert "Update, rename, and remove only existing entities" in normalized_prompt
    assert "Use the server-side `optimizer` tool for a finished roster" in normalized_prompt
    assert "Use `optimizer` to start optimization" in normalized_prompt
    assert "Do not poll repeatedly" in normalized_prompt
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
