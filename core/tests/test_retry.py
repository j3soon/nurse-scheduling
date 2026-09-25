"""Tests for retry and repeated-failure helpers used by background loops."""

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

from nurse_scheduling.server.maintenance import JobMaintenance
from nurse_scheduling.server.retry import RepeatedFailure


def _failure(**updates) -> RepeatedFailure:
    values = {"base_delay_seconds": 1.0, "max_delay_seconds": 5.0}
    values.update(updates)
    return RepeatedFailure(**values)


def test_only_the_first_failure_of_a_run_is_worth_reporting():
    repeated = _failure()

    assert [repeated.report() for _ in range(5)] == [True, False, False, False, False]


def test_a_delay_grows_while_failures_continue_and_stops_at_the_maximum():
    repeated = _failure()

    delays = []
    for _ in range(6):
        repeated.report()
        delays.append(repeated.delay_seconds())

    assert delays == [1.0, 2.0, 4.0, 5.0, 5.0, 5.0]


def test_a_long_outage_keeps_the_delay_capped_without_overflow():
    repeated = _failure()
    for _ in range(1100):
        repeated.report()

    assert repeated.delay_seconds() == 5.0


def test_recovery_reports_the_run_it_ended_and_starts_over():
    repeated = _failure()
    for _ in range(3):
        repeated.report()

    assert repeated.recovered() == 3
    assert repeated.failures == 0
    assert repeated.recovered() == 0
    # The next failure reports again, because it begins a new run.
    assert repeated.report() is True


def test_an_operation_that_never_failed_reports_no_recovery():
    assert _failure().recovered() == 0


@pytest.mark.parametrize(
    ("base", "maximum"),
    [
        (0.0, 5.0),
        (-1.0, 5.0),
        (2.0, 1.0),
        (float("nan"), 5.0),
        (float("inf"), 5.0),
        (1.0, float("nan")),
        (1.0, float("inf")),
    ],
)
def test_unusable_delays_are_refused(base, maximum):
    with pytest.raises(ValueError):
        RepeatedFailure(base_delay_seconds=base, max_delay_seconds=maximum)


def test_maintenance_backs_off_while_the_store_is_unavailable():
    class FailingController:
        def expire_worker_claims(self):
            raise RuntimeError("store unavailable")

    class RecordingStop:
        def __init__(self):
            self.delays = []

        def wait(self, delay):
            self.delays.append(delay)
            return len(self.delays) == 5

    maintenance = JobMaintenance(FailingController(), interval_seconds=1)
    stop = RecordingStop()
    maintenance._stop = stop

    maintenance._run()

    assert stop.delays == [1, 1, 2, 4, 4]
