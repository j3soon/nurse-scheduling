"""Tests for windowed counting of repeated suspicious requests."""

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

# This test is mostly AI generated.

import pytest

from nurse_scheduling.server.config import ServerSettings
from nurse_scheduling.server.suspicion import (
    MAX_TRACKED_COUNTERS,
    MemorySuspicionTracker,
    RedisSuspicionTracker,
    address_digest,
    create_suspicion_tracker,
)


class FakeClock:
    """Advanceable stand-in for wall-clock time."""

    def __init__(self, now: float = 1_000_000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def _tracker(clock=None, **updates) -> MemorySuspicionTracker:
    values = {"salt": "salt", "window_seconds": 300, "escalate_count": 5}
    values.update(updates)
    return MemorySuspicionTracker(clock=clock or FakeClock(), **values)


def test_repeats_of_one_signal_from_one_address_accumulate():
    tracker = _tracker()

    totals = [tracker.record("job_id_probe", "203.0.113.7") for _ in range(3)]

    assert totals == [1, 2, 3]


def test_separate_signals_and_addresses_count_separately():
    tracker = _tracker()

    assert tracker.record("job_id_probe", "203.0.113.7") == 1
    assert tracker.record("job_id_probe", "203.0.113.8") == 1
    assert tracker.record("timeout_out_of_range", "203.0.113.7") == 1


def test_a_new_window_starts_a_new_count():
    clock = FakeClock()
    tracker = _tracker(clock=clock, window_seconds=300)

    assert tracker.record("job_id_probe", "203.0.113.7") == 1
    clock.now += 300
    assert tracker.record("job_id_probe", "203.0.113.7") == 1


def test_counts_within_a_window_survive_time_passing_inside_it():
    clock = FakeClock(now=300.0)
    tracker = _tracker(clock=clock, window_seconds=300)

    assert tracker.record("job_id_probe", "203.0.113.7") == 1
    clock.now += 299
    assert tracker.record("job_id_probe", "203.0.113.7") == 2


def test_tracked_counters_stay_bounded():
    tracker = _tracker()

    for index in range(MAX_TRACKED_COUNTERS + 50):
        tracker.record("job_id_probe", f"203.0.113.{index}")

    assert len(tracker._counters) == MAX_TRACKED_COUNTERS


def test_a_digest_hides_the_address_and_does_not_compare_across_salts():
    digest = address_digest("salt", "203.0.113.7")

    assert "203.0.113.7" not in digest
    assert digest == address_digest("salt", "203.0.113.7")
    assert digest != address_digest("other-salt", "203.0.113.7")


def test_redis_counting_failure_reports_an_unknown_total():
    import redis

    class FailingRedis:
        def pipeline(self, transaction=True):
            raise redis.ConnectionError("unavailable")

    tracker = RedisSuspicionTracker(
        FailingRedis(),
        salt="salt",
        window_seconds=300,
        escalate_count=5,
        clock=FakeClock(),
    )

    # Counting is advisory, so an unavailable Redis must not lose the report it would escalate.
    assert tracker.record("job_id_probe", "203.0.113.7") == 0


@pytest.mark.parametrize("enabled", [True, False])
def test_the_tracker_follows_the_configured_setting(enabled):
    settings = ServerSettings(suspicion_enabled=enabled)

    tracker = create_suspicion_tracker(settings, salt="salt")

    assert isinstance(tracker, MemorySuspicionTracker) if enabled else tracker is None
