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
from ipaddress import ip_address, ip_network
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from nurse_scheduling.loader import _load_yaml
from nurse_scheduling.sentry import (
    _redact_stream_token,
    capture_invalid_request,
    capture_optimize_exception,
    flush_sentry,
    init_sentry,
)
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
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


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
    monkeypatch.setenv("SENTRY_DSN", "https://backend-key@example.ingest.sentry.io/123")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")

    init_sentry("v1.2.3")

    assert init_calls == [
        {
            "dsn": "https://backend-key@example.ingest.sentry.io/123",
            "environment": "production",
            "release": "custom-release",
            "send_default_pii": True,
            "traces_sample_rate": 1.0,
            "profile_session_sample_rate": 1.0,
            "profile_lifecycle": "trace",
            "enable_logs": True,
            # A stream token is a live credential and Sentry does not scrub a query string.
            "before_send": _redact_stream_token,
            "before_send_transaction": _redact_stream_token,
        }
    ]
    assert tags == [("app", "backend")]


def test_init_sentry_accepts_service_tag(monkeypatch):
    tags = []
    fake_sentry_sdk = types.SimpleNamespace(
        init=lambda **_kwargs: None,
        set_tag=lambda name, value: tags.append((name, value)),
    )
    monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)

    init_sentry("v1.2.3", app="ai-backend")

    assert tags == [("app", "ai-backend")]


def test_stream_token_redaction_decodes_parameter_names():
    query = "x=1&%74oken=live-secret&TOKEN=second-secret&x=2"
    event = {
        "request": {"query_string": query},
        "contexts": {"trace": {"data": {"http.query": query, "url.full": f"https://example.test/events?{query}"}}},
        "spans": [{"data": {"http.query": query, "url.full": f"https://example.test/events?{query}"}}],
    }

    redacted = _redact_stream_token(event, {})
    expected = "x=1&%74oken=[Filtered]&TOKEN=[Filtered]&x=2"
    assert redacted["request"]["query_string"] == expected
    for data in (redacted["contexts"]["trace"]["data"], redacted["spans"][0]["data"]):
        assert data["http.query"] == expected
        assert data["url.full"] == f"https://example.test/events?{expected}"


def test_init_sentry_keeps_shared_development_defaults(monkeypatch):
    init_calls = []
    fake_sentry_sdk = types.SimpleNamespace(
        init=lambda **kwargs: init_calls.append(kwargs),
        set_tag=lambda _name, _value: None,
    )
    monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)

    init_sentry("v1.2.3")

    assert init_calls[0]["dsn"] == (
        "https://e5bffd2f416c149dfb0d17751071c61d@o4510953883107328.ingest.us.sentry.io/4510953885401088"
    )
    assert init_calls[0]["environment"] == "development"


def test_flush_sentry_waits_for_pending_logs(monkeypatch):
    flush_calls = []
    fake_sentry_sdk = types.SimpleNamespace(flush=lambda **kwargs: flush_calls.append(kwargs))
    monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)

    flush_sentry()

    assert flush_calls == [{"timeout": 2.0}]


@pytest.mark.parametrize(
    ("compose_file", "service_names"),
    [
        ("compose.backend.yml", ("api", "ai", "diagnostic", "usage-reporter")),
        ("compose.backend.memory.yml", ("api", "ai", "diagnostic")),
    ],
)
def test_compose_python_services_share_sentry_environment(compose_file, service_names):
    compose_path = REPOSITORY_ROOT / "docker" / compose_file
    compose = YAML(typ="safe").load(compose_path.read_text(encoding="utf-8"))
    expected = {
        "SENTRY_DSN": "${SENTRY_BACKEND_DSN:-}",
        "SENTRY_ENVIRONMENT": "${SENTRY_ENVIRONMENT:-production}",
        "DISABLE_SENTRY": "${DISABLE_SENTRY:-}",
    }

    for service_name in service_names:
        environment = compose["services"][service_name]["environment"]
        assert {name: environment.get(name) for name in expected} == expected


