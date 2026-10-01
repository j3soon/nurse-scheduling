"""Deterministic optimizer completion fixtures using the production exporter."""

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

import hashlib
import json
from contextlib import redirect_stdout
from functools import lru_cache
from io import BytesIO, StringIO
from pathlib import Path

from nurse_scheduling import exporter, schedule
from nurse_scheduling.loader import _load_yaml

FIXTURE = Path(__file__).with_name("fixtures") / "request-audit.yaml"
ASSIGNMENTS = {"Alex": ["OFF", "K", "D"], "Mira": ["D", "N", "OFF"], "Kai": ["N", "D", "N"]}
RESULT_ASSIGNMENTS = {
    "request-audit": ASSIGNMENTS,
    "request-audit-all-strong": {**ASSIGNMENTS, "Mira": ["D", "OFF", "OFF"]},
    "request-audit-groups": {
        "Asha": ["OFF", "D", "N", "OFF"],
        "Ben": ["D", "OFF", "D", "N"],
        "Cleo": ["OFF", "OFF", "OFF", "D"],
        "Dara": ["D", "N", "D", "OFF"],
        "Eli": ["OFF", "D", "OFF", "N"],
        "Fran": ["N", "D", "N", "D"],
    },
}
RESULT_SOURCES = {
    name: FIXTURE.with_name("request-audit-groups.yaml") if name == "request-audit-groups" else FIXTURE
    for name in RESULT_ASSIGNMENTS
}


def fixture_digest(name: str) -> str:
    """Bind completion cases to their schedule and fixed assignment."""
    if name not in RESULT_ASSIGNMENTS:
        raise ValueError(f"Unknown optimizer result fixture: {name}")
    return hashlib.sha256(
        RESULT_SOURCES[name].read_bytes() + json.dumps(RESULT_ASSIGNMENTS[name], sort_keys=True).encode()
    ).hexdigest()


@lru_cache(maxsize=4)
def completion_result(name: str, source: str) -> tuple[bytes, dict]:
    """Replay a checked incumbent, export it, and simulate timeout completion metadata."""
    fixture_digest(name)
    data = _load_yaml(source.encode())
    if data != _load_yaml(RESULT_SOURCES[name].read_bytes()):
        raise ValueError("The optimizer source differs from the controlled result fixture")
    people = data["people"]["items"]
    shifts = data["shiftTypes"]["items"]
    forced = {
        (day, shift, person): int(RESULT_ASSIGNMENTS[name][p["id"]][day] == s["id"])
        for day in range(len(next(iter(RESULT_ASSIGNMENTS[name].values()))))
        for shift, s in enumerate(shifts)
        for person, p in enumerate(people)
    }
    with redirect_stdout(StringIO()):
        result = schedule(source.encode(), solver="ortools/cp-sat", forced_solution=forced, timeout=5, prettify=True)
    if result.solver_status != "OPTIMAL" or result.solution != forced:
        raise ValueError("The controlled assignment is not a verified feasible solution")
    dataframe = result.dataframe
    dataframe.data.loc[dataframe.data.iloc[:, 0] == "Status"] = dataframe.data.loc[
        dataframe.data.iloc[:, 0] == "Status"
    ].replace("OPTIMAL", "FEASIBLE")
    output = BytesIO()
    exporter.export_to_excel(dataframe, output, result.cell_export_info)
    return output.getvalue(), {
        "job_id": "eval-job",
        "state": "completed",
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "result": {
            "outcome": "feasible",
            "solver_status": "FEASIBLE",
            "termination_reason": "solver_timeout",
            "score": result.score,
        },
        "error": None,
        "download_available": True,
        "artifact_error": None,
    }
