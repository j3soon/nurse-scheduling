"""Check canonical staffing and succession audits against fixed optimizer assignments."""

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

import itertools

import pytest

from nurse_scheduling import schedule
from nurse_scheduling.ai.result_context import build_request_audit
from nurse_scheduling.loader import load_data
from nurse_scheduling.preference_audit import audit_staffing_and_successions

from .ai_eval.optimizer_fixtures import RESULT_SOURCES, completion_result
from .ai_test_helper import parse_schedule, schedule_yaml


def _forced(data, assignments):
    return {
        (d, s, p): int(assignments[d, p] == s)
        for d in range(len(data.compiled_schedule.dates))
        for s in range(len(data.shiftTypes.items))
        for p in range(len(data.people.items))
    }


def _source(preference, history):
    raw = parse_schedule(RESULT_SOURCES["policy-audit-misses"].read_text())
    raw["people"]["items"] = raw["people"]["items"][:2]
    for person in raw["people"]["items"]:
        person["history"] = history
    raw["preferences"] = [{"type": "at most one shift per day"}, preference]
    return schedule_yaml(raw)


@pytest.mark.parametrize(
    "pattern", [["N", "D"], ["ALL", "OFF"], [["N", "OFF"], "D"], ["N"], ["N", "D", "OFF"], ["D", "N", "D", "N"]]
)
@pytest.mark.parametrize("weight", [-7, 5])
@pytest.mark.parametrize("history", [[], ["N"], ["N", "D"], ["N", "D", "OFF"]])
def test_succession_audit_matches_optimizer_score(pattern, weight, history):
    source = _source(
        {"type": "shift type successions", "person": ["ALL"], "date": ["ALL"], "pattern": pattern, "weight": weight},
        history,
    )
    data = load_data(source.encode())
    assignments = {
        (d, p): s for (d, p), s in zip(itertools.product(range(3), range(2)), [-1, 1, 0, -1, 1, 0], strict=True)
    }
    result = schedule(source.encode(), solver="ortools/cp-sat", timeout=5, forced_solution=_forced(data, assignments))
    audit = audit_staffing_and_successions(data, assignments)
    assert result.solution == _forced(data, assignments)
    assert result.score == sum(
        row["weight"] * (row["unmet"] if row["weight"] < 0 else row["satisfied"]) for row in audit["successions"]
    )


@pytest.mark.parametrize("selectors", [["D", "N"], [["D", "N"]]])
@pytest.mark.parametrize("qualified", [None, ["Alex"]])
@pytest.mark.parametrize("dates", [["ALL"], ["01", "03"]])
def test_staffing_audit_matches_optimizer_score(selectors, qualified, dates):
    pref = {
        "type": "shift type requirement",
        "shiftType": selectors,
        "date": dates,
        "requiredNumPeople": 0,
        "preferredNumPeople": 6,
        "weight": -13,
    }
    if isinstance(selectors[0], list):
        pref["shiftTypeCoefficients"] = [["D", 2], ["N", 3]]
    if qualified:
        pref["qualifiedPeople"] = qualified
    source = _source(pref, [])
    data = load_data(source.encode())
    assignments = {(d, p): -1 if qualified and p else (d + p) % 2 for d in range(3) for p in range(2)}
    result = schedule(source.encode(), solver="ortools/cp-sat", timeout=5, forced_solution=_forced(data, assignments))
    audit = audit_staffing_and_successions(data, assignments)
    assert result.solution == _forced(data, assignments)
    assert result.score == sum(row["weight"] * row["preferred_shortfall"] for row in audit["staffing"])
    assert all(row["hard_unmet"] == 0 for row in audit["staffing"])


@pytest.mark.parametrize("name, misses, violations", [("policy-audit-misses", 3, 1), ("policy-audit-clean", 0, 0)])
def test_request_success_does_not_hide_staffing_or_succession_misses(name, misses, violations):
    source = RESULT_SOURCES[name].read_text()
    _, metadata = completion_result(name, source)
    audit = metadata["request_audit"]
    assert audit["source_sha256"] == metadata["source_sha256"]
    assert audit["summary"][0]["unmet"] == 0
    assert audit["policy"]["staffing"][0]["hard_unmet"] == 0
    assert audit["policy"]["staffing"][0]["preferred_unmet"] == misses
    assert audit["policy"]["staffing"][0]["preferred_shortfall"] == misses
    assert audit["policy"]["successions"][0]["unmet"] == violations
    assert audit["policy"]["successions"][0]["windows"] == 9


