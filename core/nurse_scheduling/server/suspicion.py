"""Windowed counting of repeated suspicious requests."""

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
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .config import ServerSettings

KEY_PREFIX = "nurse_scheduling:suspicion:v0"
"""Namespace and schema version prepended to every counter key."""
MAX_TRACKED_COUNTERS = 4096
"""Counters one process retains without Redis, oldest discarded first."""
DIGEST_LENGTH = 16
"""Characters of the salted address digest kept in a counter key."""
REDIS_OPERATION_TIMEOUT_SECONDS = 0.25
"""Longest a count may block. Counting runs inline on the event loop, so a degraded Redis
must cost a bounded pause rather than stall every request the process is serving."""


def address_digest(salt: str, address: str) -> str:
    """Return a salted digest identifying one address.

    Counting never reads an address back, so a digest keeps the counters from becoming a
    record of who connected. The salt is per deployment launch, so digests do not carry
    across restarts or compare between deployments.
    """
    return hashlib.sha256(f"{salt}:{address}".encode()).hexdigest()[:DIGEST_LENGTH]


class SuspicionTracker(Protocol):
    """Counts repeats of one signal from one address within a fixed window."""

    escalate_count: int
    """Occurrences within a window that make a signal worth reporting as an error."""

    def record(self, signal: str, address: str) -> int:
        """Record one occurrence and return the total for its current window.

        Returns `0` when the total is unknown, which never escalates a report.
        """


class MemorySuspicionTracker:
    """Process-local counters for deployments without shared storage.

    Each server process counts only the requests it handled, so a deployment running several
    processes reaches an escalation threshold later than one process would.
    """

    def __init__(
        self,
        *,
        salt: str,
        window_seconds: int,
        escalate_count: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Initialize empty counters bounded by insertion order."""
        self.escalate_count = escalate_count
        self._salt = salt
        self._window_seconds = window_seconds
        self._clock = clock
        self._counters: OrderedDict[tuple[str, str, int], int] = OrderedDict()
        self._lock = threading.Lock()

    def record(self, signal: str, address: str) -> int:
        """Record one occurrence and return the total for its current window."""
        key = (signal, address_digest(self._salt, address), int(self._clock() // self._window_seconds))
        with self._lock:
            total = self._counters.pop(key, 0) + 1
            self._counters[key] = total
            while len(self._counters) > MAX_TRACKED_COUNTERS:
                self._counters.popitem(last=False)
        return total


class RedisSuspicionTracker:
    """Counters shared by every server process through Redis."""

    def __init__(
        self,
        client,
        *,
        salt: str,
        window_seconds: int,
        escalate_count: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Wrap a Redis client with one window length and escalation threshold."""
        self.escalate_count = escalate_count
        self._redis = client
        self._salt = salt
        self._window_seconds = window_seconds
        self._clock = clock

    def record(self, signal: str, address: str) -> int:
        """Record one occurrence and return the total for its current window.

        Returns `0` when Redis is unavailable. Counting is advisory, so a failure must
        neither change the response nor lose the report it would have escalated.
        """
        window = int(self._clock() // self._window_seconds)
        key = f"{KEY_PREFIX}:{signal}:{address_digest(self._salt, address)}:{window}"
        try:
            with self._redis.pipeline(transaction=False) as pipeline:
                pipeline.incr(key)
                # Outlive the window so a counter read late in it still sees the total.
                pipeline.expire(key, self._window_seconds * 2)
                total, _ = pipeline.execute()
            return int(total)
        except Exception:  # noqa: BLE001
            return 0


def create_suspicion_tracker(settings: "ServerSettings", *, salt: str) -> SuspicionTracker | None:
    """Build the tracker this deployment's storage supports, or `None` when disabled."""
    if not settings.suspicion_enabled:
        return None
    if settings.job_backend != "redis":
        return MemorySuspicionTracker(
            salt=salt,
            window_seconds=settings.suspicion_window_seconds,
            escalate_count=settings.suspicion_escalate_count,
        )
    import redis

    return RedisSuspicionTracker(
        redis.Redis.from_url(
            settings.redis_url,
            decode_responses=False,
            socket_connect_timeout=REDIS_OPERATION_TIMEOUT_SECONDS,
            socket_timeout=REDIS_OPERATION_TIMEOUT_SECONDS,
        ),
        salt=salt,
        window_seconds=settings.suspicion_window_seconds,
        escalate_count=settings.suspicion_escalate_count,
    )
