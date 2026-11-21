"""Compatibility checks for Schedule Spec APIs and saved records."""

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

from nurse_scheduling.server.jobs.runner import OptimizationRunner

from .ai_test_helper import base_schedule_payload, schedule_spec_yaml
from .test_serve import _client, _wait_for_terminal


def test_tagged_v020_frontend_can_optimize_and_download():
    # Keep the release's request fields and strict API version check unchanged.
    with _client(runner=OptimizationRunner()) as client:
        info = client.get("/info").json()
        assert info["service_name"] == "nurse-scheduling-api"
        assert info["api_version"] == "0.2.0"
        response = client.post(
            "/optimize",
            files={"file": ("schedule.yaml", schedule_spec_yaml().encode(), "application/x-yaml")},
            data={"prettify": "true", "timeout": "300"},
        )
        assert response.status_code == 202
        job = response.json()
        assert {"id", "state", "terminal", "queue_position", "result", "error", "controls", "links"} <= job.keys()
        completed = _wait_for_terminal(client, job["id"])
        assert completed["state"] == "completed"
        assert client.get(completed["links"]["schedule"]).status_code == 200


def test_legacy_optimizer_submission():
    with _client() as client:
        old = client.post("/optimize", data={"yaml_content": schedule_spec_yaml()})
        new = client.post("/schedule_spec/optimize", data={"schedule_spec_yaml": schedule_spec_yaml()})
        assert old.status_code == new.status_code == 202
        assert old.json()["state"] == new.json()["state"]


@pytest.mark.parametrize(
    ("path", "file_field"), [("/optimize", "file"), ("/schedule_spec/optimize", "schedule_spec_file")]
)
@pytest.mark.parametrize(
    ("group_id", "selector", "error_message"),
    [
        ("3~4", "3~4", "Date group ID '3~4' cannot look like a date or date range expression"),
        ("FIRST", "０１", "Date '０１' is not in the format"),
    ],
)
def test_optimizer_routes_reject_invalid_date_syntax(path, file_field, group_id, selector, error_message):
    payload = base_schedule_payload()
    payload["dates"]["groups"][0]["id"] = group_id
    payload["preferences"][1]["date"] = [selector]
    content = schedule_spec_yaml(payload).encode()

    with _client(runner=OptimizationRunner()) as client:
        submission = client.post(path, files={file_field: ("schedule.yaml", content, "application/x-yaml")})
        assert submission.status_code == 202
        rejected = _wait_for_terminal(client, submission.json()["id"])

    assert rejected["state"] == "failed"
    assert rejected["error"]["code"] == "invalid_input"
    assert error_message in rejected["error"]["message"]
