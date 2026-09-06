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
import json
import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, Request

AUTH_TOKEN_ENV_NAME = "API_AUTH_TOKEN"
"""Environment setting holding the shared token."""
AUTH_TOKENS_ENV_NAME = "API_AUTH_TOKENS"
"""Environment setting holding a JSON object of administrative IDs to tokens."""
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
LEGACY_AUTH_CREDENTIAL_ID = "legacy"
"""Internal identifier assigned to the backward-compatible single token."""
_CREDENTIAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_STREAM_SELECTOR_MESSAGE = b"nurse-scheduling-stream-credential-selector"


@dataclass(frozen=True)
class AuthCredential:
    """One static bearer token and its administrative identifier."""

    id: str
    token: str


class AuthTokenRegistry:
    """Immutable static credentials indexed by a token fingerprint."""

    def __init__(self, credentials: tuple[AuthCredential, ...]) -> None:
        self._lookup_secret = secrets.token_bytes(32)
        self._credentials_by_id = {credential.id: credential for credential in credentials}
        self._credentials_by_fingerprint = {
            self._fingerprint(credential.token): credential for credential in credentials
        }
        self._credentials_by_stream_selector = {
            self._stream_selector(credential.token): credential for credential in credentials
        }

    def _fingerprint(self, token: str) -> bytes:
        """Return the fixed-length lookup key for a bearer token."""
        return hmac.new(self._lookup_secret, token.encode("utf-8"), hashlib.sha256).digest()

    @property
    def enabled(self) -> bool:
        """Return whether at least one credential is configured."""
        return bool(self._credentials_by_id)

    def authenticate(self, token: str) -> AuthCredential | None:
        """Resolve a bearer token without iterating over the credential set."""
        credential = self._credentials_by_fingerprint.get(self._fingerprint(token))
        if credential is None:
            return None
        if not hmac.compare_digest(token.encode("utf-8"), credential.token.encode("utf-8")):
            return None
        return credential

    def get(self, credential_id: str) -> AuthCredential | None:
        """Return the credential with an administrative identifier."""
        return self._credentials_by_id.get(credential_id)

    @staticmethod
    def _stream_selector(token: str) -> str:
        """Derive a stable opaque stream selector without exposing the administrative ID."""
        return hmac.new(token.encode("utf-8"), _STREAM_SELECTOR_MESSAGE, hashlib.sha256).hexdigest()

    def stream_selector(self, credential: AuthCredential) -> str:
        """Return the opaque selector embedded in this credential's stream tokens."""
        return self._stream_selector(credential.token)

    def get_by_stream_selector(self, selector: str) -> AuthCredential | None:
        """Resolve an opaque stream selector without scanning credentials."""
        return self._credentials_by_stream_selector.get(selector)


def parse_auth_credentials(value: str | None, *, name: str = AUTH_TOKENS_ENV_NAME) -> tuple[AuthCredential, ...]:
    """Parse a JSON object of administrative IDs to tokens."""
    if value is None or not value.strip():
        return ()
    raw_value = value.strip()
    if not raw_value.startswith("{"):
        raise ValueError(f"{name} must be a JSON object of ID-to-token strings")
    try:
        pairs = json.loads(raw_value, object_pairs_hook=lambda items: items)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} must be a valid JSON object of ID-to-token strings") from error
    credentials: list[AuthCredential] = []
    for credential_id, token in pairs:
        if not isinstance(token, str):
            raise ValueError(f"{name} values must be strings")  # noqa: TRY004
        credentials.append(AuthCredential(id=credential_id, token=token))
    return tuple(credentials)


def normalize_auth_credentials(
    legacy_token: str | None,
    credentials: tuple[AuthCredential, ...],
    *,
    legacy_name: str = AUTH_TOKEN_ENV_NAME,
    credentials_name: str = AUTH_TOKENS_ENV_NAME,
    required_name: str = AUTH_REQUIRED_ENV_NAME,
    required: bool,
) -> tuple[str | None, tuple[AuthCredential, ...]]:
    """Validate legacy and identified bearer credentials as one configuration."""
    normalized_legacy = normalize_auth_token(legacy_token, name=legacy_name, warn_on_short=not required)
    normalized_credentials: list[AuthCredential] = []
    ids: set[str] = set()
    tokens: set[str] = set()
    for credential in credentials:
        credential_id = credential.id.strip()
        if not _CREDENTIAL_ID_PATTERN.fullmatch(credential_id):
            raise ValueError(f"{credentials_name} IDs must use only letters, numbers, underscores, and hyphens")
        if credential_id == LEGACY_AUTH_CREDENTIAL_ID:
            raise ValueError(f"{credentials_name} ID {LEGACY_AUTH_CREDENTIAL_ID!r} is reserved")
        token = normalize_auth_token(credential.token, name=credentials_name, warn_on_short=not required)
        if token is None:
            raise ValueError(f"{credentials_name} tokens must not be empty")
        if credential_id in ids:
            raise ValueError(f"{credentials_name} contains duplicate ID {credential_id!r}")
        if token in tokens or token == normalized_legacy:
            raise ValueError(f"{credentials_name} contains a duplicate token")
        if required and len(token) < RECOMMENDED_AUTH_TOKEN_LENGTH:
            raise ValueError(
                f"{credentials_name} tokens must be at least {RECOMMENDED_AUTH_TOKEN_LENGTH} characters when "
                f"{required_name} is set"
            )
        ids.add(credential_id)
        tokens.add(token)
        normalized_credentials.append(AuthCredential(id=credential_id, token=token))
    if required and normalized_legacy is not None and len(normalized_legacy) < RECOMMENDED_AUTH_TOKEN_LENGTH:
        raise ValueError(
            f"{legacy_name} must be at least {RECOMMENDED_AUTH_TOKEN_LENGTH} characters when {required_name} is set"
        )
    if required and normalized_legacy is None and not normalized_credentials:
        raise ValueError(f"{required_name} is set, so {legacy_name} or {credentials_name} must not be empty")
    return normalized_legacy, tuple(normalized_credentials)


