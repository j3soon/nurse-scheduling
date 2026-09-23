"""Reject an oversize request body before the application buffers it."""

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

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MULTIPART_OVERHEAD_BYTES = 64 * 1024
"""Room for multipart boundaries, part headers, and the small form fields beside the upload."""
OVERSIZE_BODY_MESSAGE = "Request body is too large"


class MaxBodySizeMiddleware:
    """Refuse a declared body larger than any route accepts.

    Route handlers check their own limits, but FastAPI resolves upload parameters before a
    handler runs, so by then Starlette has already spooled the whole body. Checking the
    declared length first keeps that work bounded.

    A request that omits `Content-Length` by using chunked transfer encoding is still read
    until a route rejects it, so a deployment that faces the internet directly should also
    bound the body at its proxy.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answer 413 for an oversize declared body, otherwise run the application."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        declared_length = Headers(scope=scope).get("content-length")
        if declared_length is not None and self._exceeds_limit(declared_length):
            response = JSONResponse(
                status_code=413,
                content={"error": {"code": "request_too_large", "message": OVERSIZE_BODY_MESSAGE}},
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)

    def _exceeds_limit(self, declared_length: str) -> bool:
        """Return whether a declared body length is above the limit, ignoring an unusable value."""
        try:
            return int(declared_length) > self._max_bytes
        except ValueError:
            # A malformed header is the server's own protocol layer to reject, not ours.
            return False
