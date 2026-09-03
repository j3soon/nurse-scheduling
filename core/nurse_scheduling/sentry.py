"""Sentry integration helpers for backend error reporting."""

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

import os
import re
import sys
from typing import TYPE_CHECKING, Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder

from .anonymize_scheduling_data import anonymize_scheduling_data_in_yaml
from .server.auth import describe_stream_token, extract_bearer_token

if TYPE_CHECKING:
    from .server.jobs.models import Job

DEFAULT_SENTRY_DSN = "https://e5bffd2f416c149dfb0d17751071c61d@o4510953883107328.ingest.us.sentry.io/4510953885401088"


def _should_enable_sentry() -> bool:
    if os.getenv("DISABLE_SENTRY"):
        return False
    # Avoid sending errors from local/unit test runs by default.
    return "PYTEST_CURRENT_TEST" not in os.environ and "pytest" not in sys.modules


def init_sentry(app_version: str, *, app: str = "backend") -> None:
    """Initialize Sentry for one named application process."""
    if not _should_enable_sentry():
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN") or DEFAULT_SENTRY_DSN,
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
        release=os.getenv("SENTRY_RELEASE", f"nurse-scheduling@{app_version}"),
        # Add data like request headers and IP for users, if applicable;
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for tracing.
        traces_sample_rate=1.0,
        # To collect profiles for all profile sessions,
        # set `profile_session_sample_rate` to 1.0.
        profile_session_sample_rate=1.0,
        # Profiles will be automatically collected while
        # there is an active span.
        profile_lifecycle="trace",
        # Enable logs to be sent to Sentry
        enable_logs=True,
    )
    sentry_sdk.set_tag("app", app)


def flush_sentry(timeout: float = 2.0) -> None:
    """Flush pending events and logs before a short-lived process exits."""
    if not _should_enable_sentry():
        return

    import sentry_sdk

    sentry_sdk.flush(timeout=timeout)


def capture_optimize_exception(job: "Job", content: bytes, error: Exception) -> None:
    if not _should_enable_sentry():
        return

    import sentry_sdk

    anonymized_content = anonymize_scheduling_data_in_yaml(content)
    content_sanitized = anonymized_content is not content

    # Ref: https://docs.sentry.io/platforms/python/enriching-events/scopes/
    with sentry_sdk.new_scope() as scope:
        scope.set_context(
            "schedule_state",
            {
                "attached": True,
                "content_sanitized": content_sanitized,
                "input_name": job.request.input_name,
                "job_id": job.id,
                "size_bytes": len(anonymized_content),
            },
        )
        scope.add_attachment(
            bytes=anonymized_content,
            filename=job.request.input_name,
            content_type="application/x-yaml",
        )
        sentry_sdk.capture_exception(error)


JOB_ID_SHAPE = re.compile(r"^job_[0-9a-f]{32}$")
"""Shape of an issued job identifier, used to describe a request for a missing one."""
STREAM_ROUTE_SUFFIX = "/events"
"""Route suffix of the only endpoint accepting a stream token."""


def _describe_job_id(request: Request) -> str | None:
    """Describe a requested job identifier's shape without repeating the identifier."""
    job_id = request.path_params.get("job_id")
    if job_id is None:
        return None
    return "issued_shape" if JOB_ID_SHAPE.match(job_id) else "unissued_shape"


def classify_suspicious_request(
    request: Request,
    status_code: int,
    error_code: str | None,
) -> tuple[str, str] | None:
    """Return a suspicious request's signal name and Sentry level, or `None` when it is noise.

    Internet background traffic probes paths that do not exist and endpoints it cannot
    authenticate against. The signals below instead require knowledge of this API's contract,
    so they are worth reporting even though they arrive as ordinary client errors.
    """
    if status_code == 401:
        # Only the deployment secret can sign a token, so a well-formed unexpired one that
        # failed verification was constructed rather than issued.
        stream_token_is_live = describe_stream_token(request.query_params.get("token")) == "live"
        if request.url.path.endswith(STREAM_ROUTE_SUFFIX) and stream_token_is_live:
            return "forged_stream_token", "error"
        if extract_bearer_token(request.headers.get("Authorization")) is not None:
            return "rejected_bearer_token", "warning"
        return None
    if status_code == 404:
        # A missing route is noise. A missing job was addressed through a real route.
        return ("job_id_probe", "warning") if error_code == "job_not_found" else None
    invalid_reason = getattr(request.state, "invalid_reason", None)
    if invalid_reason is not None:
        return invalid_reason, "warning"
    return None


def capture_invalid_request(
    request: Request,
    status_code: int,
    detail: Any,
    error_code: str | None = None,
) -> None:
    if not _should_enable_sentry():
        return
    signal = classify_suspicious_request(request, status_code, error_code)
    # Missing routes, expired resources, and unauthenticated probes of a protected
    # deployment are expected and not actionable.
    if signal is None and status_code in (401, 404):
        return

    import sentry_sdk

    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)
    serialized_detail = jsonable_encoder(detail)
    message = "Invalid API request"
    level = "warning"
    fingerprint = ["invalid-request", str(status_code), route_path]

    with sentry_sdk.new_scope() as scope:
        if signal is not None:
            # Imported here so processes that only report errors do not load the routes.
            from .server.api.optimize import CLIENT_ID_COOKIE_NAME

            signal_name, level = signal
            message = f"Suspicious API request: {signal_name}"
            fingerprint = ["suspicious-request", signal_name]
            scope.set_tag("request.suspicious", signal_name)
            scope.set_context(
                "suspicious_request",
                {
                    "signal": signal_name,
                    "job_id": _describe_job_id(request),
                    # Named without "token", which Sentry scrubs from a field name.
                    "stream_state": describe_stream_token(request.query_params.get("token")),
                    "bearer_presented": extract_bearer_token(request.headers.get("Authorization")) is not None,
                    "client_id": request.cookies.get(CLIENT_ID_COOKIE_NAME),
                    "user_agent": request.headers.get("User-Agent"),
                    "origin": request.headers.get("Origin"),
                },
            )
        scope.set_tag("request.invalid", True)
        scope.set_tag("http.status_code", status_code)
        scope.set_tag("http.method", request.method)
        scope.set_tag("http.route", route_path)
        scope.set_context(
            "invalid_request",
            {
                "path": request.url.path,
                "route": route_path,
                "method": request.method,
                "status_code": status_code,
                "detail": serialized_detail,
            },
        )
        scope.fingerprint = fingerprint
        sentry_sdk.capture_message(message, level=level)
