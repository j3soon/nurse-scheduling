"""Optional shared-token authentication for protected API routes."""

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

import hashlib
import hmac
import logging
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import HTTPException, Request

AUTH_TOKEN_ENV_NAME = "API_AUTH_TOKEN"
"""Environment setting holding the shared token."""
AUTH_REQUIRED_ENV_NAME = "API_AUTH_REQUIRED"
"""Environment setting requiring authentication, baked into images built for deployment."""
AUTH_SCHEME = "bearer"
"""Authentication scheme advertised by `/info` and required in `Authorization`."""
RECOMMENDED_AUTH_TOKEN_LENGTH = 16
"""Shortest shared token considered hard enough to guess on an internet-facing deployment."""
STREAM_TOKEN_GRACE_SECONDS = 10
"""Slack added to a stream token's lifetime for clock skew and the delay before it is used."""
MISSING_CREDENTIALS_MESSAGE = "Backend credentials are required."
INVALID_CREDENTIALS_MESSAGE = "Backend credentials are invalid."
_AUTHENTICATE_HEADERS = {"WWW-Authenticate": "Bearer"}

auth_logger = logging.getLogger("nurse_scheduling.server.auth")


def normalize_auth_token(value: str | None) -> str | None:
    """Return the shared token, or `None` when authentication is disabled.

    A short token is accepted with a warning rather than refused, so local testing is not
    blocked while a deployment still gets a clear signal to use a generated secret.
    """
    if value is None:
        return None
    token = value.strip()
    if not token:
        return None
    # A non-ASCII token cannot be carried by an HTTP header, so accepting one would start a
    # server that rejects every client for a reason no response explains.
    if not token.isascii():
        raise ValueError(f"{AUTH_TOKEN_ENV_NAME} must contain only ASCII characters")
    if len(token) < RECOMMENDED_AUTH_TOKEN_LENGTH:
        auth_logger.warning(
            "[server:auth] %s is shorter than %d characters and is unsafe outside local testing",
            AUTH_TOKEN_ENV_NAME,
            RECOMMENDED_AUTH_TOKEN_LENGTH,
        )
    return token


def extract_bearer_token(header_value: str | None) -> str | None:
    """Return the token carried by an `Authorization: Bearer <token>` header."""
    if not header_value:
        return None
    scheme, _, token = header_value.partition(" ")
    if scheme.strip().lower() != AUTH_SCHEME:
        return None
    token = token.strip()
    return token or None


def _stream_signature(secret: str, job_id: str, expires_at: int) -> str:
    """Sign one job identifier and expiry with the deployment's shared token."""
    message = f"{job_id}:{expires_at}".encode()
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def create_stream_token(
    secret: str,
    job_id: str,
    *,
    ttl_seconds: int,
    now: datetime | None = None,
) -> str:
    """Mint a short-lived token authorizing only one job's event stream.

    `EventSource` cannot send an `Authorization` header, so the stream is authorized by a
    URL parameter instead. The token is scoped to one job and expires, which keeps the
    deployment's shared token out of URLs, proxy logs, and referrer headers.
    """
    issued_at = now or datetime.now(timezone.utc)
    expires_at = int(issued_at.timestamp()) + ttl_seconds
    return f"{expires_at}.{_stream_signature(secret, job_id, expires_at)}"


def verify_stream_token(secret: str, job_id: str, token: str | None, *, now: datetime | None = None) -> bool:
    """Return whether a token authorizes this job's event stream and has not expired."""
    expires_text, separator, signature = (token or "").partition(".")
    if not separator:
        return False
    try:
        expires_at = int(expires_text)
    except ValueError:
        return False
    current_time = int((now or datetime.now(timezone.utc)).timestamp())
    if current_time > expires_at:
        return False
    return hmac.compare_digest(signature, _stream_signature(secret, job_id, expires_at))


def create_auth_dependency(expected_token: str | None) -> Callable[[Request], None]:
    """Build a route dependency enforcing the configured shared token.

    The returned dependency accepts every request when no token is configured, which keeps
    local and default deployments unauthenticated.
    """

    def require_auth(request: Request) -> None:
        """Reject a request that does not present the configured shared token.

        Raises:
            HTTPException: With status 401 when credentials are missing or invalid.
        """
        if expected_token is None:
            return
        provided_token = extract_bearer_token(request.headers.get("Authorization"))
        if provided_token is None:
            raise HTTPException(
                status_code=401,
                detail=MISSING_CREDENTIALS_MESSAGE,
                headers=_AUTHENTICATE_HEADERS,
            )
        # Compare in constant time so responses do not leak the expected token.
        if not hmac.compare_digest(provided_token.encode("utf-8"), expected_token.encode("utf-8")):
            raise HTTPException(
                status_code=401,
                detail=INVALID_CREDENTIALS_MESSAGE,
                headers=_AUTHENTICATE_HEADERS,
            )

    return require_auth


def create_stream_auth_dependency(expected_token: str | None) -> Callable[[Request], None]:
    """Build a route dependency accepting the shared token or a job's stream token."""

    def require_stream_auth(request: Request) -> None:
        """Reject a stream request presenting neither accepted credential.

        Raises:
            HTTPException: With status 401 when credentials are missing or invalid.
        """
        if expected_token is None:
            return
        provided_token = extract_bearer_token(request.headers.get("Authorization"))
        if provided_token is not None and hmac.compare_digest(
            provided_token.encode("utf-8"), expected_token.encode("utf-8")
        ):
            return
        job_id = request.path_params.get("job_id", "")
        if job_id and verify_stream_token(expected_token, job_id, request.query_params.get("token")):
            return
        raise HTTPException(
            status_code=401,
            detail=INVALID_CREDENTIALS_MESSAGE if provided_token else MISSING_CREDENTIALS_MESSAGE,
            headers=_AUTHENTICATE_HEADERS,
        )

    return require_stream_auth
