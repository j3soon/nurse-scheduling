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

from nurse_scheduling.sentry import CLIENT_ADDRESS_TAG
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
    tags = {}

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
            # Every request records the address it connected from before routing.
            set_tag=lambda name, value: tags.__setitem__(name, value),
            new_scope=new_scope,
            capture_message=capture_message,
        ),
    )
    return types.SimpleNamespace(events=events, tags=tags)


def _app(*, auth_token=None, **overrides):
    settings = ServerSettings(
        claim_poll_seconds=0.005,
        maintenance_interval_seconds=60,
        sse_keepalive_seconds=0.01,
        auth_token=auth_token,
        **overrides,
    )
    return create_app(settings=settings, store=MemoryJobStore(), start_background=False)


def _client(*, auth_token=None, connected_from=("203.0.113.7", 40000), **overrides) -> TestClient:
    return TestClient(_app(auth_token=auth_token, **overrides), client=connected_from)


def _signals(captured) -> list[tuple[str, str]]:
    """Return the reported signal name and level of every suspicious-request event."""
    return [
        (event["scope"].contexts["suspicious_request"]["signal"], event["level"])
        for event in captured.events
        if "suspicious_request" in event["scope"].contexts
    ]


# Signals worth reporting: each one requires knowledge of this API's contract.


def test_missing_job_through_a_real_route_is_reported(captured):
    client = _client()

    response = client.get(f"/optimize/{ISSUED_JOB_ID}")

    assert response.status_code == 404
    assert _signals(captured) == [("job_id_probe", "warning")]
    assert captured.events[0]["scope"].contexts["suspicious_request"]["job_id"] == "issued_shape"
    assert captured.events[0]["scope"].fingerprint == ["suspicious-request", "job_id_probe"]


@pytest.mark.parametrize("path", ["/optimize/not-a-job-id", "/optimize/.env", "/optimize/wp-login.php"])
def test_a_wordlist_path_on_the_job_route_is_not_reported(captured, path):
    """The job route matches any single segment, so a scanner reaches it without knowing it."""
    client = _client()

    response = client.get(path)

    assert response.status_code == 404
    assert captured.events == []


def test_forged_stream_token_is_reported_as_an_error(captured):
    client = _client(auth_token=AUTH_TOKEN)
    expires_at = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())

    response = client.get(f"/optimize/{ISSUED_JOB_ID}/events?token={expires_at}.{FORGED_SIGNATURE}")

    assert response.status_code == 401
    assert _signals(captured) == [("forged_stream_token", "error")]
    # Sentry scrubs a field whose name contains "token", so this one must not.
    assert captured.events[0]["scope"].contexts["suspicious_request"]["stream_state"] == "live"


@pytest.mark.parametrize(
    ("encoding", "level"),
    [
        ("{exp}.{sig}", "error"),
        ("+{exp}.{sig}", "warning"),
        ("{exp}.{SIG}", "warning"),
        (" {exp}.{sig}", "warning"),
    ],
)
def test_a_forged_token_cannot_hide_behind_another_spelling(captured, encoding, level):
    """`int` accepts spellings this server never mints, so shape alone must not gate reporting."""
    client = _client(auth_token=AUTH_TOKEN)
    expires_at = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    token = encoding.format(exp=expires_at, sig=FORGED_SIGNATURE, SIG=FORGED_SIGNATURE.upper())

    response = client.get(f"/optimize/{ISSUED_JOB_ID}/events", params={"token": token})

    assert response.status_code == 401
    assert _signals(captured) == [("forged_stream_token", level)]


def test_rejected_bearer_token_is_reported(captured):
    client = _client(auth_token=AUTH_TOKEN)

    response = client.get("/optimize/options", headers={"Authorization": "Bearer wrong-token"})

    assert response.status_code == 401
    assert _signals(captured) == [("rejected_bearer_token", "warning")]
    assert captured.events[0]["scope"].contexts["suspicious_request"]["bearer_presented"] is True


