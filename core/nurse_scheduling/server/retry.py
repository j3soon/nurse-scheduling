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
