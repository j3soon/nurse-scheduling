"""Shared helpers for opt-in real-world scheduling smoke tests."""

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

import nurse_scheduling
from ruamel.yaml import YAML
from nurse_scheduling.solver_interface import SolverProgress


REAL_TESTCASE = Path(__file__).parents[1] / "testcases" / "real" / "large-ward-with-87-people-2025-11.yaml"
SMOKE_TEST_TIMEOUT_SECONDS = 300
EXPECTED_SOLUTION_SIZE = 30 * 11 * 87
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


def _critical_request_notes(cell_export_info) -> list[str]:
    if not isinstance(cell_export_info, dict):
        return []
    comments = cell_export_info.get("comments")
    if not isinstance(comments, dict):
        return []
    return [note for notes in comments.values() for note in notes if note.startswith(CRITICAL_REQUEST_NOTE_PREFIX)]


def run_real_schedule_smoke_test(solver: str):
    file_content = _add_critical_request_formatting_rules(REAL_TESTCASE.read_bytes())
    stop_after_zero_critical_notes = False

    def track_critical_notes(payload):
        nonlocal stop_after_zero_critical_notes
        comments = (
            payload.cell_export_info.get("comments")
            if isinstance(payload, SolverProgress) and isinstance(payload.cell_export_info, dict)
            else None
        )
        if isinstance(comments, dict):
            stop_after_zero_critical_notes = not _critical_request_notes(payload.cell_export_info)

    supports_progress_stop = solver == "ortools/cp-sat"

    df, solution, score, status, cell_export_info = nurse_scheduling.schedule(
        file_content,
        prettify=True,
        solver=solver,
        timeout=None if supports_progress_stop else SMOKE_TEST_TIMEOUT_SECONDS,
        progress_callback=track_critical_notes if supports_progress_stop else None,
        should_stop=(lambda: stop_after_zero_critical_notes) if supports_progress_stop else None,
    )

    critical_notes = _critical_request_notes(cell_export_info)

    assert status in {"FEASIBLE", "OPTIMAL"}
    assert df is not None
    assert solution is not None
    assert len(solution) == EXPECTED_SOLUTION_SIZE
    assert isinstance(score, int)
    assert critical_notes == [], f"Found {len(critical_notes)} critical notes: {critical_notes[:10]}"
