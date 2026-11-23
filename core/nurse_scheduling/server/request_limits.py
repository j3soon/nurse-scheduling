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

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute
from starlette.datastructures import FormData, Headers
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.requests import AwaitableOrContextManager
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MULTIPART_OVERHEAD_BYTES = 64 * 1024
"""Room for multipart boundaries, part headers, and the small form fields beside the upload."""
OVERSIZE_BODY_MESSAGE = "Request body is too large"


class ScheduleSpecFormRequest(Request):
    """Parse a submission form whose text field can be as large as an uploaded file.

    Starlette limits each text field to 1 MiB by default. `MaxBodySizeMiddleware` already
    bounds the whole body, and the route checks the exact Schedule Spec YAML limit.
    """

    def form(
        self,
        *,
        max_files: float = 1000,
        max_fields: float = 1000,
        max_part_size: int | None = None,
    ) -> AwaitableOrContextManager[FormData]:
        """Read the form with a text field limit no stricter than the body limit."""
        if max_part_size is None:
            max_part_size = self.app.state.settings.max_yaml_bytes + MULTIPART_OVERHEAD_BYTES
        return super().form(max_files=max_files, max_fields=max_fields, max_part_size=max_part_size)


class ScheduleSpecFormRoute(APIRoute):
    """Route class for endpoints that accept Schedule Spec YAML as a form field."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Hand FastAPI a request whose form parser admits the configured YAML size."""
        handler = super().get_route_handler()

        async def route_handler(request: Request) -> Response:
            return await handler(ScheduleSpecFormRequest(request.scope, request.receive))

        return route_handler


class MaxBodySizeMiddleware:
    """Refuse a body larger than any route accepts.

    Route handlers check their own limits, but FastAPI resolves upload parameters before a
    handler runs, so by then Starlette has already spooled the whole body. Checking the
    declared length first keeps that work bounded. A request that omits `Content-Length`
    by using chunked transfer encoding stops when its received bytes pass the limit.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Answer 413 for an oversize body, otherwise run the application."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        declared_length = headers.get("content-length")
        if declared_length is not None and self._exceeds_limit(declared_length):
            response = JSONResponse(
                status_code=413,
                content={"error": {"code": "request_too_large", "message": OVERSIZE_BODY_MESSAGE}},
            )
            await response(scope, receive, send)
            return
        content_type = (headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        is_form_body = content_type in {"multipart/form-data", "application/x-www-form-urlencoded"}
        received = 0

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max_bytes:
                    if is_form_body:
                        # Starlette closes partially spooled files on this exception.
                        raise MultiPartException(OVERSIZE_BODY_MESSAGE)
                    raise HTTPException(status_code=413, detail=OVERSIZE_BODY_MESSAGE)
            return message

        await self._app(scope, bounded_receive, send)

    def _exceeds_limit(self, declared_length: str) -> bool:
        """Return whether a declared body length is above the limit, ignoring an unusable value."""
        try:
            return int(declared_length) > self._max_bytes
        except ValueError:
            # A malformed header is the server's own protocol layer to reject, not ours.
            return False
