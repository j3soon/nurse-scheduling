"""Environment-backed configuration for the experimental AI service."""

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

# This code is mostly AI generated.

import os
from dataclasses import dataclass
from typing import Literal, cast

AttachmentMode = Literal["none", "images"]
DocumentAttachmentMode = Literal["none", "text"]
SandboxBackendName = Literal["none", "e2b"]


def _read_positive_int(name: str, default: int) -> int:
    """Read a positive integer environment setting."""
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _read_non_negative_int(name: str, default: int) -> int:
    """Read a non-negative integer environment setting."""
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _read_max_tool_calls() -> int:
    """Read the tool budget, translating the former turn budget if needed."""
    if os.getenv("AI_MAX_TOOL_CALLS") is not None:
        return _read_non_negative_int("AI_MAX_TOOL_CALLS", 5)
    if os.getenv("AI_MAX_AGENT_TURNS") is not None:
        return _read_positive_int("AI_MAX_AGENT_TURNS", 6) - 1
    return 5


def _read_positive_float(name: str, default: float) -> float:
    """Read a positive floating point environment setting."""
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _read_bool(name: str, default: bool) -> bool:
    """Read a conventional boolean environment setting."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _read_attachment_mode() -> AttachmentMode:
    """Read the enabled attachment capability."""
    value = os.getenv("AI_ATTACHMENT_MODE", "images").strip().lower()
    if value not in {"none", "images"}:
        raise ValueError("AI_ATTACHMENT_MODE must be one of: none, images")
    return cast(AttachmentMode, value)


def _read_document_attachment_mode() -> DocumentAttachmentMode:
    """Read the enabled document attachment capability."""
    value = os.getenv("AI_DOCUMENT_ATTACHMENT_MODE", "text").strip().lower()
    if value not in {"none", "text"}:
        raise ValueError("AI_DOCUMENT_ATTACHMENT_MODE must be one of: none, text")
    return cast(DocumentAttachmentMode, value)


def _read_sandbox_backend() -> SandboxBackendName:
    """Read the optional disposable sandbox provider."""
    value = os.getenv("AI_SANDBOX_BACKEND", "none").strip().lower()
    if value not in {"none", "e2b"}:
        raise ValueError("AI_SANDBOX_BACKEND must be one of: none, e2b")
    return cast(SandboxBackendName, value)


@dataclass(frozen=True)
class AiSettings:
    """Runtime settings for one isolated AI backend process."""

    provider_base_url: str
    provider_api_key: str
    provider_model: str
    provider_timeout_seconds: float = 120.0
    session_ttl_seconds: int = 3600
    max_sessions: int = 1000
    max_history_messages: int = 20
    max_message_chars: int = 8000
    max_schedule_bytes: int = 1_000_000
    max_concurrent_requests: int = 4
    max_tool_calls: int = 5
    attachment_mode: AttachmentMode = "images"
    max_image_files: int = 4
    max_image_bytes: int = 5_000_000
    document_attachment_mode: DocumentAttachmentMode = "text"
    max_document_files: int = 4
    max_document_bytes: int = 5_000_000
    max_document_text_chars: int = 50_000
    max_pdf_pages: int = 100
    max_xlsx_sheets: int = 20
    max_xlsx_cells: int = 100_000
    max_xlsx_uncompressed_bytes: int = 50_000_000
    sandbox_backend: SandboxBackendName = "none"
    e2b_api_key: str = ""
    e2b_template: str = "nurse-scheduling-ai-sandbox"
    sandbox_command_timeout_seconds: float = 10.0
    sandbox_turn_timeout_seconds: float = 300.0
    sandbox_cleanup_timeout_seconds: float = 10.0
    bash_tool_max_command_chars: int = 4_000
    bash_tool_max_stdout_chars: int = 12_000
    bash_tool_max_stderr_chars: int = 4_000
    bash_tool_max_output_chars: int = 16_000
    cookie_secure: bool = True

    @classmethod
    def from_env(cls) -> "AiSettings":
        """Load settings without embedding provider credentials in the repository."""
        provider_api_key = os.getenv("AI_PROVIDER_API_KEY", "").strip()
        if not provider_api_key:
            raise ValueError("AI_PROVIDER_API_KEY is required")

        provider_base_url = os.getenv("AI_PROVIDER_BASE_URL", "").strip().rstrip("/")
        provider_model = os.getenv("AI_PROVIDER_MODEL", "local-model").strip()
        if not provider_base_url:
            raise ValueError("AI_PROVIDER_BASE_URL is required")
        if not provider_model:
            raise ValueError("AI_PROVIDER_MODEL must not be empty")

        sandbox_backend = _read_sandbox_backend()
        e2b_api_key = os.getenv("E2B_API_KEY", "").strip()
        e2b_template = os.getenv("E2B_TEMPLATE", "nurse-scheduling-ai-sandbox").strip()
        if sandbox_backend == "e2b" and not e2b_api_key:
            raise ValueError("E2B_API_KEY is required when AI_SANDBOX_BACKEND=e2b")
        if sandbox_backend == "e2b" and not e2b_template:
            raise ValueError("E2B_TEMPLATE is required when AI_SANDBOX_BACKEND=e2b")
        if sandbox_backend == "none":
            raise ValueError("AI_SANDBOX_BACKEND must be configured")

        return cls(
            provider_base_url=provider_base_url,
            provider_api_key=provider_api_key,
            provider_model=provider_model,
            provider_timeout_seconds=_read_positive_float("AI_PROVIDER_TIMEOUT_SECONDS", 120.0),
            session_ttl_seconds=_read_positive_int("AI_SESSION_TTL_SECONDS", 3600),
            max_sessions=_read_positive_int("AI_MAX_SESSIONS", 1000),
            max_history_messages=_read_positive_int("AI_MAX_HISTORY_MESSAGES", 20),
            max_message_chars=_read_positive_int("AI_MAX_MESSAGE_CHARS", 8000),
            max_schedule_bytes=_read_positive_int("AI_MAX_SCHEDULE_BYTES", 1_000_000),
            max_concurrent_requests=_read_positive_int("AI_MAX_CONCURRENT_REQUESTS", 4),
            max_tool_calls=_read_max_tool_calls(),
            attachment_mode=_read_attachment_mode(),
            max_image_files=_read_positive_int("AI_MAX_IMAGE_FILES", 4),
            max_image_bytes=_read_positive_int("AI_MAX_IMAGE_BYTES", 5_000_000),
            document_attachment_mode=_read_document_attachment_mode(),
            max_document_files=_read_positive_int("AI_MAX_DOCUMENT_FILES", 4),
            max_document_bytes=_read_positive_int("AI_MAX_DOCUMENT_BYTES", 5_000_000),
            max_document_text_chars=_read_positive_int("AI_MAX_DOCUMENT_TEXT_CHARS", 50_000),
            max_pdf_pages=_read_positive_int("AI_MAX_PDF_PAGES", 100),
            max_xlsx_sheets=_read_positive_int("AI_MAX_XLSX_SHEETS", 20),
            max_xlsx_cells=_read_positive_int("AI_MAX_XLSX_CELLS", 100_000),
            max_xlsx_uncompressed_bytes=_read_positive_int("AI_MAX_XLSX_UNCOMPRESSED_BYTES", 50_000_000),
            sandbox_backend=sandbox_backend,
            e2b_api_key=e2b_api_key,
            e2b_template=e2b_template,
            sandbox_command_timeout_seconds=_read_positive_float("AI_SANDBOX_COMMAND_TIMEOUT_SECONDS", 10.0),
            sandbox_turn_timeout_seconds=_read_positive_float("AI_SANDBOX_TURN_TIMEOUT_SECONDS", 300.0),
            sandbox_cleanup_timeout_seconds=_read_positive_float("AI_SANDBOX_CLEANUP_TIMEOUT_SECONDS", 10.0),
            bash_tool_max_command_chars=_read_positive_int("AI_BASH_TOOL_MAX_COMMAND_CHARS", 4_000),
            bash_tool_max_stdout_chars=_read_positive_int("AI_BASH_TOOL_MAX_STDOUT_CHARS", 12_000),
            bash_tool_max_stderr_chars=_read_positive_int("AI_BASH_TOOL_MAX_STDERR_CHARS", 4_000),
            bash_tool_max_output_chars=_read_positive_int("AI_BASH_TOOL_MAX_OUTPUT_CHARS", 16_000),
            cookie_secure=_read_bool("AI_COOKIE_SECURE", True),
        )
