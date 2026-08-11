"""Tests for the text-only experimental AI service."""

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
from collections.abc import AsyncIterator, Sequence
from unittest.mock import ANY

import pytest
from fastapi.testclient import TestClient

from nurse_scheduling.ai.app import SERVICE_NAME, create_app
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.provider import ChatMessage, ProviderError


class FakeProvider:
    """Record prompts and return deterministic streamed responses."""

    def __init__(self, responses: list[list[str] | Exception] | None = None) -> None:
        self.responses = responses or [["Hello", " from AI"]]
        self.calls: list[list[ChatMessage]] = []

    async def stream_chat(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.calls.append(list(messages))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        for delta in response:
            yield delta


def make_settings(**overrides: object) -> AiSettings:
    """Create isolated settings with small test-friendly limits."""
    values = {
        "provider_base_url": "https://provider.example/v1",
        "provider_api_key": "test-token",
        "provider_model": "test-model",
        "max_sessions": 10,
        "max_history_messages": 20,
        "max_message_chars": 100,
        "max_schedule_bytes": 1000,
        "max_concurrent_requests": 2,
        "cookie_secure": False,
    }
    values.update(overrides)
    return AiSettings(**values)


def create_session(client: TestClient, schedule_yaml: str = "description: test") -> str:
    """Create a session and return its public UUID."""
    response = client.post("/sessions", json={"schedule_yaml": schedule_yaml})
    assert response.status_code == 201
    return response.json()["id"]


def parse_sse(response_text: str) -> list[tuple[str, dict[str, str]]]:
    """Parse the small SSE subset emitted by the service."""
    events: list[tuple[str, dict[str, str]]] = []
    for block in response_text.strip().split("\n\n"):
        lines = block.splitlines()
        event_type = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        data = next(json.loads(line.removeprefix("data: ")) for line in lines if line.startswith("data: "))
        events.append((event_type, data))
    return events


def test_health_and_streamed_schedule_question() -> None:
    provider = FakeProvider()
    client = TestClient(create_app(settings=make_settings(), provider=provider))

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
    assert "Alice" in prompt[-2]["content"]
    assert "untrusted data" in prompt[0]["content"]


def test_completed_turn_is_available_to_the_next_question() -> None:
    provider = FakeProvider([["First answer"], ["Second answer"]])
    client = TestClient(create_app(settings=make_settings(), provider=provider))
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
    assert "description: current" in provider.calls[1][-2]["content"]


def test_session_uuid_alone_does_not_bypass_browser_ownership() -> None:
    app = create_app(settings=make_settings(), provider=FakeProvider())
    owner_client = TestClient(app)
    other_client = TestClient(app)
    session_id = create_session(owner_client)
    create_session(other_client)

    response = other_client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Try another session"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat session not found."


def test_provider_failure_is_streamed_without_recording_a_turn() -> None:
    provider = FakeProvider([ProviderError("Provider unavailable."), ["Recovered"]])
    client = TestClient(create_app(settings=make_settings(), provider=provider))
    session_id = create_session(client)

    failed = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Failed question"},
    )
    recovered = client.post(
        f"/sessions/{session_id}/messages",
        json={"message": "Retry"},
    )

    assert parse_sse(failed.text) == [("error", {"message": "Provider unavailable."})]
    assert recovered.status_code == 200
    assert all(message["content"] != "Failed question" for message in provider.calls[1])


def test_request_limits_are_enforced() -> None:
    client = TestClient(
        create_app(
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


def test_environment_configuration_requires_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_PROVIDER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="AI_PROVIDER_API_KEY is required"):
        AiSettings.from_env()
