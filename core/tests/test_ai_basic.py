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

import base64
import hashlib
import json
from collections.abc import AsyncIterator, Sequence
from unittest.mock import ANY

import pytest
from fastapi.testclient import TestClient

from nurse_scheduling.ai.app import SERVICE_NAME, create_app
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.editor import EDIT_TOOL
from nurse_scheduling.ai.provider import ChatMessage, ProviderError, TextDelta, ToolCall, ToolCallRequest

from .ai_test_helper import SCHEDULE_BYTE_LIMIT, base_schedule_payload, schedule_yaml

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\xff\xd9"
WEBP_BYTES = b"RIFF\x04\x00\x00\x00WEBP"


class FakeProvider:
    """Record prompts and return deterministic streamed responses."""

    def __init__(self, responses: list[list[str] | Exception] | None = None) -> None:
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
            yield TextDelta(delta)


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
    # The schedule itself is read with the view tool, so only its shape is sent.
    assert "Alice" not in prompt[0]["content"]
    assert "schedule.yaml is 2 lines" in prompt[0]["content"]
    assert "untrusted data" in prompt[0]["content"]


def test_capabilities_report_configured_attachment_limits() -> None:
    client = TestClient(
        create_app(
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
    }


def test_image_is_sent_to_provider_but_not_retained_in_history() -> None:
    provider = FakeProvider([["Image answer"], ["Follow-up answer"]])
    client = TestClient(create_app(settings=make_settings(attachment_mode="images"), provider=provider))
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
        ("ward.webp", "image/webp", WEBP_BYTES),
    ],
)
def test_supported_image_signatures_are_sent_to_provider(filename: str, media_type: str, data: bytes) -> None:
    provider = FakeProvider()
    client = TestClient(create_app(settings=make_settings(attachment_mode="images"), provider=provider))
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
    client = TestClient(create_app(settings=make_settings(), provider=provider))
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
    client = TestClient(create_app(settings=make_settings(), provider=FakeProvider()))
    session_id = create_session(client)

    response = client.post(
        f"/sessions/{session_id}/messages",
        data={"message": "Read the file."},
        files={"documents": (filename, b"Alice works Monday.", media_type)},
    )

    assert response.status_code == 200


def test_images_and_documents_share_one_provider_user_message() -> None:
    provider = FakeProvider()
    client = TestClient(create_app(settings=make_settings(), provider=provider))
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
    client = TestClient(create_app(settings=make_settings(**settings), provider=FakeProvider()))
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
    client = TestClient(create_app(settings=make_settings(**settings), provider=FakeProvider()))
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
    assert "Current schedule summary:" in provider.calls[1][0]["content"]
    assert provider.calls[1][0]["role"] == "system"
    assert all(message["role"] != "system" for message in provider.calls[1][1:])


def test_private_container_origin_can_call_ai_backend_directly() -> None:
    client = TestClient(create_app(settings=make_settings(), provider=FakeProvider()))

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
    provider_error = "The AI provider returned HTTP 525. Error ID: 72dc8f31-45af-410d-9fc2-41bdf1fc718f."
    provider = FakeProvider([ProviderError(provider_error), ["Recovered"]])
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

    assert parse_sse(failed.text) == [("error", {"message": provider_error})]
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


def test_environment_configuration_enables_images_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.delenv("AI_ATTACHMENT_MODE", raising=False)
    monkeypatch.delenv("AI_DOCUMENT_ATTACHMENT_MODE", raising=False)

    assert AiSettings.from_env().attachment_mode == "images"
    assert AiSettings.from_env().document_attachment_mode == "text"


def test_environment_configuration_reads_tool_call_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_MAX_TOOL_CALLS", "7")
    monkeypatch.setenv("AI_MAX_AGENT_TURNS", "20")

    assert AiSettings.from_env().max_tool_calls == 7


def test_environment_configuration_translates_legacy_agent_turn_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.delenv("AI_MAX_TOOL_CALLS", raising=False)
    monkeypatch.setenv("AI_MAX_AGENT_TURNS", "6")

    assert AiSettings.from_env().max_tool_calls == 5


def test_environment_configuration_rejects_negative_tool_call_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "test-token")
    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("AI_MAX_TOOL_CALLS", "-1")

    with pytest.raises(ValueError, match="AI_MAX_TOOL_CALLS must be non-negative"):
        AiSettings.from_env()


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


class ScriptedToolProvider:
    """Return a scripted tool call, then a text answer."""

    def __init__(self, *turns) -> None:
        self._turns = list(turns)
        self.calls: list[list[ChatMessage]] = []

    async def stream_events(self, messages: Sequence[ChatMessage], tools=None) -> AsyncIterator[object]:
        self.calls.append(list(messages))
        for event in self._turns[min(len(self.calls) - 1, len(self._turns) - 1)]:
            yield event


