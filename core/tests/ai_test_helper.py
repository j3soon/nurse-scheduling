"""Shared schedule fixtures for the experimental AI tests."""

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

from io import BytesIO
from typing import Any

from ruamel.yaml import YAML

from nurse_scheduling.loader import _load_yaml

SCHEDULE_BYTE_LIMIT = 1_000_000


def base_schedule_payload() -> dict:
    """Return a small schedule in the shape the web frontend produces."""
    return {
        "appVersion": "v0.0.0-test",
        "apiVersion": "alpha",
        "description": "",
        "dates": {
            "range": {"startDate": "2026-01-01", "endDate": "2026-01-02"},
            "items": [],
            "groups": [{"id": "FIRST", "description": "", "members": ["2026-01-01"]}],
        },
        "people": {
            "items": [
                {"id": "P1", "description": "", "history": []},
                {"id": "P2", "description": "", "history": []},
            ],
            "groups": [{"id": "PEOPLE", "description": "", "members": ["P1", "P2"]}],
        },
        "shiftTypes": {
            "items": [{"id": "D", "description": ""}, {"id": "N", "description": ""}],
            "groups": [{"id": "WORK", "description": "", "members": ["D", "N"]}],
        },
        "preferences": [
            {"type": "at most one shift per day"},
            {
                "type": "shift request",
                "person": ["P1"],
                "date": ["FIRST"],
                "shiftType": ["D"],
                "weight": 1,
            },
        ],
        "export": {"formatting": [], "extraColumns": [], "extraRows": []},
    }


def schedule_yaml(payload: dict | None = None) -> str:
    """Render a schedule payload as the block YAML the browser sends."""
    yaml = YAML(typ="safe")
    yaml.default_flow_style = False
    yaml.representer.sort_base_mapping_type_on_output = False
    output = BytesIO()
    yaml.dump(payload if payload is not None else base_schedule_payload(), output)
    return output.getvalue().decode("utf-8")


def parse_schedule(text: str) -> Any:
    """Parse a schedule the way the service does."""
    return _load_yaml(text.encode("utf-8"))
