"""Tests for LiteLLM deployment limits, cached health, and evaluation admission."""

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
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from nurse_scheduling.ai.litellm_concurrency import discover_capacity, main

NOW = datetime(2026, 10, 24, tzinfo=timezone.utc)


def deployment(name, limit=4, model="qwen"):
    return {"model_name": model, "litellm_params": {"max_parallel_requests": limit}, "model_info": {"id": name}}


def health(status, age=0):
    return {"status": status, "checked_at": (NOW - timedelta(seconds=age)).isoformat()}


def discover(rows, checks=None, *, metadata_status=200, health_status=200):
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path == "/v1/model/info":
            return httpx.Response(metadata_status, json={"data": rows})
        assert request.url.path == "/health/latest"
        return httpx.Response(health_status, json={"latest_health_checks": checks})

    capacity = discover_capacity(
        "https://gateway.example/v1", "app-key", "qwen", transport=httpx.MockTransport(respond), now=NOW
    )
    assert all(request.method == "GET" for request in requests)
    return capacity


@pytest.mark.parametrize(
    ("checks", "expected"),
    [
        ({"primary": health("healthy"), "secondary": health("healthy")}, 8),
        ({"primary": health("healthy"), "secondary": health("unhealthy")}, 4),
        ({"primary": health("unhealthy"), "secondary": health("healthy")}, 4),
        ({"primary": health("unhealthy"), "secondary": health("unhealthy")}, 0),
        ({"primary": health("healthy"), "secondary": health("healthy", 7201)}, 4),
        ({"primary": health("healthy")}, 4),
        ({}, 4),
    ],
)
def test_capacity_counts_only_confirmed_healthy_deployments(checks, expected):
    rows = [deployment("primary"), deployment("secondary"), deployment("other", 100, "other-model")]
    capacity = discover(rows, checks)
    assert capacity.limit == expected
    assert len(capacity.deployments) == 2
    assert capacity.configured_limit == 8
    if expected:
        assert capacity.select_jobs(None, 100) == expected
    else:
        with pytest.raises(ValueError, match="No healthy"):
            capacity.select_jobs(1, 100)


def test_duplicate_deployment_ids_do_not_add_capacity():
    capacity = discover([deployment("primary")] * 2, {"primary": health("healthy")})
    assert capacity.limit == 4 and len(capacity.deployments) == 1


def test_conflicting_ids_use_fallback():
    capacity = discover([deployment("primary", 4), deployment("primary", 8)], {"primary": health("healthy")})
    assert capacity.limit == 4
    assert "conflicting" in capacity.reason


@pytest.mark.parametrize("limit", [None, 0, -1, True, "4"])
def test_invalid_limits_use_fallback(limit):
    capacity = discover([deployment("primary", limit)], {"primary": health("healthy")})
    assert capacity.limit == 4


def test_fallback_respects_a_smaller_deployment_limit_without_ids():
    capacity = discover([{"model_name": "qwen", "litellm_params": {"max_parallel_requests": 2}}], {})
    assert capacity.limit == 2


@pytest.mark.parametrize("health_status", [401, 403, 404, 500])
def test_blocked_health_uses_a_conservative_fallback(health_status):
    capacity = discover([deployment("primary"), deployment("secondary")], health_status=health_status)
    assert capacity.limit == 4
    assert all(item.health == "unknown" for item in capacity.deployments)


def test_unavailable_model_metadata_uses_fallback():
    capacity = discover([], metadata_status=404)
    assert capacity.limit == 4 and not capacity.deployments


@pytest.mark.parametrize("record", [{}, {"status": "healthy", "checked_at": "bad"}, health("healthy", -1)])
def test_missing_invalid_or_future_health_times_are_unknown(record):
    capacity = discover([deployment("primary")], {"primary": record})
    assert capacity.deployments[0].health == "unknown"


@pytest.mark.parametrize(
    ("requested", "attempts", "expected"), [(None, 100, 20), (30, 100, 20), (3, 100, 3), (8, 2, 2)]
)
def test_jobs_obey_sandbox_requested_and_work_limits(requested, attempts, expected):
    capacity = discover([deployment("primary", 40)], {"primary": health("healthy")})
    assert capacity.select_jobs(requested, attempts) == expected


def test_explicit_jobs_cannot_exceed_provider_limit():
    assert discover([deployment("primary")]).select_jobs(20, 100) == 4


@pytest.mark.parametrize("base_url", ["https://gateway.example/v1/", "http://127.0.0.1:14000/proxy/v1"])
def test_metadata_and_health_reuse_provider_origin_and_key(base_url):
    requests = []
    api_base = base_url.rstrip("/")
    health_url = api_base.removesuffix("/v1") + "/health/latest"

    def respond(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer provider-key"
        if str(request.url) == api_base + "/model/info":
            return httpx.Response(200, json={"data": [deployment("primary"), deployment("secondary")]})
        assert str(request.url) == health_url
        return httpx.Response(
            200, json={"latest_health_checks": {name: health("healthy") for name in ("primary", "secondary")}}
        )

    capacity = discover_capacity(base_url, "provider-key", "qwen", transport=httpx.MockTransport(respond), now=NOW)
    assert capacity.limit == 8
    assert len(requests) == 2


def test_admin_command_outputs_capacity_without_credentials(monkeypatch, capsys):
    from nurse_scheduling.ai import litellm_concurrency

    monkeypatch.setenv("AI_PROVIDER_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("AI_PROVIDER_API_KEY", "secret-app-key")
    monkeypatch.setenv("AI_PROVIDER_MODEL", "qwen")
    monkeypatch.setattr(litellm_concurrency, "discover_capacity", lambda *args: discover([deployment("primary")]))
    assert main([]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["eval_ceiling"] == 4
    assert "secret-app-key" not in output


@pytest.mark.skipif(shutil.which("bash") is None or os.name == "nt", reason="Bash wrapper needs POSIX")
def test_shell_wrapper_help_needs_no_credentials_and_explicit_missing_file_is_an_error(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts" / "check_litellm_concurrency.sh"
    env = {**os.environ, "AI_ENV_FILE": str(tmp_path / "missing.env")}
    result = subprocess.run(["bash", str(script), "--help"], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0 and "--model" in result.stdout
    result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 2 and "Environment file not found" in result.stderr
