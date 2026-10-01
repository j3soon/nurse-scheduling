"""Semantic and standalone checks for the sandbox optimizer result reader."""

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
import subprocess
import sys

import pytest
from openpyxl import load_workbook

from nurse_scheduling.ai.attachment_tools.inspect_optimizer_result import _assigned, inspect_result
from nurse_scheduling.ai.result_context import build_result_context
from nurse_scheduling.ai.sandbox_agent import INSPECTION_HELPERS, REFERENCE_ATTACHMENT_TOOLS, inspection_helper_catalog

from .ai_eval.optimizer_fixtures import FIXTURE, completion_result


@pytest.fixture
def audit(tmp_path):
    context = build_result_context(FIXTURE.read_text())
    payload, _ = completion_result("request-audit", FIXTURE.read_text())
    path = tmp_path / "result.xlsx"
    path.write_bytes(payload)
    return path, context


def test_reader_counts_actual_assignments_and_hard_avoids(audit):
    path, context = audit
    result = inspect_result(path, context, context["source_sha256"])
    assert result["summary"] == [
        {"weight": 11_000_000_000, "total": 4, "satisfied": 3, "unmet": 1},
        {"weight": 11_000_000, "total": 1, "satisfied": 0, "unmet": 1},
        {"weight": "-.inf", "total": 3, "satisfied": 3, "unmet": 0},
    ]
    assert [(row["person"], row["date"], row["assigned"]) for row in result["unmet"]] == [
        ("Mira", "2026-05-02", "N"),
        ("Alex", "2026-05-03", "D"),
    ]
    assert result["score"] == 33_000_000_000
    assert result["score_direction"] == "maximize"
    assert result["status"] == "FEASIBLE"


def test_reader_accepts_reordered_people_and_offset_headers(audit):
    path, context = audit
    workbook = load_workbook(path)
    ws = workbook.active
    first, third = [c.value for c in ws[3]], [c.value for c in ws[5]]
    for col, value in enumerate(third, 1):
        ws.cell(3, col).value = value
    for col, value in enumerate(first, 1):
        ws.cell(5, col).value = value
    ws.insert_rows(1)
    ws.cell(1, 1).value = "Roster title"
    workbook.save(path)
    result = inspect_result(path, context, context["source_sha256"])
    assert result["summary"][0]["unmet"] == 1


def test_reader_does_not_count_lower_weight_markers_as_strong_misses(audit):
    path, context = audit
    payload, _ = completion_result("request-audit-all-strong", FIXTURE.read_text())
    path.write_bytes(payload)
    result = inspect_result(path, context, context["source_sha256"])
    assert [(row["total"], row["unmet"]) for row in result["summary"]] == [(4, 0), (1, 1), (3, 0)]


def test_compiled_context_uses_canonical_groups_and_reserved_selectors():
    source = (
        FIXTURE.read_text()
        .replace("groups: []\nshiftTypes:", "groups: [{id: Team, members: [Kai]}]\nshiftTypes:")
        .replace("person: [Kai]", "person: [Team]")
    )
    context = build_result_context(source)
    last = context["requests"][-1]
    assert last["people"] == ["Kai"]
    assert last["dates"] == ["2026-05-01", "2026-05-02", "2026-05-03"]
    assert last["shift_types"] == ["K"]


def test_reader_rejects_mismatched_source_and_unknown_decorations(audit):
    path, context = audit
    with pytest.raises(ValueError, match="source"):
        inspect_result(path, context, "0" * 64)
    workbook = load_workbook(path)
    workbook.active.cell(3, 5).value = "* OFF?"
    workbook.save(path)
    with pytest.raises(ValueError, match="unknown or ambiguous"):
        inspect_result(path, context, context["source_sha256"])


@pytest.mark.parametrize(
    "value,expected", [(None, "OFF"), (" [OFF]", "OFF"), ("K [K]", "K"), ("D [OFF] [X]", "D"), ("D+", "D+"), (0, "0")]
)
def test_assignment_reader_handles_annotations_and_exact_shift_ids(value, expected):
    assert _assigned(value, ["D", "D+", "K", "0"]) == expected


def test_assignment_reader_rejects_ambiguous_literal_shift_ids():
    with pytest.raises(ValueError, match="ambiguous"):
        _assigned("D [OFF]", ["D", "D [OFF]"])


def test_reader_bounds_detail_without_changing_counts(audit):
    path, context = audit
    result = inspect_result(path, context, context["source_sha256"], max_unmet=1)
    assert len(result["unmet"]) == 1 and result["unmet_truncated"]
    filtered = inspect_result(path, context, context["source_sha256"], weights=["11000000000"])
    assert len(filtered["summary"]) == 1 and filtered["summary"][0]["total"] == 4


def test_standalone_hydrated_reader_runs_without_project_imports(audit, tmp_path):
    path, context = audit
    for source in REFERENCE_ATTACHMENT_TOOLS.values():
        (tmp_path / source.name).write_bytes(source.read_bytes())
    context_path = tmp_path / "context.json"
    context_path.write_text(json.dumps(context))
    result = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "inspect_optimizer_result.py"),
            str(path),
            "--context",
            str(context_path),
            "--source-sha256",
            context["source_sha256"],
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["summary"][0]["unmet"] == 1


def test_catalog_only_advertises_real_hydrated_scripts():
    catalog = inspection_helper_catalog()
    assert len(INSPECTION_HELPERS) == len(REFERENCE_ATTACHMENT_TOOLS)
    for path, source in REFERENCE_ATTACHMENT_TOOLS.items():
        assert source.is_file() and path in catalog