def test_policy_summary_size_limit_preserves_request_counts(monkeypatch):
    import json

    from nurse_scheduling.ai import result_context

    source = RESULT_SOURCES["policy-audit-misses"].read_text()
    workbook, metadata = completion_result("policy-audit-misses", source)
    requests = {k: v for k, v in metadata["request_audit"].items() if k != "policy"}
    requests["scope"] = "Expanded shift-request person/date cells. Staffing and rest are not audited."
    monkeypatch.setattr(result_context, "MAX_REQUEST_AUDIT_BYTES", len(json.dumps(requests).encode()) + 1)
    assert build_request_audit(source, workbook) == requests


def test_stale_policy_counts_have_a_different_source():
    source = RESULT_SOURCES["policy-audit-stale"].read_text()
    workbook, metadata = completion_result("policy-audit-stale", source)
    assert metadata["request_audit"]["source_sha256"] != metadata["source_sha256"]
    assert metadata["request_audit"]["policy"]["staffing"][0]["preferred_unmet"] == 0
    assert build_request_audit(source, workbook)["policy"]["staffing"][0]["preferred_unmet"] == 3


def test_incomplete_or_unknown_assignments_cannot_produce_a_policy_verdict():
    source = _source({"type": "shift type successions", "person": ["ALL"], "pattern": ["N", "D"], "weight": -1}, [])
    data = load_data(source.encode())
    with pytest.raises(ValueError, match="every person and date"):
        audit_staffing_and_successions(data, {})
    with pytest.raises(ValueError, match="Unknown assigned shift"):
        audit_staffing_and_successions(data, {(d, p): 99 for d in range(3) for p in range(2)})


def test_result_reader_reuses_only_the_policy_for_this_workbook(tmp_path):
    from nurse_scheduling.ai.attachment_tools.inspect_optimizer_result import inspect_result
    from nurse_scheduling.ai.result_context import build_result_context

    source = RESULT_SOURCES["policy-audit-misses"].read_text()
    workbook, metadata = completion_result("policy-audit-misses", source)
    context = build_result_context(source, workbook=workbook)
    path = tmp_path / "result.xlsx"
    path.write_bytes(workbook)
    audit = inspect_result(path, context, metadata["source_sha256"])
    assert audit["policy"] == metadata["request_audit"]["policy"]
    assert audit["policy"]["successions"][0]["satisfied"] == 8
    assert audit["policy"]["successions"][0]["goal"] == "avoid_pattern"
    clean, _ = completion_result("policy-audit-clean", source)
    path.write_bytes(clean)
    changed = inspect_result(path, context, metadata["source_sha256"])
    assert "policy" not in changed
    assert "policy_unavailable" in changed
    assert changed["summary"][0]["unmet"] == 0
    selected = inspect_result(path, context, metadata["source_sha256"], people=["Kai"])
    assert selected["assignments"][0]["shift_type"] == "OFF"


def test_policy_context_is_optional_for_unsupported_workbooks():
    from nurse_scheduling.ai.result_context import build_result_context

    source = RESULT_SOURCES["policy-audit-misses"].read_text()
    assert build_result_context(source, workbook=b"invalid workbook") == build_result_context(source)


def test_a_succession_match_crossing_history_is_counted():
    source = _source(
        {"type": "shift type successions", "person": ["ALL"], "date": ["ALL"], "pattern": ["N", "D"], "weight": -7},
        ["N"],
    )
    data = load_data(source.encode())
    assignments = {(d, p): -1 for d in range(3) for p in range(2)}
    assignments[0, 0] = 0
    row = audit_staffing_and_successions(data, assignments)["successions"][0]
    assert row["windows"] == 6
    assert row["satisfied"] == 5
    assert row["unmet"] == 1


