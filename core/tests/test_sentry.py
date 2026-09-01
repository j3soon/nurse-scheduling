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
from datetime import datetime, timezone

import pytest

from nurse_scheduling.loader import _load_yaml
from nurse_scheduling.sentry import capture_invalid_request, capture_optimize_exception, init_sentry
from nurse_scheduling.server.jobs.models import Job, JobRequest, JobState

SCHEDULE_YAML = b"""\
apiVersion: alpha
description: Sensitive schedule
dates:
  groups:
    - id: special-dates
      members: [Alice]
      description: Sensitive date group
people:
  items:
    - id: Alice
      description: Sensitive Alice
    - id: Bob
      description: Sensitive Bob
  groups:
    - id: P1
      members: [Alice, Bob]
      description: Sensitive people group
preferences:
  - type: shift request
    description: Sensitive request
    person: Alice
  - type: shift type requirement
    qualifiedPeople: [P1]
  - type: shift affinity
    people1: [Alice]
    people2: [[Bob, P1]]
export:
  formatting:
    - type: row
      description: Sensitive formatting
      people: [ALL, Alice, P1]
  extraRows:
    - type: count
      description: Sensitive count
      countPeople: [Bob, P1]
"""


def _running_job(input_name: str) -> Job:
    return Job(
        id="job_test",
        state=JobState.RUNNING,
        created_at=datetime.now(timezone.utc),
        request=JobRequest(
            input_name=input_name,
            client_id="client_test",
            solver="ortools/cp-sat",
            prettify=True,
            timeout_seconds=60,
        ),
    )


def test_capture_optimize_exception_attaches_anonymized_yaml(monkeypatch):
    attachments = []
    contexts = []

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
        capture_exception=lambda error: None,
    )
    monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)
    job = _running_job("schedule.yaml")

    capture_optimize_exception(job, SCHEDULE_YAML, ValueError("invalid"))

    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment["filename"] == "schedule.yaml"
    assert b"Bob" not in attachment["bytes"]
    assert b"description" not in attachment["bytes"]
    assert b"Sensitive" not in attachment["bytes"]
    assert _load_yaml(attachment["bytes"])["people"]["items"] == [{"id": "P2"}, {"id": "P3"}]
    assert contexts == [
        (
            "schedule_state",
            {
                "attached": True,
                "content_sanitized": True,
                "input_name": "schedule.yaml",
                "job_id": "job_test",
                "size_bytes": len(attachment["bytes"]),
            },
        )
    ]


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
    job = _running_job("invalid.yaml")
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
                "content_sanitized": False,
                "input_name": "invalid.yaml",
                "job_id": "job_test",
                "size_bytes": len(content),
            },
        )
    ]
    assert captured_errors == [error]


def test_init_sentry_configures_sdk_when_enabled(monkeypatch):
    init_calls = []
    tags = []
    fake_sentry_sdk = types.SimpleNamespace(
        init=lambda **kwargs: init_calls.append(kwargs),
        set_tag=lambda name, value: tags.append((name, value)),
    )
    monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)
    monkeypatch.setenv("SENTRY_RELEASE", "custom-release")

    init_sentry("v1.2.3")

    assert init_calls == [
        {
            "dsn": "https://e5bffd2f416c149dfb0d17751071c61d@o4510953883107328.ingest.us.sentry.io/4510953885401088",
            "release": "custom-release",
            "send_default_pii": True,
            "traces_sample_rate": 1.0,
            "profile_session_sample_rate": 1.0,
            "profile_lifecycle": "trace",
            "enable_logs": True,
        }
    ]
    assert tags == [("app", "backend")]


def test_capture_invalid_request_records_route_context_and_fingerprint(monkeypatch):
    scopes = []
    messages = []

    class FakeScope:
        def __enter__(self):
            scopes.append(self)
            self.tags = []
            self.contexts = []
            self.fingerprint = None
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def set_tag(self, name, value):
            self.tags.append((name, value))

        def set_context(self, name, context):
            self.contexts.append((name, context))

    fake_sentry_sdk = types.SimpleNamespace(
        new_scope=FakeScope,
        capture_message=lambda message, level: messages.append((message, level)),
    )
    request = types.SimpleNamespace(
        scope={"route": types.SimpleNamespace(path="/optimize/{job_id}")},
        url=types.SimpleNamespace(path="/optimize/abc"),
        method="GET",
    )
    detail = [{"loc": ("path", "job_id"), "msg": "missing"}]
    monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)

    capture_invalid_request(request, 422, detail)

    assert messages == [("Invalid API request", "warning")]
    assert len(scopes) == 1
    scope = scopes[0]
    assert scope.tags == [
        ("request.invalid", True),
        ("http.status_code", 422),
        ("http.method", "GET"),
        ("http.route", "/optimize/{job_id}"),
    ]
    assert scope.contexts == [
        (
            "invalid_request",
            {
                "path": "/optimize/abc",
                "route": "/optimize/{job_id}",
                "method": "GET",
                "status_code": 422,
                "detail": [{"loc": ["path", "job_id"], "msg": "missing"}],
            },
        )
    ]
    assert scope.fingerprint == ["invalid-request", "422", "/optimize/{job_id}"]


@pytest.mark.parametrize("route", [None, types.SimpleNamespace(path="/optimize/{job_id}")])
def test_capture_invalid_request_ignores_not_found(monkeypatch, route):
    request = types.SimpleNamespace(
        scope={"route": route},
        url=types.SimpleNamespace(path="/optimize/missing"),
        method="GET",
    )
    fake_sentry_sdk = types.SimpleNamespace(
        new_scope=lambda: pytest.fail("404 response reached Sentry"),
    )
    monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)

    capture_invalid_request(request, 404, "Not Found")


def test_capture_invalid_request_ignores_unauthorized():
    """Unauthenticated probes of a protected public deployment are expected traffic."""
    request = types.SimpleNamespace(
        scope={"route": None},
        url=types.SimpleNamespace(path="/optimize/options"),
        method="GET",
    )
    fake_sentry_sdk = types.SimpleNamespace(
        new_scope=lambda: pytest.fail("401 response reached Sentry"),
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
        monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)

        capture_invalid_request(request, 401, "Backend credentials are required.")
