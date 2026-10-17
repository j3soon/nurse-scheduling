"""Check that persistent AI streams cannot stall the security probe."""

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

import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("probe.py")
with patch.object(sys, "argv", [str(SCRIPT), str(SCRIPT.parents[3])]):
    PROBE = runpy.run_path(str(SCRIPT))


class ProbeReplyTests(unittest.TestCase):
    def test_reply_stops_reading_the_persistent_stream(self) -> None:
        def lines():
            yield "event: text"
            yield 'data: {"text": "Scan reply."}'
            self.fail("The probe kept reading after the reply")

        self.assertTrue(PROBE["received_stub_reply"](lines()))

    def test_terminal_events_stop_reading_without_a_reply(self) -> None:
        for event in ("error", "done", "stopped", "stale"):
            with self.subTest(event=event):

                def lines(event_name=event):
                    yield f"event: {event_name}"
                    self.fail("The probe kept reading after the turn ended")

                self.assertFalse(PROBE["received_stub_reply"](lines()))

    def test_keepalives_cannot_extend_the_total_wait(self) -> None:
        def lines():
            yield ": keepalive"
            yield ": keepalive"
            self.fail("The probe kept reading past its deadline")

        with patch("time.monotonic", side_effect=[0.0, 1.0, 16.0]):
            self.assertFalse(PROBE["received_stub_reply"](lines()))


if __name__ == "__main__":
    unittest.main()
