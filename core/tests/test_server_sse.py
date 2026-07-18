"""Focused tests for optimization server-sent event framing."""

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

import json
from datetime import datetime, timezone

import pytest

from nurse_scheduling.server.api.sse import format_sse_event
from nurse_scheduling.server.jobs.models import JobEvent


def _payload(frame: str) -> dict:
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))


def test_format_sse_event_includes_id_topic_json_data_and_final_blank_line():
    occurred_at = datetime(2026, 7, 18, 12, 30, tzinfo=timezone.utc)

    frame = format_sse_event(
        JobEvent(
            id="7",
            type="job.test",
            data={"state": "running"},
            occurred_at=occurred_at,
        )
    )

    assert frame.startswith("id: 7\nevent: job.test\ndata: ")
    assert frame.endswith("\n\n")
    assert _payload(frame) == {
        "state": "running",
        "occurred_at": "2026-07-18T12:30:00+00:00",
    }


def test_format_sse_event_omits_absent_id():
    frame = format_sse_event(
        JobEvent(
            type="job.test",
            data={},
            occurred_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
        )
    )

    assert not frame.startswith("id:")
    assert frame.startswith("event: job.test\n")


def test_format_sse_event_uses_persisted_timestamp_on_payload_collision():
    frame = format_sse_event(
        JobEvent(
            type="job.test",
            data={"occurred_at": "spoofed"},
            occurred_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
        )
    )

    assert _payload(frame)["occurred_at"] == "2026-07-18T00:00:00+00:00"


def test_format_sse_event_propagates_json_serialization_errors():
    event = JobEvent(
        type="job.test",
        data={"unsupported": {1, 2}},
        occurred_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
    )

    with pytest.raises(TypeError):
        format_sse_event(event)
