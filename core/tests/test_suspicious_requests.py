"""Tests for separating suspicious API requests from internet background noise."""

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
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from nurse_scheduling.server.app import create_app
from nurse_scheduling.server.auth import create_stream_token, describe_stream_token
from nurse_scheduling.server.config import ServerSettings
from nurse_scheduling.server.stores.memory import MemoryJobStore

AUTH_TOKEN = "test-token-of-sufficient-length"
ISSUED_JOB_ID = "job_0123456789abcdef0123456789abcdef"
FORGED_SIGNATURE = "f" * 64


@pytest.fixture
def captured(monkeypatch):
    """Collect Sentry messages, levels, and contexts instead of sending them."""
    events = []

    class FakeScope:
        def __init__(self):
            self.contexts = {}
            self.tags = {}
            self.fingerprint = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def set_tag(self, name, value):
            self.tags[name] = value

        def set_context(self, name, context):
            self.contexts[name] = context

    scopes = []

    def new_scope():
        scope = FakeScope()
        scopes.append(scope)
        return scope

    def capture_message(message, level="info"):
        events.append({"message": message, "level": level, "scope": scopes[-1]})

    monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "sentry_sdk",
        types.SimpleNamespace(
            # `create_app` initializes Sentry, which this fake accepts and discards.
            init=lambda **kwargs: None,
            set_tag=lambda name, value: None,
            new_scope=new_scope,
            capture_message=capture_message,
        ),
    )
    return events


def _client(*, auth_token=None) -> TestClient:
    settings = ServerSettings(
        claim_poll_seconds=0.005,
        maintenance_interval_seconds=60,
        sse_keepalive_seconds=0.01,
        auth_token=auth_token,
    )
    app = create_app(settings=settings, store=MemoryJobStore(), start_background=False)
    return TestClient(app)


def _signals(events) -> list[tuple[str, str]]:
    """Return the reported signal name and level of every suspicious-request event."""
    return [
        (event["scope"].contexts["suspicious_request"]["signal"], event["level"])
        for event in events
        if "suspicious_request" in event["scope"].contexts
    ]


# Signals worth reporting: each one requires knowledge of this API's contract.


def test_missing_job_through_a_real_route_is_reported(captured):
    client = _client()

    response = client.get(f"/optimize/{ISSUED_JOB_ID}")

    assert response.status_code == 404
    assert _signals(captured) == [("job_id_probe", "warning")]
    assert captured[0]["scope"].contexts["suspicious_request"]["job_id"] == "issued_shape"
    assert captured[0]["scope"].fingerprint == ["suspicious-request", "job_id_probe"]


def test_missing_job_with_an_unissued_identifier_shape_is_reported(captured):
    client = _client()

    response = client.get("/optimize/not-a-job-id")

    assert response.status_code == 404
    assert _signals(captured) == [("job_id_probe", "warning")]
    assert captured[0]["scope"].contexts["suspicious_request"]["job_id"] == "unissued_shape"


def test_forged_stream_token_is_reported_as_an_error(captured):
    client = _client(auth_token=AUTH_TOKEN)
    expires_at = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())

    response = client.get(f"/optimize/{ISSUED_JOB_ID}/events?token={expires_at}.{FORGED_SIGNATURE}")

    assert response.status_code == 401
    assert _signals(captured) == [("forged_stream_token", "error")]
    # Sentry scrubs a field whose name contains "token", so this one must not.
    assert captured[0]["scope"].contexts["suspicious_request"]["stream_state"] == "live"


def test_rejected_bearer_token_is_reported(captured):
    client = _client(auth_token=AUTH_TOKEN)

    response = client.get("/optimize/options", headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code == 401
    assert _signals(captured) == [("rejected_bearer_token", "warning")]
    assert captured[0]["scope"].contexts["suspicious_request"]["bearer_presented"] is True


def test_timeout_beyond_the_advertised_maximum_is_reported(captured):
    client = _client()

    response = client.post(
        "/optimize",
        data={"yaml_content": "apiVersion: alpha\n", "timeout": 10**9},
    )

    assert response.status_code == 400
    assert _signals(captured) == [("timeout_out_of_range", "warning")]


# Background noise: none of these reach Sentry.


def test_unmatched_route_is_not_reported(captured):
    client = _client()

    response = client.get("/wp-admin/setup-config.php")

    assert response.status_code == 404
    assert captured == []


def test_missing_credentials_are_not_reported(captured):
    client = _client(auth_token=AUTH_TOKEN)

    response = client.get("/optimize/options")

    assert response.status_code == 401
    assert captured == []


def test_expired_stream_token_is_not_reported(captured):
    client = _client(auth_token=AUTH_TOKEN)
    expired = create_stream_token(
        AUTH_TOKEN,
        ISSUED_JOB_ID,
        ttl_seconds=-3600,
        now=datetime.now(timezone.utc),
    )

    response = client.get(f"/optimize/{ISSUED_JOB_ID}/events?token={expired}")

    assert response.status_code == 401
    assert captured == []


def test_accepted_request_within_the_advertised_range_is_not_reported(captured):
    client = _client()

    response = client.post(
        "/optimize",
        data={"yaml_content": "apiVersion: alpha\n", "timeout": 60},
    )

    assert response.status_code == 202
    assert captured == []


# Token description underpins the stream-token signal.


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        (None, "absent"),
        ("", "absent"),
        ("not-a-token", "malformed"),
        ("1700000000.short", "malformed"),
        (f"1700000000.{FORGED_SIGNATURE}", "expired"),
    ],
)
def test_describe_stream_token_classifies_shape_and_freshness(token, expected):
    assert describe_stream_token(token) == expected


def test_describe_stream_token_reports_an_unexpired_token_as_live():
    live = create_stream_token(AUTH_TOKEN, ISSUED_JOB_ID, ttl_seconds=3600)

    assert describe_stream_token(live) == "live"
