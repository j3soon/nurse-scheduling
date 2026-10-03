"""Canonical selectors and freshness checks for current request inspection."""

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

from nurse_scheduling.ai.attachment_tools.inspect_shift_requests import inspect_requests
from nurse_scheduling.ai.result_context import build_result_context
from nurse_scheduling.ai.sandbox_agent import REFERENCE_ATTACHMENT_TOOLS

from .ai_eval.runner import fixture_text


@pytest.mark.parametrize(
    "fixture,weights,entries,targets",
    [
        ("ward87", ["11000000000"], 89, 408),
        ("ward87", ["-.inf"], 8, 5130),
    ],
)
def test_counts_use_resolved_selectors(fixture, weights, entries, targets):
    source = fixture_text(fixture).encode()
    result = inspect_requests(build_result_context(source.decode()), source, weights=weights, max_requests=0)
    assert result["request_entries"] == entries
    assert result["person_date_targets"] == targets
    assert result["requests"] == []
    assert result["requests_truncated"]


def test_group_and_cross_month_filters_count_targets_per_entry():
    source = fixture_text("request-audit-groups").encode()
    context = build_result_context(source.decode())
    result = inspect_requests(context, source, people=["Asha"], dates=["2026-06-01"], max_requests=20)
    assert result["request_entries"] == result["person_date_targets"] == 2
    assert [r["preference_index"] for r in result["requests"]] == [5, 6]
    assert [r["shift_types"] for r in result["requests"]] == [["N"], ["K"]]
    assert not result["requests_truncated"]
    assert (
        inspect_requests(
            context, source, weights=["-11000000000"], people=["Asha"], dates=["2026-06-01"], max_requests=20
        )["request_entries"]
        == 1
    )


@pytest.mark.parametrize(
    "options,message",
    [
        ({"people": ["missing"]}, "Unknown person"),
        ({"dates": ["2026-06-32"]}, "Unknown ISO"),
        ({"weights": ["0"]}, "Zero-weight"),
        ({"max_requests": -1}, "max_requests"),
        ({"max_requests": 1001}, "max_requests"),
    ],
)
def test_unsupported_queries_fail_explicitly(options, message):
    source = fixture_text("request-audit-groups").encode()
    with pytest.raises(ValueError, match=message):
        inspect_requests(build_result_context(source.decode()), source, **options)


def test_edited_source_rejects_compiled_context():
    source = fixture_text("request-audit-groups").encode()
    with pytest.raises(ValueError, match="stale"):
        inspect_requests(build_result_context(source.decode()), source + b"\n")


def test_standalone_cli_uses_only_hydrated_helpers(tmp_path):
    for path in REFERENCE_ATTACHMENT_TOOLS.values():
        (tmp_path / path.name).write_bytes(path.read_bytes())
    source = fixture_text("ward87")
    (tmp_path / "schedule.yaml").write_text(source)
    (tmp_path / "context.json").write_text(json.dumps(build_result_context(source)))
    process = subprocess.run(
        [
            sys.executable,
            str(tmp_path / "inspect_shift_requests.py"),
            "--context",
            str(tmp_path / "context.json"),
            "--source",
            str(tmp_path / "schedule.yaml"),
            "--weight=-.inf",
            "--max-requests",
            "0",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(process.stdout)["person_date_targets"] == 5130
