"""Bounded provider retry classification and delays, following Pi v1.0.0."""

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

import math
import random
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

MAX_RETRY_DELAY_SECONDS = 60.0
_NON_RETRYABLE_LIMIT = re.compile(
    r"GoUsageLimitError|FreeUsageLimitError|Monthly usage limit reached|available balance|"
    r"insufficient_quota|out of budget|quota exceeded|billing|subscription_sharing_usage_limit_exceeded",
    re.IGNORECASE,
)


def is_retryable_status(status: int, headers: httpx.Headers, body: str) -> bool:
    """Follow Pi's transient status policy, excluding account and request failures."""
    if status in {400, 401, 402, 403, 404, 405, 407, 413, 415, 422} or _NON_RETRYABLE_LIMIT.search(body):
        return False
    hint = headers.get("x-should-retry")
    if hint in {"true", "false"}:
        return hint == "true"
    return status in {408, 409, 429} or status >= 500


def retry_delay(
    headers: httpx.Headers, attempt: int, base_seconds: float, *, now: datetime | None = None
) -> float | None:
    """Return Pi's bounded server delay or jittered backoff. None refuses a long wait."""
    for name, scale in (("retry-after-ms", 0.001), ("retry-after", 1.0)):
        raw = headers.get(name)
        if raw is None:
            continue
        try:
            delay = float(raw) * scale
        except ValueError:
            if name != "retry-after":
                continue
            try:
                at = parsedate_to_datetime(raw)
                if at.tzinfo is None:
                    at = at.replace(tzinfo=UTC)
                delay = max(0.0, (at - (now or datetime.now(UTC))).total_seconds())
            except (ValueError, TypeError, OverflowError):
                continue
        if math.isfinite(delay) and delay >= 0:
            return delay if delay <= MAX_RETRY_DELAY_SECONDS else None
    backoff = min(8.0, base_seconds * 2 ** min(attempt - 1, 30))
    return backoff * (1 - random.random() * 0.25)
