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

import ipaddress
import logging
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

sentry_logger = logging.getLogger("nurse_scheduling.sentry")

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
        before_send=_redact_stream_token,
        before_send_transaction=_redact_stream_token,
    )
    sentry_sdk.set_tag("app", app)


STREAM_TOKEN_QUERY = re.compile(r"(?i)(^|&)token=[^&]*")
"""Query parameter carrying a job's stream credential."""


def _redact_stream_token(event: dict, _hint: dict) -> dict:
    """Remove a stream credential from a reported query string.

    Sentry scrubs sensitive headers, cookies, and body fields, but not a query string, and a
    rejected request can still carry a valid token. Stream tokens are kept out of logs by
    design, so one must not reach a report either.
    """
    request = event.get("request")
    if isinstance(request, dict) and isinstance(request.get("query_string"), str):
        request["query_string"] = STREAM_TOKEN_QUERY.sub(r"\1token=[Filtered]", request["query_string"])
    return event


def flush_sentry(timeout: float = 2.0) -> None:
    """Flush pending events and logs before a short-lived process exits."""
    if not _should_enable_sentry():
        return

    import sentry_sdk

    sentry_sdk.flush(timeout=timeout)


def _connection_address(request: Request) -> str | None:
    """Return the address a request connected from, or `None` when it is not one.

    A peer is not always an address. A Unix socket has none, and a proxy chain can resolve
    to a name, so reporting the value unchecked would attribute events to something Sentry
    rejects as an address.
    """
    client = request.client
    if client is None:
        return None
    try:
        ipaddress.ip_address(client.host)
    except ValueError:
        return None
    return client.host


CLIENT_ADDRESS_TAG = "client.address"
"""Tag naming the address a request connected from."""


def tag_client_address(request: Request) -> None:
    """Record the address a request connected from, alongside Sentry's own attribution.

    Sentry infers a request's address from the leftmost `X-Forwarded-For` entry, which the
    caller supplies. Uvicorn resolves the address from the proxy chain it trusts instead.
    Recording that separately leaves Sentry's attribution untouched and makes a caller
    claiming a different address visible as a disagreement between the two.
    """
    if not _should_enable_sentry():
        return
    try:
        address = _connection_address(request)
        if address is None:
            return

        import sentry_sdk

        sentry_sdk.set_tag(CLIENT_ADDRESS_TAG, address)
    except Exception:
        # This runs for every request, so a reporting failure must never fail one.
        sentry_logger.warning("[sentry:report] could not record a connection address", exc_info=True)


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
ISSUED_JOB_ID_SHAPE = "issued_shape"
"""Description of a job identifier that this server could have issued."""
"""Shape of an issued job identifier, used to describe a request for a missing one."""
STREAM_ROUTE_SUFFIX = "/events"
"""Route suffix of the only endpoint accepting a stream token."""


def _describe_job_id(request: Request) -> str | None:
    """Describe a requested job identifier's shape without repeating the identifier."""
    job_id = request.path_params.get("job_id")
    if job_id is None:
        return None
    return ISSUED_JOB_ID_SHAPE if JOB_ID_SHAPE.match(job_id) else "unissued_shape"


def _record_suspicion(request: Request, signal_name: str) -> int:
    """Count this signal's repeats from one address, or `0` when they are not counted."""
    tracker = getattr(request.app.state, "suspicion_tracker", None)
    if tracker is None:
        return 0
    address = _connection_address(request)
    if address is None:
        return 0
    return tracker.record(signal_name, address)


def _escalate_count(request: Request) -> int:
    """Return the repeat count that escalates a signal, or `0` when none escalates it."""
    tracker = getattr(request.app.state, "suspicion_tracker", None)
    return getattr(tracker, "escalate_count", 0) or 0


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
        # Carrying a stream token at all takes knowing this route mints one. A token that
        # neither verifies nor merely aged out was constructed, whatever shape it took, so
        # reporting only the minted shape would let a forgery hide behind any other spelling.
        # An expired one is a stale link, and one shaped as expired cannot authorize anything.
        stream_state = describe_stream_token(request.query_params.get("token"))
        if request.url.path.endswith(STREAM_ROUTE_SUFFIX) and stream_state not in ("absent", "expired"):
            return "forged_stream_token", "error" if stream_state == "live" else "warning"
        if extract_bearer_token(request.headers.get("Authorization")) is not None:
            return "rejected_bearer_token", "warning"
        return None
    if status_code == 404:
        # A missing route is noise, and so is a wordlist path that merely landed on the job
        # route. Only an identifier of the issued shape shows knowledge of what a job ID is.
        if error_code == "job_not_found" and _describe_job_id(request) == ISSUED_JOB_ID_SHAPE:
            return "job_id_probe", "warning"
        return None
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
    try:
        _capture_invalid_request(request, status_code, detail, error_code)
    except Exception:
        # Reporting is never worth failing a request over, and a failure here would also
        # turn a client error into a server error only for the requests worth reporting.
        sentry_logger.warning("[sentry:report] could not report an invalid request", exc_info=True)


def _capture_invalid_request(
    request: Request,
    status_code: int,
    detail: Any,
    error_code: str | None = None,
) -> None:
    """Build and send one report for a client error worth keeping."""
    signal = classify_suspicious_request(request, status_code, error_code)
    # Missing routes, expired resources, and unauthenticated probes of a protected
    # deployment are expected and not actionable.
    if signal is None and status_code in (401, 404):
        return

    import sentry_sdk

    level = "warning"
    occurrences = 0
    if signal is not None:
        signal_name, level = signal
        occurrences = _record_suspicion(request, signal_name)
        escalate_count = _escalate_count(request)
        if occurrences and escalate_count:
            if occurrences > escalate_count:
                # One address cannot spend the project's event quota. The escalated report
                # already names the address, and its counter keeps rising unreported.
                return
            if occurrences == escalate_count:
                # Repetition from one address is deliberate in a way one request is not.
                level = "error"

    route = request.scope.get("route")
    route_path = getattr(route, "path", request.url.path)
    serialized_detail = jsonable_encoder(detail)
    message = "Invalid API request"
    fingerprint = ["invalid-request", str(status_code), route_path]

    with sentry_sdk.new_scope() as scope:
        if signal is not None:
            # Imported here so processes that only report errors do not load the routes.
            from .server.api.optimize import CLIENT_ID_COOKIE_NAME

            signal_name = signal[0]
            message = f"Suspicious API request: {signal_name}"
            fingerprint = ["suspicious-request", signal_name]
            scope.set_tag("request.suspicious", signal_name)
            scope.set_context(
                "suspicious_request",
                {
                    "signal": signal_name,
                    "occurrences": occurrences or None,
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