def test_yaml_that_expands_past_the_limit_is_refused_and_reported(captured):
    """A few hundred bytes of aliases would otherwise spend a worker on their expansion."""
    client = _client()
    bomb = b"apiVersion: alpha\ndescription: &a [" + b",".join([b"x"] * 9) + b"]\n"
    for index in range(1, 8):
        previous, current = chr(ord("a") + index - 1), chr(ord("a") + index)
        bomb += f"k{current}: &{current} [{','.join(f'*{previous}' for _ in range(9))}]\n".encode()

    response = client.post("/optimize", data={"yaml_content": bomb.decode()})

    assert response.status_code == 400
    assert _signals(captured) == [("yaml_expansion_bomb", "error")]


def test_ordinary_yaml_is_not_refused_as_an_expansion(captured):
    client = _client()

    response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n"})

    assert response.status_code == 202
    assert captured.events == []


def test_deeply_nested_yaml_is_refused_and_reported(captured):
    """Nesting is expensive to read, so it is refused on the same signal as an expansion."""
    client = _client()
    depth = 10_000
    payload = "apiVersion: alpha\nx: " + "[" * depth + "]" * depth + "\n"

    response = client.post("/optimize", data={"yaml_content": payload})

    assert response.status_code == 400
    assert _signals(captured) == [("yaml_expansion_bomb", "error")]


def test_accepted_yaml_using_aliases_is_reported(captured):
    """Nothing this project produces uses an alias, so one marks a hand-built client."""
    client = _client()

    response = client.post(
        "/optimize",
        data={"yaml_content": "apiVersion: alpha\npeople: &p [Alice, Bob]\na: *p\n"},
    )

    assert response.status_code == 202
    assert _signals(captured) == [("yaml_aliases_used", "warning")]


def test_accepted_yaml_that_does_not_parse_is_reported(captured):
    """A real client serializes its data, so it does not submit something unparseable."""
    client = _client()

    response = client.post("/optimize", data={"yaml_content": "apiVersion: alpha\n  bad: ["})

    assert response.status_code == 202
    assert _signals(captured) == [("yaml_unparseable", "warning")]


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
    assert captured.events == []


def test_missing_credentials_are_not_reported(captured):
    client = _client(auth_token=AUTH_TOKEN)

    response = client.get("/optimize/options")

    assert response.status_code == 401
    assert captured.events == []


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
    assert captured.events == []


def test_accepted_request_within_the_advertised_range_is_not_reported(captured):
    client = _client()

    response = client.post(
        "/optimize",
        data={"yaml_content": "apiVersion: alpha\n", "timeout": 60},
    )

    assert response.status_code == 202
    assert captured.events == []


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


# Address attribution: the connection address is recorded beside Sentry's own.


def test_a_peer_that_is_not_an_address_is_left_to_sentry(captured):
    """Recording a name Sentry cannot parse would tag every such event as invalid."""
    client = _client(connected_from=("not-an-address", 50000))

    response = client.get(f"/optimize/{ISSUED_JOB_ID}")

    assert response.status_code == 404
    assert _signals(captured) == [("job_id_probe", "warning")]
    assert CLIENT_ADDRESS_TAG not in captured.tags


def test_a_connection_address_is_recorded_on_every_request(captured):
    client = _client(connected_from=("203.0.113.7", 40000))

    client.get("/ready", headers={"X-Forwarded-For": "192.0.2.99"})

    # Sentry's own attribution keeps the claimed address; this records the real one.
    assert captured.tags[CLIENT_ADDRESS_TAG] == "203.0.113.7"


# Repetition: one request is a mistake, the same one repeated is deliberate.


def test_probing_distinct_identifiers_escalates_to_an_error(captured):
    """Working through identifiers is enumeration, whatever each individual miss looks like."""
    client = _client(suspicion_escalate_count=3)

    for index in range(3):
        client.get(f"/optimize/job_{index:032x}")

    assert _signals(captured) == [
        ("job_id_probe", "warning"),
        ("job_id_probe", "warning"),
        ("job_id_probe", "error"),
    ]
    contexts = [event["scope"].contexts["suspicious_request"] for event in captured.events]
    assert [context["occurrences"] for context in contexts] == [1, 2, 3]
    assert [context["distinct_job_ids"] for context in contexts] == [1, 2, 3]