def create_auth_registry(
    legacy_token: str | None, credentials: tuple[AuthCredential, ...]
) -> AuthTokenRegistry:
    """Build the runtime registry, assigning the legacy token its reserved ID."""
    combined = credentials
    if legacy_token is not None:
        combined = (AuthCredential(id=LEGACY_AUTH_CREDENTIAL_ID, token=legacy_token), *combined)
    return AuthTokenRegistry(combined)


def normalize_auth_token(
    value: str | None,
    *,
    name: str = AUTH_TOKEN_ENV_NAME,
    warn_on_short: bool = True,
) -> str | None:
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
        raise ValueError(f"{name} must contain only ASCII characters")
    if warn_on_short and len(token) < RECOMMENDED_AUTH_TOKEN_LENGTH:
        auth_logger.warning(
            "[server:auth] %s is shorter than %d characters and is unsafe outside local testing",
            name,
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
    credential_selector: str | None = None,
    now: datetime | None = None,
) -> str:
    """Mint a short-lived token authorizing only one job's event stream.

    `EventSource` cannot send an `Authorization` header, so the stream is authorized by a
    URL parameter instead. The token is scoped to one job and expires, which keeps the
    deployment's shared token out of URLs, proxy logs, and referrer headers.
    """
    issued_at = now or datetime.now(timezone.utc)
    expires_at = int(issued_at.timestamp()) + ttl_seconds
    signature = _stream_signature(secret, job_id, expires_at)
    if credential_selector is None:
        return f"{expires_at}.{signature}"
    return f"{credential_selector}.{expires_at}.{signature}"


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


def create_auth_dependency(registry: AuthTokenRegistry) -> Callable[[Request], None]:
    """Build a route dependency enforcing the configured shared token.

    The returned dependency accepts every request when no token is configured, which keeps
    local and default deployments unauthenticated.
    """

    def require_auth(request: Request) -> None:
        """Reject a request that does not present the configured shared token.

        Raises:
            HTTPException: With status 401 when credentials are missing or invalid.
        """
        if not registry.enabled:
            request.state.auth_credential_id = None
            return
        provided_token = extract_bearer_token(request.headers.get("Authorization"))
        if provided_token is None:
            raise HTTPException(
                status_code=401,
                detail=MISSING_CREDENTIALS_MESSAGE,
                headers=_AUTHENTICATE_HEADERS,
            )
        credential = registry.authenticate(provided_token)
        if credential is None:
            raise HTTPException(
                status_code=401,
                detail=INVALID_CREDENTIALS_MESSAGE,
                headers=_AUTHENTICATE_HEADERS,
            )
        request.state.auth_credential_id = credential.id

    return require_auth


def create_stream_auth_dependency(registry: AuthTokenRegistry) -> Callable[[Request], None]:
    """Build a route dependency accepting the shared token or a job's stream token."""

    def require_stream_auth(request: Request) -> None:
        """Reject a stream request presenting neither accepted credential.

        Raises:
            HTTPException: With status 401 when credentials are missing or invalid.
        """
        if not registry.enabled:
            request.state.auth_credential_id = None
            return
        provided_token = extract_bearer_token(request.headers.get("Authorization"))
        credential = registry.authenticate(provided_token) if provided_token is not None else None
        if credential is not None:
            request.state.auth_credential_id = credential.id
            return
        job_id = request.path_params.get("job_id", "")
        token = request.query_params.get("token")
        credential_selector, separator, legacy_or_expiry = (token or "").partition(".")
        if separator:
            identified_credential = registry.get_by_stream_selector(credential_selector)
            if identified_credential is not None and verify_stream_token(
                identified_credential.token,
                job_id,
                f"{legacy_or_expiry}",
            ):
                request.state.auth_credential_id = identified_credential.id
                return
            legacy_credential = registry.get(LEGACY_AUTH_CREDENTIAL_ID)
            if legacy_credential is not None and verify_stream_token(legacy_credential.token, job_id, token):
                request.state.auth_credential_id = legacy_credential.id
                return
        raise HTTPException(
            status_code=401,
            detail=INVALID_CREDENTIALS_MESSAGE if provided_token else MISSING_CREDENTIALS_MESSAGE,
            headers=_AUTHENTICATE_HEADERS,
        )

    return require_stream_auth
