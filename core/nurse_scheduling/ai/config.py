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

from ..server.auth import AuthCredential, normalize_auth_credentials, parse_auth_credentials

SandboxBackendName = Literal["none", "e2b"]
AI_AUTH_TOKEN_ENV_NAME = "AI_AUTH_TOKEN"
AI_AUTH_TOKENS_ENV_NAME = "AI_AUTH_TOKENS"
AI_AUTH_REQUIRED_ENV_NAME = "AI_AUTH_REQUIRED"


def validate_ai_auth_credentials(
    token: str | None,
    tokens: tuple[AuthCredential, ...],
    *,
    required: bool,
) -> tuple[str | None, tuple[AuthCredential, ...]]:
    """Normalize AI bearer credentials and enforce deployment requirements."""
    return normalize_auth_credentials(
        token,
        tokens,
        legacy_name=AI_AUTH_TOKEN_ENV_NAME,
        credentials_name=AI_AUTH_TOKENS_ENV_NAME,
        required_name=AI_AUTH_REQUIRED_ENV_NAME,
        required=required,
    )


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


def _read_non_negative_float(name: str, default: float) -> float:
    """Read a non-negative floating point environment setting."""
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
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
    auth_token: str | None = None
    auth_tokens: tuple[AuthCredential, ...] = ()
    auth_required: bool = False
    provider_timeout_seconds: float = 180.0
    provider_max_attempts: int = 3
    provider_retry_backoff_seconds: float = 1.0
    optimizer_base_url: str = "http://localhost:8000"
    optimizer_auth_token: str = ""
    optimizer_poll_interval_seconds: float = 1.0
    optimizer_request_timeout_seconds: float = 30.0
    optimizer_default_timeout_seconds: int = 300
    optimizer_max_runs_per_session: int = 50
    optimizer_max_result_bytes: int = 10_000_000
    optimizer_result_cache_bytes: int = 100_000_000
    session_ttl_seconds: int = 172_800
    history_postgres_url: str = ""
    history_retention_days: int = 30
    request_log_enabled: bool = True
    """Whether incoming question previews are logged, which records chat text."""
    max_sessions: int = 1000
    max_history_messages: int = 1000
    max_message_chars: int = 8000
    max_schedule_bytes: int = 1_000_000
    max_concurrent_requests: int = 4
    max_attachment_files: int = 8
    max_attachment_bytes: int = 5_000_000
    sandbox_backend: SandboxBackendName = "none"
    e2b_api_key: str = ""
    e2b_template: str = "nurse-scheduling-ai-sandbox"
    sandbox_command_timeout_seconds: float = 30.0
    sandbox_turn_timeout_seconds: float = 3600.0
    agent_max_tool_rounds: int = 200
    agent_max_tool_calls: int = 400
    sandbox_cleanup_timeout_seconds: float = 10.0
    sandbox_max_attempts: int = 3
    sandbox_retry_backoff_seconds: float = 0.5
    sandbox_pause_request_timeout_seconds: float = 5.0
    sandbox_control_request_timeout_seconds: float = 2.0
    sandbox_reaper_interval_seconds: float = 30.0
    cookie_secure: bool = True

    @classmethod
    def from_env(cls) -> "AiSettings":
        """Load settings without embedding provider credentials in the repository."""
        auth_token = os.getenv(AI_AUTH_TOKEN_ENV_NAME)
        auth_tokens = parse_auth_credentials(
            os.getenv(AI_AUTH_TOKENS_ENV_NAME),
            name=AI_AUTH_TOKENS_ENV_NAME,
        )
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
            auth_token=auth_token,
            auth_tokens=auth_tokens,
            auth_required=_read_bool(AI_AUTH_REQUIRED_ENV_NAME, False),
            provider_timeout_seconds=_read_positive_float("AI_PROVIDER_TIMEOUT_SECONDS", 180.0),
            provider_max_attempts=_read_positive_int("AI_PROVIDER_MAX_ATTEMPTS", 3),
            provider_retry_backoff_seconds=_read_non_negative_float("AI_PROVIDER_RETRY_BACKOFF_SECONDS", 1.0),
            optimizer_base_url=os.getenv("AI_OPTIMIZER_BASE_URL", "").strip().rstrip("/") or "http://localhost:8000",
            optimizer_auth_token=os.getenv("AI_OPTIMIZER_AUTH_TOKEN", "").strip(),
            optimizer_poll_interval_seconds=_read_positive_float("AI_OPTIMIZER_POLL_INTERVAL_SECONDS", 1.0),
            optimizer_request_timeout_seconds=_read_positive_float("AI_OPTIMIZER_REQUEST_TIMEOUT_SECONDS", 30.0),
            optimizer_default_timeout_seconds=_read_positive_int("AI_OPTIMIZER_DEFAULT_TIMEOUT_SECONDS", 300),
            optimizer_max_runs_per_session=_read_positive_int("AI_OPTIMIZER_MAX_RUNS_PER_SESSION", 50),
            optimizer_max_result_bytes=_read_positive_int("AI_OPTIMIZER_MAX_RESULT_BYTES", 10_000_000),
            optimizer_result_cache_bytes=_read_positive_int("AI_OPTIMIZER_RESULT_CACHE_BYTES", 100_000_000),
            session_ttl_seconds=_read_positive_int("AI_SESSION_TTL_SECONDS", 172_800),
            history_postgres_url=os.getenv("AI_HISTORY_POSTGRES_URL", "").strip(),
            history_retention_days=_read_positive_int("AI_HISTORY_RETENTION_DAYS", 30),
            request_log_enabled=_read_bool("AI_REQUEST_LOG_ENABLED", True),
            max_sessions=_read_positive_int("AI_MAX_SESSIONS", 1000),
            max_history_messages=_read_positive_int("AI_MAX_HISTORY_MESSAGES", 1000),
            max_message_chars=_read_positive_int("AI_MAX_MESSAGE_CHARS", 8000),
            max_schedule_bytes=_read_positive_int("AI_MAX_SCHEDULE_BYTES", 1_000_000),
            max_concurrent_requests=_read_positive_int("AI_MAX_CONCURRENT_REQUESTS", 4),
            max_attachment_files=_read_positive_int("AI_MAX_ATTACHMENT_FILES", 8),
            max_attachment_bytes=_read_positive_int("AI_MAX_ATTACHMENT_BYTES", 5_000_000),
            sandbox_backend=sandbox_backend,
            e2b_api_key=e2b_api_key,
            e2b_template=e2b_template,
            sandbox_command_timeout_seconds=_read_positive_float("AI_SANDBOX_COMMAND_TIMEOUT_SECONDS", 30.0),
            sandbox_turn_timeout_seconds=_read_positive_float("AI_SANDBOX_TURN_TIMEOUT_SECONDS", 3600.0),
            agent_max_tool_rounds=_read_positive_int("AI_AGENT_MAX_TOOL_ROUNDS", 200),
            agent_max_tool_calls=_read_positive_int("AI_AGENT_MAX_TOOL_CALLS", 400),
            sandbox_cleanup_timeout_seconds=_read_positive_float("AI_SANDBOX_CLEANUP_TIMEOUT_SECONDS", 10.0),
            sandbox_max_attempts=_read_positive_int("AI_SANDBOX_MAX_ATTEMPTS", 3),
            sandbox_retry_backoff_seconds=_read_non_negative_float("AI_SANDBOX_RETRY_BACKOFF_SECONDS", 0.5),
            sandbox_pause_request_timeout_seconds=_read_positive_float("AI_SANDBOX_PAUSE_REQUEST_TIMEOUT_SECONDS", 5.0),
            sandbox_control_request_timeout_seconds=_read_positive_float(
                "AI_SANDBOX_CONTROL_REQUEST_TIMEOUT_SECONDS", 2.0
            ),
            sandbox_reaper_interval_seconds=_read_positive_float("AI_SANDBOX_REAPER_INTERVAL_SECONDS", 30.0),
            cookie_secure=_read_bool("AI_COOKIE_SECURE", True),
        )
