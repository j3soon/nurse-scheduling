"""Bounded-time smoke test for the real-world OR-Tools scheduling scenario."""

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

from io import BytesIO
from pathlib import Path
import sys

# Add the project root to the Python path so imports work when running this file explicitly.
sys.path.insert(0, str(Path(__file__).parents[2]))

import nurse_scheduling
from ruamel.yaml import YAML


REAL_TESTCASE = Path(__file__).parents[1] / "testcases" / "real" / "large-ward-with-87-people-2025-11.yaml"
SMOKE_TEST_TIMEOUT_SECONDS = 180
CRITICAL_REQUEST_NOTE_PREFIX = "Critical unsatisfied request:"
CRITICAL_REQUEST_FORMATTING_RULES = [
    {
        "type": "cell",
        "people": ["ALL"],
        "dates": ["ALL"],
        "shiftTypes": ["ALL", "OFF"],
        "when": {
            "preference": {
                "types": ["shift request"],
                "satisfied": False,
                "weightRange": [float("-inf"), -11_000_000_000],
            }
        },
        "note": {"text": f"{CRITICAL_REQUEST_NOTE_PREFIX} {{shiftType}}, weight={{weight}}"},
    },
    {
        "type": "cell",
        "people": ["ALL"],
        "dates": ["ALL"],
        "shiftTypes": ["ALL", "OFF"],
        "when": {
            "preference": {
                "types": ["shift request"],
                "satisfied": False,
                "weightRange": [11_000_000_000, float("inf")],
            }
        },
        "note": {"text": f"{CRITICAL_REQUEST_NOTE_PREFIX} {{shiftType}}, weight={{weight}}"},
    },
]


def _add_critical_request_formatting_rules(file_content: bytes) -> bytes:
    yaml = YAML(typ="safe")
    scenario = yaml.load(file_content)
    scenario.setdefault("export", {}).setdefault("formatting", []).extend(CRITICAL_REQUEST_FORMATTING_RULES)
    output = BytesIO()
    yaml.dump(scenario, output)
    return output.getvalue()


def test_real_schedule_ortools_finds_feasible_solution_within_fixed_budget():
    file_content = _add_critical_request_formatting_rules(REAL_TESTCASE.read_bytes())

    df, solution, score, status, cell_export_info = nurse_scheduling.schedule(
        file_content,
        prettify=True,
        solver="ortools/cp-sat",
        timeout=SMOKE_TEST_TIMEOUT_SECONDS,
    )

    critical_notes = [
        note
        for notes in cell_export_info["comments"].values()
        for note in notes
        if note.startswith(CRITICAL_REQUEST_NOTE_PREFIX)
    ]

    assert status in {"FEASIBLE", "OPTIMAL"}
    assert df is not None
    assert solution is not None
    assert len(solution) == 30 * 11 * 87
    assert isinstance(score, int)
    assert critical_notes == []
