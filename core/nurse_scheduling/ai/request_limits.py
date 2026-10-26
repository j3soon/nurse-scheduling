"""Authenticate AI session requests and bound their bodies before parsing."""

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

# This file is mostly AI generated.

from collections.abc import Callable

from starlette._utils import get_route_path
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..server.request_limits import MULTIPART_OVERHEAD_BYTES
from .config import AiSettings

JSON_MAX_BYTES = 64 * 1024 * 1024
BODY_TOO_LARGE_MESSAGE = "AI request body is too large."


class AiRequestLimitsMiddleware:
    """Check credentials before FastAPI buffers JSON, then count received bytes."""

    def __init__(self, app: ASGIApp, *, settings: AiSettings, require_auth: Callable[[Request], None]) -> None:
        self._app = app
        self._require_auth = require_auth
        self._json_max_bytes = JSON_MAX_BYTES
        # The browser uploads one file per request.
        self._upload_max_bytes = settings.max_attachment_bytes + MULTIPART_OVERHEAD_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        path = get_route_path(scope).rstrip("/")
        if scope["method"] != "OPTIONS" and (path == "/sessions" or path.startswith("/sessions/")):
            try:
                self._require_auth(Request(scope))
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
                await response(scope, receive, send)
                return
        is_upload = scope["method"] == "POST" and path.startswith("/sessions/") and path.endswith("/uploads")
        max_bytes = self._upload_max_bytes if is_upload else self._json_max_bytes
        declared_length = Headers(scope=scope).get("content-length")
        try:
            oversized = declared_length is not None and int(declared_length) > max_bytes
        except ValueError:
            oversized = False
        if oversized:
            await JSONResponse({"detail": BODY_TOO_LARGE_MESSAGE}, status_code=413)(scope, receive, send)
            return
        received = 0

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    if is_upload:
                        # Starlette closes partially spooled files for multipart parsing errors.
                        raise MultiPartException(BODY_TOO_LARGE_MESSAGE)
                    raise HTTPException(status_code=413, detail=BODY_TOO_LARGE_MESSAGE)
            return message

        await self._app(scope, bounded_receive, send)