@pytest.mark.parametrize("compose_file", ["compose.backend.yml", "compose.backend.memory.yml"])
def test_compose_trusts_only_its_pinned_forwarding_proxies(compose_file):
    docker_dir = REPOSITORY_ROOT / "docker"
    compose = YAML(typ="safe").load((docker_dir / compose_file).read_text(encoding="utf-8"))

    def default(value, name):
        prefix = "${" + name + ":-"
        assert value.startswith(prefix) and value.endswith("}")
        return value[len(prefix) : -1]

    nginx_ip = default(compose["services"]["nginx"]["networks"]["api"]["ipv4_address"], "NGINX_API_IP")
    tunnel_ip = default(
        compose["services"]["cloudflared"]["networks"]["tunnel"]["ipv4_address"],
        "CLOUDFLARED_TUNNEL_IP",
    )
    trusted = default(compose["services"]["api"]["environment"]["FORWARDED_ALLOW_IPS"], "FORWARDED_ALLOW_IPS")

    assert trusted.split(",") == [nginx_ip, tunnel_ip]
    assert ip_address(nginx_ip) in ip_network(
        default(compose["networks"]["api"]["ipam"]["config"][0]["subnet"], "API_NETWORK_SUBNET")
    )
    assert ip_address(tunnel_ip) in ip_network(
        default(compose["networks"]["tunnel"]["ipam"]["config"][0]["subnet"], "TUNNEL_NETWORK_SUBNET")
    )
    assert "proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;" in (
        docker_dir / "nginx.backend.conf"
    ).read_text(encoding="utf-8")


@pytest.mark.parametrize("env_file", [".env.example", ".env.staging.example"])
def test_compose_env_trust_matches_its_proxy_addresses(env_file):
    lines = (REPOSITORY_ROOT / "docker" / env_file).read_text(encoding="utf-8").splitlines()
    values = dict(line.split("=", 1) for line in lines if line and not line.startswith("#") and "=" in line)

    assert values["FORWARDED_ALLOW_IPS"].split(",") == [
        values["NGINX_API_IP"],
        values["CLOUDFLARED_TUNNEL_IP"],
    ]
    assert ip_address(values["NGINX_API_IP"]) in ip_network(values["API_NETWORK_SUBNET"])
    assert ip_address(values["CLOUDFLARED_TUNNEL_IP"]) in ip_network(values["TUNNEL_NETWORK_SUBNET"])


def _request(path: str, *, route: str | None = None, method: str = "GET") -> types.SimpleNamespace:
    """Build a stub carrying every request attribute the reporting path reads."""
    return types.SimpleNamespace(
        scope={"route": types.SimpleNamespace(path=route) if route is not None else None},
        url=types.SimpleNamespace(path=path),
        method=method,
        headers={},
        query_params={},
        cookies={},
        path_params={},
        state=types.SimpleNamespace(),
    )


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
    request = _request("/optimize/abc", route="/optimize/{job_id}")
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


@pytest.mark.parametrize("route", [None, "/optimize/{job_id}"])
def test_capture_invalid_request_ignores_not_found(monkeypatch, route):
    request = _request("/optimize/missing", route=route)
    fake_sentry_sdk = types.SimpleNamespace(
        new_scope=lambda: pytest.fail("404 response reached Sentry"),
    )
    monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)

    capture_invalid_request(request, 404, "Not Found")


def test_capture_invalid_request_ignores_unauthorized():
    """Unauthenticated probes of a protected public deployment are expected traffic."""
    request = _request("/optimize/options")
    fake_sentry_sdk = types.SimpleNamespace(
        new_scope=lambda: pytest.fail("401 response reached Sentry"),
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr("nurse_scheduling.sentry._should_enable_sentry", lambda: True)
        monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sentry_sdk)

        capture_invalid_request(request, 401, "Backend credentials are required.")