def test_retrying_one_identifier_never_escalates(captured):
    """A tab polling a deleted job repeats without ever working through anything."""
    client = _client(suspicion_escalate_count=3)

    for _ in range(3):
        client.get(f"/optimize/{ISSUED_JOB_ID}")

    assert {level for _, level in _signals(captured)} == {"warning"}
    contexts = [event["scope"].contexts["suspicious_request"] for event in captured.events]
    assert [context["distinct_job_ids"] for context in contexts] == [1, 1, 1]


def test_probes_from_different_addresses_do_not_escalate_each_other(captured):
    # One application, so one shared tracker, which is what makes the addresses the variable.
    app = _app(suspicion_escalate_count=3)

    for last_octet in range(3):
        TestClient(app, client=(f"203.0.113.{last_octet}", 40000)).get(f"/optimize/{ISSUED_JOB_ID}")

    assert {level for _, level in _signals(captured)} == {"warning"}
    contexts = [event["scope"].contexts["suspicious_request"] for event in captured.events]
    assert [context["occurrences"] for context in contexts] == [1, 1, 1]


def test_counting_is_skipped_when_disabled(captured):
    client = _client(suspicion_enabled=False)

    client.get(f"/optimize/{ISSUED_JOB_ID}")

    assert _signals(captured) == [("job_id_probe", "warning")]
    assert captured.events[0]["scope"].contexts["suspicious_request"]["occurrences"] is None


# Invariants: reporting must be invisible to the caller and unable to fail a request.


def test_a_reported_request_answers_exactly_like_an_unreported_one(captured):
    """A caller must not be able to tell which requests were reported.

    Both requests miss a job and answer identically. Only one is reported, because only one
    used an identifier this server could have issued.
    """
    client = _client()

    reported = client.get(f"/optimize/{ISSUED_JOB_ID}")
    unreported = client.get("/optimize/wp-login.php")

    assert _signals(captured) == [("job_id_probe", "warning")]
    assert (reported.status_code, reported.content) == (unreported.status_code, unreported.content)
    ignored = {"date", "server"}
    assert {k: v for k, v in reported.headers.items() if k.lower() not in ignored} == {
        k: v for k, v in unreported.headers.items() if k.lower() not in ignored
    }


def test_a_failing_tracker_leaves_the_response_alone(captured):
    """Counting is advisory, so any failure in it must not become a server error."""

    class FailingTracker:
        escalate_count = 5

        def record(self, signal, address):
            raise RuntimeError("redis pool exhausted")

    app = _app()
    app.state.suspicion_tracker = FailingTracker()

    response = TestClient(app, client=("203.0.113.7", 40000)).get(f"/optimize/{ISSUED_JOB_ID}")

    assert response.status_code == 404
    assert response.json() == {"error": {"code": "job_not_found", "message": "Job was not found"}}


def test_a_failing_address_tag_leaves_the_response_alone(monkeypatch, captured):
    """The tag runs on every request, so its failure must not fail an ordinary one."""

    def explode(request):
        raise RuntimeError("scope unavailable")

    # Fails inside the reporting helper, which is where a real failure would arise.
    monkeypatch.setattr("nurse_scheduling.sentry._connection_address", explode)

    response = _client().get("/ready")

    assert response.status_code == 200


def test_one_address_cannot_spend_the_event_quota(captured):
    """Repeats past the escalation point keep counting but stop being reported."""
    client = _client(suspicion_escalate_count=3)

    for index in range(8):
        client.get(f"/optimize/job_{index:032x}")

    assert _signals(captured) == [
        ("job_id_probe", "warning"),
        ("job_id_probe", "warning"),
        ("job_id_probe", "error"),
    ]
