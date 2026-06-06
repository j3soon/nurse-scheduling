"""Tests for backend Sentry integration helpers."""

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

import sys
import types
from datetime import UTC, datetime

from nurse_scheduling.jobs import OptimizeJob, OptimizeJobStatus
from nurse_scheduling.loader import _load_yaml
from nurse_scheduling.sentry import capture_optimize_exception


SCHEDULE_YAML = b"""\
apiVersion: alpha
dates:
  groups:
    - id: special-dates
      members: [Alice]
people:
  items:
    - id: Alice
    - id: Bob
  groups:
    - id: P1
      members: [Alice, Bob]
preferences:
  - type: shift request
    person: Alice
  - type: shift type requirement
    qualifiedPeople: [P1]
  - type: shift affinity
    people1: [Alice]
    people2: [[Bob, P1]]
export:
  formatting:
    - type: row
      people: [ALL, Alice, P1]
  extraRows:
    - type: count
      countPeople: [Bob, P1]
"""


def test_capture_optimize_exception_attaches_anonymized_yaml(monkeypatch):
    attachments = []

    class FakeScope:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def set_context(self, name, context):
            pass

        def add_attachment(self, **attachment):
            attachments.append(attachment)

    fake_sentry_sdk = types.SimpleNamespace(
        new_scope=FakeScope,
        capture_exception=lambda error: None,
    )
    monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)
    job = OptimizeJob(
        id="opt_test",
        status=OptimizeJobStatus.RUNNING,
        created_at=datetime.now(UTC),
        input_name="schedule.yaml",
        solver="ortools/cp-sat",
        prettify=True,
        timeout=60,
    )

    capture_optimize_exception(job, SCHEDULE_YAML, ValueError("invalid"))

    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment["filename"] == "schedule.yaml"
    assert b"Bob" not in attachment["bytes"]
    assert _load_yaml(attachment["bytes"])["people"]["items"] == [{"id": "P2"}, {"id": "P3"}]


def test_capture_optimize_exception_attaches_unparseable_raw_yaml(monkeypatch):
    attachments = []
    contexts = []
    captured_errors = []

    class FakeScope:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def set_context(self, name, context):
            contexts.append((name, context))

        def add_attachment(self, **attachment):
            attachments.append(attachment)

    fake_sentry_sdk = types.SimpleNamespace(
        new_scope=FakeScope,
        capture_exception=captured_errors.append,
    )
    monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)
    job = OptimizeJob(
        id="opt_test",
        status=OptimizeJobStatus.RUNNING,
        created_at=datetime.now(UTC),
        input_name="invalid.yaml",
        solver="ortools/cp-sat",
        prettify=True,
        timeout=60,
    )
    error = ValueError("invalid")

    content = b"people: ["
    capture_optimize_exception(job, content, error)

    assert attachments == [
        {
            "bytes": content,
            "filename": "invalid.yaml",
            "content_type": "application/x-yaml",
        }
    ]
    assert contexts == [
        (
            "schedule_state",
            {
                "attached": True,
                "people_ids_anonymized": False,
                "input_name": "invalid.yaml",
                "job_id": "opt_test",
                "size_bytes": len(content),
            },
        )
    ]
    assert captured_errors == [error]
