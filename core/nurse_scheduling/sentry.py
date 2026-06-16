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
import sys
from typing import TYPE_CHECKING, Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder

from .anonymize_scheduling_data import anonymize_scheduling_data_in_yaml

if TYPE_CHECKING:
    from .jobs import OptimizeJob


def _should_enable_sentry() -> bool:
    if os.getenv("DISABLE_SENTRY"):
        return False
    # Avoid sending errors from local/unit test runs by default.
    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return False
    return True


def init_sentry(app_version: str) -> None:
    if not _should_enable_sentry():
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn="https://e5bffd2f416c149dfb0d17751071c61d@o4510953883107328.ingest.us.sentry.io/4510953885401088",
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
    sentry_sdk.set_tag("app", "backend")


def capture_optimize_exception(job: "OptimizeJob", content: bytes, error: Exception) -> None:
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
                "input_name": job.input_name,
                "job_id": job.id,
                "size_bytes": len(anonymized_content),
            },
        )
        scope.add_attachment(
            bytes=anonymized_content,
            filename=job.input_name,
            content_type="application/x-yaml",
        )
        sentry_sdk.capture_exception(error)


def capture_invalid_request(request: Request, status_code: int, detail: Any) -> None:
    if not _should_enable_sentry():
        return

    import sentry_sdk

    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)
    serialized_detail = jsonable_encoder(detail)

    with sentry_sdk.new_scope() as scope:
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
        scope.fingerprint = ["invalid-request", str(status_code), route_path]
        sentry_sdk.capture_message("Invalid API request", level="warning")