def rename_call() -> list[object]:
    """Ask the editor to give the first person a description."""
    arguments = json.dumps(
        {"old_str": "  - id: P1\n    description: ''", "new_str": "  - id: P1\n    description: Head"}
    )
    return [ToolCallRequest((ToolCall("call_0", EDIT_TOOL, arguments),))]


def proposing_client() -> tuple[TestClient, str, str]:
    """Run one proposing turn and return the client, session, and base revision."""
    provider = ScriptedToolProvider(rename_call(), [TextDelta("Renamed P1.")])
    client = TestClient(create_app(settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT), provider=provider))
    schedule = schedule_yaml()
    session_id = create_session(client, schedule)
    response = client.post(f"/sessions/{session_id}/messages", json={"message": "Rename P1."})
    assert response.status_code == 200
    return client, session_id, hashlib.sha256(schedule.encode("utf-8")).hexdigest()


def test_a_tool_run_streams_tool_use_and_a_proposal() -> None:
    provider = ScriptedToolProvider(rename_call(), [TextDelta("Renamed P1.")])
    client = TestClient(create_app(settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT), provider=provider))
    session_id = create_session(client, schedule_yaml())

    response = client.post(f"/sessions/{session_id}/messages", json={"message": "Rename P1."})

    events = parse_sse(response.text)
    tool = next(data for name, data in events if name == "tool")
    assert tool["name"] == EDIT_TOOL
    assert tool["ok"] is True
    assert "Head" in tool["arguments"]
    assert "schedule.yaml is valid" in tool["result"]
    proposal = next(data for name, data in events if name == "proposal")
    assert "people.items[0].description" in proposal["diff"]
    assert not any(name == "proposal" and "schedule" in data for name, data in events)


def test_approval_returns_the_proposed_schedule_once() -> None:
    client, session_id, revision = proposing_client()

    approved = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})
    repeated = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})

    assert approved.status_code == 200
    assert "description: Head" in approved.json()["schedule_yaml"]
    assert repeated.status_code == 404


def test_approval_is_refused_when_the_browser_holds_another_revision() -> None:
    client, session_id, _ = proposing_client()

    stale = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": "0" * 64})
    retried = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": "0" * 64})

    assert stale.status_code == 409
    assert "changed after this proposal" in stale.json()["detail"]
    assert retried.status_code == 404


def test_rejection_drops_the_proposal() -> None:
    client, session_id, revision = proposing_client()

    rejected = client.post(f"/sessions/{session_id}/proposal/reject")
    approved = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})

    assert rejected.status_code == 204
    assert approved.status_code == 404


def test_a_newer_schedule_replaces_the_snapshot_and_the_proposal() -> None:
    client, session_id, revision = proposing_client()
    payload = base_schedule_payload()
    payload["description"] = "Ward A"

    updated = client.put(f"/sessions/{session_id}/schedule", json={"schedule_yaml": schedule_yaml(payload)})
    approved = client.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision})

    assert updated.status_code == 204
    assert approved.status_code == 404


def test_sessions_are_private_to_their_browser() -> None:
    _, session_id, revision = proposing_client()
    other = TestClient(create_app(settings=make_settings(), provider=FakeProvider()))

    assert other.post(f"/sessions/{session_id}/proposal/approve", json={"base_sha256": revision}).status_code == 404
    assert other.put(f"/sessions/{session_id}/schedule", json={"schedule_yaml": "a: 1"}).status_code == 404


def test_approval_allows_a_schedule_the_user_had_not_finished() -> None:
    payload = base_schedule_payload()
    payload["preferences"] = []
    provider = ScriptedToolProvider(rename_call(), [TextDelta("Renamed P1.")])
    client = TestClient(create_app(settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT), provider=provider))
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
    client = TestClient(create_app(settings=make_settings(max_schedule_bytes=SCHEDULE_BYTE_LIMIT), provider=provider))
    schedule = schedule_yaml()
    session_id = create_session(client, schedule)

    client.post(f"/sessions/{session_id}/messages", json={"message": "How many people?"})

    system_prompt = provider.calls[0][0]["content"]
    assert "2 people, 2 shift types, 2 preferences" in system_prompt
    assert "Group ids: people PEOPLE" in system_prompt
    assert "Dates run from 2026-01-01 to 2026-01-02" in system_prompt
    summary = system_prompt.split("Current schedule summary:\n")[1]
    assert len(summary) < len(schedule) / 2


def test_a_browser_may_send_the_newer_schedule_across_origins() -> None:
    client = TestClient(create_app(settings=make_settings(), provider=FakeProvider()))

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
