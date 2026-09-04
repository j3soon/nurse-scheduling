"""Small retry primitive shared by backend infrastructure operations."""

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

import time
from collections.abc import Callable
from typing import TypeVar

RetryResult = TypeVar("RetryResult")
DEFAULT_RETRY_MAX_ATTEMPTS = 20
"""Default attempts used by backend read and write retries."""
DEFAULT_RETRY_INITIAL_DELAY_SECONDS = 0.001
"""Default delay after the first retryable failure."""
DEFAULT_RETRY_MAX_DELAY_SECONDS = 0.05
"""Default maximum delay between retry attempts."""


DEFAULT_OUTAGE_MAX_DELAY_SECONDS = 5.0
"""Longest a recurring background operation waits after repeated failures."""


class RepeatedFailure:
    """Slow and quiet a recurring operation while its dependency stays unavailable.

    A background loop that retries on a fixed interval turns one outage into an unbounded
    stream of identical reports, which costs the error budget exactly when it is needed. This
    reports the first failure and the recovery, and lengthens the wait in between.
    """

    def __init__(self, *, base_delay_seconds: float, max_delay_seconds: float = DEFAULT_OUTAGE_MAX_DELAY_SECONDS):
        """Configure the normal retry delay and the longest delay backoff may reach."""
        if base_delay_seconds <= 0 or max_delay_seconds < base_delay_seconds:
            raise ValueError("repeated failure delays must be positive and ordered")
        self._base_delay_seconds = base_delay_seconds
        self._max_delay_seconds = max_delay_seconds
        self._failures = 0

    @property
    def failures(self) -> int:
        """Number of consecutive failures recorded since the last success."""
        return self._failures

    def report(self) -> bool:
        """Record one failure and return whether it is the one worth reporting."""
        self._failures += 1
        return self._failures == 1

    def delay_seconds(self) -> float:
        """Return how long to wait before retrying, growing while failures continue."""
        if self._failures <= 1:
            return self._base_delay_seconds
        return min(self._base_delay_seconds * (2 ** (self._failures - 1)), self._max_delay_seconds)

    def recovered(self) -> int:
        """Record one success and return how many consecutive failures it ended."""
        ended, self._failures = self._failures, 0
        return ended


# Keep the Python 3.10-compatible TypeVar form.
def retry_with_backoff(
    operation: Callable[[], RetryResult],
    *,
    retry_on: type[Exception] | tuple[type[Exception], ...],
    max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS,
    initial_delay_seconds: float = DEFAULT_RETRY_INITIAL_DELAY_SECONDS,
    max_delay_seconds: float = DEFAULT_RETRY_MAX_DELAY_SECONDS,
) -> RetryResult:
    """Retry selected exceptions with bounded exponential backoff."""
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    if initial_delay_seconds < 0 or max_delay_seconds < initial_delay_seconds:
        raise ValueError("retry delays must be nonnegative and ordered")

    for attempt in range(max_attempts):
        try:
            return operation()
        except retry_on:
            if attempt + 1 == max_attempts:
                raise
            delay_seconds = min(initial_delay_seconds * (2**attempt), max_delay_seconds)
            time.sleep(delay_seconds)
    raise AssertionError("retry loop ended without returning or raising")
