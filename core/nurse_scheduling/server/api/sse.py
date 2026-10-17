"""Server-sent event framing and connection limits for optimization job events."""

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

import json
import threading

from ..jobs.models import JobEvent


def format_sse_event(event: JobEvent) -> str:
    """Serialize one persisted event using the SSE wire format.

    Raises:
        TypeError: If the event payload contains a value unsupported by JSON.
    """
    event_id = f"id: {event.id}\n" if event.id is not None else ""
    payload = {"occurred_at": event.occurred_at.isoformat(), **event.data}
    return f"{event_id}event: {event.type}\ndata: {json.dumps(payload)}\n\n"


class EventStreamLimiter:
    """Count open job event streams per client address in one API process."""

    def __init__(self, limit: int):
        self._limit = limit
        self._open: dict[str, int] = {}
        # The route reserves a slot in a worker thread and the response releases it on the event loop.
        self._lock = threading.Lock()

    def acquire(self, address: str) -> bool:
        """Reserve a stream slot for the address, or return `False` when it holds the limit."""
        with self._lock:
            count = self._open.get(address, 0)
            if count >= self._limit:
                return False
            self._open[address] = count + 1
            return True

    def release(self, address: str) -> None:
        """Free one stream slot that `acquire` reserved for the address."""
        with self._lock:
            remaining = self._open[address] - 1
            if remaining:
                self._open[address] = remaining
            else:
                del self._open[address]
