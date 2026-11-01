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

from . import test_ai_basic as basic
from .test_serve import _client


def test_tagged_v020_frontend_can_optimize_and_download():
    from .test_serve import _wait_for_terminal

    # Keep the release's request fields and strict API version check unchanged.
    with _client() as client:
        info = client.get("/info").json()
        assert info["service_name"] == "nurse-scheduling-api"
        assert info["api_version"] == "0.2.0"
        response = client.post(
            "/optimize",
            files={"file": ("schedule.yaml", basic.schedule_yaml().encode(), "application/x-yaml")},
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
        old = client.post("/optimize", data={"yaml_content": basic.schedule_yaml()})
        new = client.post("/schedule_spec/optimize", data={"schedule_spec_yaml": basic.schedule_yaml()})
        assert old.status_code == new.status_code == 202
        assert old.json()["state"] == new.json()["state"]
