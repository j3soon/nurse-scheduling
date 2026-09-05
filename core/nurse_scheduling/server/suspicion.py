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

# This file is mostly AI generated.

import hashlib
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .config import ServerSettings

KEY_PREFIX = "nurse_scheduling:suspicion:v0"
"""Namespace and schema version prepended to every counter key."""
MAX_TRACKED_COUNTERS = 4096
"""Counters one process retains without Redis, oldest discarded first."""
MAX_TRACKED_SUBJECTS = 64
"""Distinct subjects one counter retains without Redis, which is past every threshold.

Bounded low because every counter may hold this many at once, and the retained digests
are released only by insertion pressure."""
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


@dataclass(frozen=True)
class SuspicionCount:
    """What one address has done with one signal inside the current window."""

    occurrences: int = 0
    """Requests carrying this signal, or `0` when the total is unknown."""
    distinct_subjects: int = 0
    """Distinct subjects named, or `0` when the signal names none.

    A signal repeated against one subject is a client stuck on it, while the same count
    spread across many is a caller working through them. Only the second is deliberate.
    """


class SuspicionTracker(Protocol):
    """Counts repeats of one signal from one address within a fixed window."""

    escalate_count: int
    """Occurrences within a window that make a signal worth reporting as an error."""

    def record(self, signal: str, address: str, subject: str | None = None) -> SuspicionCount:
        """Record one occurrence and return what this address has done in this window."""


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
        self._subjects: OrderedDict[tuple[str, str, int], set[int]] = OrderedDict()
        self._lock = threading.Lock()

    def record(self, signal: str, address: str, subject: str | None = None) -> SuspicionCount:
        """Record one occurrence and return what this address has done in this window."""
        key = (signal, address_digest(self._salt, address), int(self._clock() // self._window_seconds))
        with self._lock:
            total = self._counters.pop(key, 0) + 1
            self._counters[key] = total
            while len(self._counters) > MAX_TRACKED_COUNTERS:
                self._counters.popitem(last=False)
            distinct = 0
            if subject is not None:
                seen = self._subjects.pop(key, set())
                if len(seen) < MAX_TRACKED_SUBJECTS:
                    seen.add(hash(address_digest(self._salt, subject)))
                self._subjects[key] = seen
                distinct = len(seen)
                while len(self._subjects) > MAX_TRACKED_COUNTERS:
                    self._subjects.popitem(last=False)
        return SuspicionCount(occurrences=total, distinct_subjects=distinct)


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
        self._fallback = MemorySuspicionTracker(
            salt=salt,
            window_seconds=window_seconds,
            escalate_count=escalate_count,
            clock=clock,
        )
        """Counts within this process while Redis is unavailable.

        A report is capped by its count, so losing the count during an outage would remove
        the cap at the moment the error budget matters most.
        """

    def record(self, signal: str, address: str, subject: str | None = None) -> SuspicionCount:
        """Record one occurrence and return what this address has done in this window.

        Falls back to counting within this process when Redis is unavailable, which counts
        only what this process saw but keeps a count rather than none. Counting is advisory,
        so a failure must neither change the response nor lose the report it would escalate.

        Distinct subjects are counted approximately, which is exact at the small counts a
        threshold compares against and only loses precision far above one.
        """
        window = int(self._clock() // self._window_seconds)
        key = f"{KEY_PREFIX}:{signal}:{address_digest(self._salt, address)}:{window}"
        ttl_seconds = self._window_seconds * 2
        try:
            with self._redis.pipeline(transaction=False) as pipeline:
                pipeline.incr(key)
                # Outlive the window so a counter read late in it still sees the total.
                pipeline.expire(key, ttl_seconds)
                if subject is not None:
                    # A fixed-size sketch, so a caller naming endless subjects cannot grow it.
                    pipeline.pfadd(f"{key}:subjects", address_digest(self._salt, subject))
                    pipeline.expire(f"{key}:subjects", ttl_seconds)
                    pipeline.pfcount(f"{key}:subjects")
                results = pipeline.execute()
            return SuspicionCount(
                occurrences=int(results[0]),
                distinct_subjects=int(results[-1]) if subject is not None else 0,
            )
        except Exception:  # noqa: BLE001
            return self._fallback.record(signal, address, subject)


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