@pytest.mark.parametrize(
    "pattern,history,future",
    [
        (["N", "D"], ["N"], ["D"]),
        (["N", "D", "OFF"], ["N", "D"], ["OFF"]),
        (["N", "D", "N", "D"], ["N", "D", "N"], ["D", "OFF"]),
    ],
)
@pytest.mark.parametrize("weight", [-10, 7])
def test_short_horizon_still_checks_history_crossing_patterns(pattern, history, future, weight):
    raw = parse_schedule(RESULT_SOURCES["policy-audit-misses"].read_text())
    raw["dates"]["range"]["endDate"] = f"2026-05-{len(future):02d}"
    raw["people"]["items"] = [{"id": "Kai", "description": "", "history": history}]
    raw["preferences"] = [
        {"type": "at most one shift per day"},
        {
            "type": "shift type successions",
            "person": ["ALL"],
            "date": ["ALL"],
            "pattern": pattern,
            "weight": weight,
        },
    ]
    source = schedule_yaml(raw)
    data = load_data(source.encode())
    ids = {s.id: i for i, s in enumerate(data.shiftTypes.items)}
    ids["OFF"] = -1
    assignments = {(d, 0): ids[shift] for d, shift in enumerate(future)}
    audit = audit_staffing_and_successions(data, assignments)["successions"][0]
    assert audit["windows"] == 1
    assert audit["unmet" if weight < 0 else "satisfied"] == 1
    result = schedule(source.encode(), solver="ortools/cp-sat", timeout=5, forced_solution=_forced(data, assignments))
    assert result.score == weight


def test_short_horizon_optimizer_avoids_a_history_rest_penalty():
    raw = parse_schedule(RESULT_SOURCES["policy-audit-misses"].read_text())
    raw["dates"]["range"]["endDate"] = "2026-05-01"
    raw["people"]["items"] = [{"id": "Kai", "description": "", "history": ["N"]}]
    raw["preferences"] = [
        {"type": "at most one shift per day"},
        {
            "type": "shift request",
            "person": ["Kai"],
            "date": ["ALL"],
            "shiftType": ["D"],
            "weight": 1,
        },
        {
            "type": "shift type successions",
            "person": ["ALL"],
            "date": ["ALL"],
            "pattern": ["N", "D"],
            "weight": -10,
        },
    ]
    result = schedule(schedule_yaml(raw).encode(), solver="ortools/cp-sat", timeout=5)
    assert result.solver_status == "OPTIMAL"
    assert result.score == 0
    assert result.solution[0, 0, 0] == 0


@pytest.mark.parametrize(
    "history,pattern,dates,days",
    [
        ([], ["N", "D"], ["ALL"], 1),
        (["N"], ["N", "D", "OFF"], ["ALL"], 1),
        (["N", "D"], ["N", "D"], ["ALL"], 1),
        (["N", "D"], ["N", "D", "OFF"], ["02"], 2),
    ],
)
def test_short_history_windows_require_future_evidence_and_selected_dates(history, pattern, dates, days):
    raw = parse_schedule(RESULT_SOURCES["policy-audit-misses"].read_text())
    raw["dates"]["range"]["endDate"] = f"2026-05-{days:02d}"
    raw["people"]["items"] = [{"id": "Kai", "description": "", "history": history}]
    raw["preferences"] = [
        {"type": "at most one shift per day"},
        {"type": "shift type successions", "person": ["ALL"], "date": dates, "pattern": pattern, "weight": -10},
    ]
    data = load_data(schedule_yaml(raw).encode())
    audit = audit_staffing_and_successions(data, {(d, 0): -1 for d in range(days)})["successions"][0]
    assert audit["windows"] == 0


def test_short_horizon_hard_history_rest_rule_rejects_a_forced_day():
    raw = parse_schedule(RESULT_SOURCES["policy-audit-misses"].read_text())
    raw["dates"]["range"]["endDate"] = "2026-05-01"
    raw["people"]["items"] = [{"id": "Kai", "description": "", "history": ["N"]}]
    raw["preferences"] = [
        {"type": "at most one shift per day"},
        {
            "type": "shift type successions",
            "person": ["ALL"],
            "date": ["ALL"],
            "pattern": ["N", "D"],
            "weight": float("-inf"),
        },
    ]
    source = schedule_yaml(raw)
    data = load_data(source.encode())
    result = schedule(source.encode(), solver="ortools/cp-sat", timeout=5, forced_solution=_forced(data, {(0, 0): 0}))
    assert result.solver_status == "INFEASIBLE"
