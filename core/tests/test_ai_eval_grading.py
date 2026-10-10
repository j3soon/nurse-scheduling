"""Tests for evaluation case loading and verifiable grading."""

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

import copy
import hashlib
import json
from pathlib import Path

import pytest

from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.pi.edit import EDIT_TOOL
from nurse_scheduling.ai.pi.read import READ_TOOL
from nurse_scheduling.ai.pi.write import WRITE_TOOL
from nurse_scheduling.ai.schedule_context import describe_schedule
from nurse_scheduling.loader import _load_yaml

from .ai_eval.attachment_fixtures import attachment_fixture_names, load_attachment_fixtures
from .ai_eval.grading import (
    EvalCase,
    EvalCaseError,
    RunOutcome,
    computed_values,
    covered_paths,
    covered_preference_types,
    grade,
    load_cases,
    resolve,
)

CASES_PATH = Path(__file__).parent / "ai_eval" / "cases"
NEW_SCHEDULE_PATH = Path(__file__).parent / "ai_eval" / "fixtures" / "new-schedule.yaml"
SMALL_CLINIC_PATH = Path(__file__).parent / "ai_eval" / "fixtures" / "small-clinic.yaml"
CROSS_YEAR_UNIT_PATH = Path(__file__).parent / "ai_eval" / "fixtures" / "cross-year-unit.yaml"
WARD_PATH = Path(__file__).parent / "testcases" / "real" / "large-ward-with-87-people-2025-11.yaml"

FIXTURE_SCHEDULES = {
    "shift-groups": _load_yaml((CASES_PATH.parent / "fixtures" / "shift-groups.yaml").read_bytes()),
    "policy-audit": _load_yaml((CASES_PATH.parent / "fixtures" / "policy-audit.yaml").read_bytes()),
    "request-audit-groups": _load_yaml((CASES_PATH.parent / "fixtures" / "request-audit-groups.yaml").read_bytes()),
    "weight-units": _load_yaml((CASES_PATH.parent / "fixtures" / "weight-units.yaml").read_bytes()),
    "request-audit": _load_yaml((CASES_PATH.parent / "fixtures" / "request-audit.yaml").read_bytes()),
    "cross-year-unit": _load_yaml(CROSS_YEAR_UNIT_PATH.read_bytes()),
    "new-schedule": _load_yaml(NEW_SCHEDULE_PATH.read_bytes()),
    "small-clinic": _load_yaml(SMALL_CLINIC_PATH.read_bytes()),
    "ward87": _load_yaml(WARD_PATH.read_bytes()),
}

SCHEDULE = {
    "description": "Ward A",
    "dates": {"range": {"startDate": "2026-03-01", "endDate": "2026-03-14"}, "groups": []},
    "people": {
        "items": [{"id": "P1", "description": "Head nurse"}, {"id": "P2", "description": ""}],
        "groups": [{"id": "Day People", "members": ["P1"]}, {"id": "Day People w/o A", "members": ["P2"]}],
    },
    "preferences": [
        {"type": "at most one shift per day"},
        {"type": "shift request", "person": ["P1"], "date": ["2026-03-02"], "shiftType": ["N"], "weight": 1},
    ],
}


def qualified_staffing_proposal(general_count=1, qualified=("S1", "S2")):
    proposed = copy.deepcopy(FIXTURE_SCHEDULES["new-schedule"])
    proposed["dates"]["range"] = {"startDate": "2026-03-01", "endDate": "2026-03-01"}
    proposed["people"]["items"] = [{"id": p, "description": ""} for p in ("S1", "S2", "J1", "J2", "J3")]
    proposed["people"]["groups"] = [{"id": "Seniors", "description": "", "members": list(qualified)}]
    proposed["shiftTypes"]["items"] = [{"id": s, "description": ""} for s in ("D", "D+", "E", "N")]
    proposed["preferences"] = [
        {"type": "at most one shift per day"},
        *[
            {
                "type": "shift type requirement",
                "shiftType": [s],
                "date": ["ALL"],
                "qualifiedPeople": ["Seniors"] if s == "D+" else ["ALL"],
                "requiredNumPeople": n,
            }
            for s, n in (("D", general_count), ("D+", 1), ("E", 1), ("N", 1))
        ],
    ]
    return proposed


@pytest.mark.parametrize("general_count", [1, 2])
@pytest.mark.parametrize(
    "wrong_field",
    [None, "day_slots", "total_working_slots", "off_people", "senior_day_slots", "eligible_senior_people"],
)
def test_staffing_explanation_checks_arithmetic_separately_from_proposal(general_count, wrong_field):
    case_id = "staffing-explanation-" + ("included-in-day-total" if general_count == 1 else "additional-day-slot")
    case = next(c for c in load_cases(CASES_PATH) if c.id == case_id)
    answer = copy.deepcopy(case.answer_json)
    if wrong_field:
        answer[wrong_field] += 1
    result = grade(
        case,
        RunOutcome(
            initial=FIXTURE_SCHEDULES["new-schedule"],
            proposed=qualified_staffing_proposal(general_count),
            answer=json.dumps(answer),
        ),
    )
    assert result.passed == (wrong_field is None)


@pytest.mark.parametrize(
    "case_id,general_count,passed",
    [
        ("senior-included-in-day-total", 1, True),
        ("senior-included-in-day-total", 2, False),
        ("senior-additional-day-slot", 2, True),
        ("senior-additional-day-slot", 1, False),
    ],
)
def test_staffing_grader_distinguishes_inclusive_and_additive_counts(case_id, general_count, passed):
    case = next(c for c in load_cases(CASES_PATH) if c.id == case_id)
    proposed = qualified_staffing_proposal(general_count)
    result = grade(case, RunOutcome(initial=FIXTURE_SCHEDULES[case.fixture], proposed=proposed))
    assert result.passed == passed


def test_staffing_grader_rejects_unqualified_senior_slots():
    case = next(c for c in load_cases(CASES_PATH) if c.id == "senior-included-in-day-total")
    result = grade(
        case,
        RunOutcome(initial=FIXTURE_SCHEDULES[case.fixture], proposed=qualified_staffing_proposal(qualified=("J1",))),
    )
    assert not result.passed


@pytest.mark.parametrize("general_count", [1, 2])
def test_staffing_oracle_reference_assignment_is_solver_feasible(general_count):
    import yaml

    from nurse_scheduling.ai.validation import validate_frontend_schedule_yaml
    from nurse_scheduling.frontend_validation import load_frontend_data
    from nurse_scheduling.scheduler import schedule

    source = yaml.safe_dump(qualified_staffing_proposal(general_count)).encode()
    assert validate_frontend_schedule_yaml(source.decode(), max_bytes=50_000).valid
    data = load_frontend_data(source)
    assigned = ["D+", "D" if general_count == 2 else "OFF", "D", "E", "N"]
    forced = {
        (0, s, p): int(assigned[p] == item.id)
        for s, item in enumerate(data.shiftTypes.items)
        for p in range(len(data.people.items))
    }
    result = schedule(source, solver="ortools/cp-sat", timeout=5, forced_solution=forced)
    assert result.solver_status == "OPTIMAL"
    assert result.solution == forced


def _case(**overrides) -> object:
    entry = {"id": "case", "fixture": "new-schedule", "question": "q", "expect_proposal": True}
    entry.update(overrides)
    return entry


def _write(tmp_path: Path, *entries: dict) -> Path:
    """Write one case per file, the way the dataset is stored."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        (tmp_path / f"{entry['id']}.json").write_text(json.dumps(entry), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    "context",
    [{"frontend_timezone": "Unknown/Place"}, {"current_time": "2031-03-31T23:30:00"}, {"current_time": "bad"}],
    ids=["unknown-zone", "missing-offset", "invalid-time"],
)
def test_invalid_clock_context_is_rejected(tmp_path, context):
    with pytest.raises(EvalCaseError, match="clock context"):
        load_cases(_write(tmp_path, _case(expect_proposal=False, **context)))


def test_misspelled_assertion_key_cannot_silently_drop_schedule_checks(tmp_path):
    with pytest.raises(EvalCaseError, match="must use `assert`"):
        load_cases(_write(tmp_path, _case(assertions=[{"path": "description", "kind": "equals", "value": "Ward"}])))


@pytest.mark.parametrize("field", ["answer_jsno", "semantic_checks", "tool_usgae", "expected_diffs"])
def test_unknown_case_fields_cannot_silently_drop_checks(tmp_path, field):
    with pytest.raises(EvalCaseError, match=f"unknown case fields: {field}"):
        load_cases(_write(tmp_path, _case(expect_proposal=False, **{field: {}})))


@pytest.mark.parametrize("night,passed", [("N", True), ("N+", True), ("N", False)])
def test_qualified_explanation_grades_counts_instead_of_a_night_suffix(night, passed):
    case = next(c for c in load_cases(CASES_PATH) if c.id == "new-schedule-qualified-slots")
    counts = copy.deepcopy(case.answer_json)
    if not passed:
        counts["night"] = {"total": 2, "senior": 1, "other": 1}
    answer = (
        f"Use D+ and E+ for senior slots. {night} is senior-only. "
        "A single unrestricted D requirement cannot guarantee a one-senior and one-other mix.\n" + json.dumps(counts)
    )
    activity = [
        {
            "kind": "tool",
            "name": "read",
            "ok": True,
            "arguments": json.dumps({"path": "/reference/user-guide/build-a-real-schedule.md"}),
        }
    ]
    assert grade(case, RunOutcome(answer=answer, activity=activity)).passed == passed
    if passed:
        invalid = "This app cannot represent senior staffing.\n" + answer
        assert not grade(case, RunOutcome(answer=invalid, activity=activity)).passed


@pytest.mark.parametrize("members,passes", [(["D"], True), (["D", "E"], False)])
def test_day_group_creation_grades_the_actual_members(members, passes):
    from io import StringIO

    from ruamel.yaml import YAML

    from nurse_scheduling.ai.validation import validate_frontend_schedule_yaml

    case = next(c for c in load_cases(CASES_PATH) if c.id == "day-group-creation")
    proposed = copy.deepcopy(FIXTURE_SCHEDULES[case.fixture])
    proposed["shiftTypes"]["items"].append({"id": "E", "description": "Evening shift"})
    proposed["shiftTypes"]["groups"].append({"id": "Day", "description": "Daytime shifts", "members": members})
    source = StringIO()
    YAML(typ="safe").dump(proposed, source)
    assert validate_frontend_schedule_yaml(source.getvalue(), max_bytes=50_000).valid
    assert grade(case, RunOutcome(initial=FIXTURE_SCHEDULES[case.fixture], proposed=proposed)).passed == passes


@pytest.mark.parametrize("members,passes", [(["D", "D+"], True), (["D", "D+", "E", "N"], False)])
def test_day_group_grader_rejects_automatic_evening_and_night_members(members, passes):
    case = next(c for c in load_cases(CASES_PATH) if c.id == "day-group-adds-only-day-shifts")
    proposed = copy.deepcopy(FIXTURE_SCHEDULES[case.fixture])
    proposed["shiftTypes"]["items"].append({"id": "D+", "description": "Senior day shift"})
    proposed["shiftTypes"]["groups"][0]["members"] = members
    result = grade(case, RunOutcome(initial=FIXTURE_SCHEDULES[case.fixture], proposed=proposed))
    assert result.passed == passes


def test_day_group_grader_accepts_explicit_custom_membership():
    case = next(c for c in load_cases(CASES_PATH) if c.id == "day-group-explicit-broadening-control")
    proposed = copy.deepcopy(FIXTURE_SCHEDULES[case.fixture])
    proposed["shiftTypes"]["groups"][0]["members"] = ["N", "D", "E"]
    assert grade(case, RunOutcome(initial=FIXTURE_SCHEDULES[case.fixture], proposed=proposed)).passed


def test_day_group_reference_fixture_is_valid_and_all_still_includes_every_shift():
    from nurse_scheduling.ai.validation import validate_frontend_schedule_yaml
    from nurse_scheduling.frontend_validation import load_frontend_data

    source = (CASES_PATH.parent / "fixtures" / "shift-groups.yaml").read_bytes()
    assert validate_frontend_schedule_yaml(source.decode(), max_bytes=50_000).valid
    compiled = load_frontend_data(source).compiled_schedule
    assert compiled.map_sid_s["Day"] == (0,)
    assert compiled.map_sid_s["ALL"] == (0, 1, 2)


@pytest.mark.parametrize(
    "command, allowed",
    [
        ("date +%Y-%m-%d", False),
        ("TZ=Asia/Taipei date +%H:%M", False),
        ("echo $(date)", False),
        ("python -c 'from datetime import datetime; print(datetime.now())'", False),
        ("date -d '2031-04-01' +%Y-%m-%d", True),
        ("TZ=Asia/Taipei date --date='2031-04-01' +%Y-%m-%d", True),
        ("python -c 'from datetime import date; print(date(2031, 4, 1))'", True),
    ],
    ids=["shell-now", "shell-zone", "substitution", "python-now", "shell-input", "shell-input-zone", "python-input"],
)
def test_clock_grading_distinguishes_vm_time_from_supplied_date_calculations(command, allowed):
    from .ai_eval.grading import _check_vm_clock_queries

    event = {"kind": "tool_start", "name": "bash", "arguments": json.dumps({"command": command})}
    assert _check_vm_clock_queries([event])[0].passed is allowed


@pytest.mark.parametrize("delivered", ["original-sha", "changed-sha"], ids=["unchanged", "changed"])
def test_optimizer_archive_grades_actual_delivered_bytes(delivered):
    case = next(case for case in load_cases(CASES_PATH) if case.id == "optimizer-result-explicit-zip")
    outcome = RunOutcome(
        initial=FIXTURE_SCHEDULES[case.fixture],
        activity=[
            {"kind": "optimizer", "turn": 2},
            {"kind": "optimizer_artifact", "sha256": "original-sha"},
            {"kind": "download", "files": {"original-result.xlsx": delivered}},
        ],
        intermediate_answers=("Started.", "Use Download result."),
        proposal_turns=(False, False, False),
    )
    assert grade(case, outcome).passed is (delivered == "original-sha")


@pytest.mark.parametrize(
    "answer, allowed",
    [("Use Download result.", True), ("Would you like me to prepare a ZIP download?", False)],
    ids=["existing-button", "redundant-offer"],
)
def test_download_grading_rejects_an_offer_in_the_completion_reply(answer, allowed):
    case = next(case for case in load_cases(CASES_PATH) if case.id == "optimizer-result-already-downloadable")
    outcome = RunOutcome(
        initial=FIXTURE_SCHEDULES[case.fixture],
        answer="Use Download result.",
        activity=[{"kind": "optimizer", "turn": 2}, {"kind": "optimizer_artifact", "sha256": "original-sha"}],
        intermediate_answers=("Started.", "Use Download result. " + answer),
        proposal_turns=(False, False, False),
    )
    assert grade(case, outcome).passed is allowed


def test_resolves_fields_indexes_and_selectors():
    assert resolve(SCHEDULE, "dates.range.startDate") == ["2026-03-01"]
    assert resolve(SCHEDULE, "people.items[0].id") == ["P1"]
    assert resolve(SCHEDULE, "people.items[?id=P1].description") == ["Head nurse"]
    assert resolve(SCHEDULE, "people.items[?id=P9]") == []


def test_turn_tool_limits_do_not_penalize_edits_after_clarification(tmp_path: Path):
    case = load_cases(
        _write(
            tmp_path,
            _case(
                expect_proposal=False,
                user_turns=["Add a request.", "Use N."],
                turn_tool_usage=[{"max_total": 0}, {"required": ["edit"]}],
            ),
        )
    )[0]
    tool = {"kind": "tool", "name": "edit", "ok": True}
    events = [{"kind": "user", "turn": 1}, {"kind": "user", "turn": 2}, tool]
    assert grade(case, RunOutcome(activity=events)).passed
    premature = [{"kind": "user", "turn": 1}, tool, {"kind": "user", "turn": 2}, tool]
    failures = grade(case, RunOutcome(activity=premature)).failures()
    assert len(failures) == 1
    assert failures[0].description == "turn 1: uses at most 0 tool call(s)"


@pytest.mark.parametrize("raw", [{}, [{}, None], [{"max_total": -1}]])
def test_invalid_turn_tool_limits_are_rejected(tmp_path: Path, raw):
    with pytest.raises(EvalCaseError, match="turn_tool_usage|max_total"):
        load_cases(_write(tmp_path, _case(expect_proposal=False, turn_tool_usage=raw)))


@pytest.mark.parametrize(
    ("answer", "passes"),
    [
        ("No, the proposal is pending. You must approve it.", True),
        ("NOT YET. Your approval is required.", True),
        ("It has not changed. Please approve the proposal first.", True),
        ("No, the saved schedule is updated only after your approval.", True),
        ("Now updated. Please approve it.", False),
        ("Yes, the saved schedule changed. Approval is pending.", False),
        ("No other fields changed. The saved schedule has now changed. Please approve it.", False),
        ("No, it has not changed.", False),
    ],
)
def test_proposal_answer_contract_accepts_denials_and_rejects_false_adoption(answer, passes):
    case = next(case for case in load_cases(CASES_PATH) if case.id == "proposal-is-not-saved-yet")
    proposed = copy.deepcopy(FIXTURE_SCHEDULES[case.fixture])
    proposed["description"] = "April clinic roster"
    outcome = RunOutcome(
        answer=f"April clinic roster. {answer}", proposed=proposed, initial=FIXTURE_SCHEDULES[case.fixture]
    )
    assert grade(case, outcome).passed == passes


@pytest.mark.parametrize("field_name", ["answer_matches", "answer_not_matches"])
@pytest.mark.parametrize("raw", ["not a list", [""], [123], ["["]])
def test_invalid_answer_patterns_are_rejected(tmp_path: Path, field_name, raw):
    with pytest.raises(EvalCaseError, match=field_name):
        load_cases(_write(tmp_path, _case(expect_proposal=False, **{field_name: raw})))


@pytest.mark.parametrize("answer", ["There is no shift type S in the schedule.", "S is absent.", "S was not found."])
def test_missing_shift_case_accepts_equivalent_correct_refusals(answer):
    case = next(case for case in load_cases(CASES_PATH) if case.id == "rename-unknown-shift")
    assert grade(case, RunOutcome(answer=answer)).passed


def test_a_selector_matches_one_id_exactly():
    # `Day People` is a prefix of `Day People w/o A`, so a loose match would
    # silently grade against the wrong group.
    assert resolve(SCHEDULE, "people.groups[?id=Day People].members") == [["P1"]]


def test_selectors_chain_and_match_inside_list_fields():
    found = resolve(SCHEDULE, "preferences[?type=shift request][?person=P1][?shiftType=N]")

    assert len(found) == 1
    assert found[0]["date"] == ["2026-03-02"]


def test_expands_a_list_into_its_entries():
    assert resolve(SCHEDULE, "people.items[].id") == ["P1", "P2"]
    assert resolve(SCHEDULE, "people.groups[].members") == [["P1"], ["P2"]]


def test_delta_compares_a_collection_with_the_fixture(tmp_path: Path):
    grown = copy.deepcopy(SCHEDULE)
    grown["people"]["items"].append({"id": "P3", "description": ""})
    case = _case(**{"assert": [{"path": "people.items", "delta": 1}], "changes": ["people.items"]})
    loaded = load_cases(_write(tmp_path, case))[0]

    assert grade(loaded, RunOutcome(proposed=grown, initial=SCHEDULE)).passed
    assert not grade(loaded, RunOutcome(proposed=SCHEDULE, initial=SCHEDULE)).passed


def test_added_and_removed_name_the_entries_that_changed(tmp_path: Path):
    renamed = copy.deepcopy(SCHEDULE)
    renamed["people"]["items"][0]["id"] = "Alice"
    case = _case(
        **{
            "assert": [
                {"path": "people.items[].id", "added": ["Alice"]},
                {"path": "people.items[].id", "removed": ["P1"]},
            ],
            "changes": ["people.items"],
        }
    )

    assert grade(load_cases(_write(tmp_path, case))[0], RunOutcome(proposed=renamed, initial=SCHEDULE)).passed


def test_added_catches_an_extra_entry_that_a_size_would_miss(tmp_path: Path):
    # Adding two entries and removing one leaves the size unchanged by +1, so
    # only identity catches it.
    sloppy = copy.deepcopy(SCHEDULE)
    sloppy["people"]["items"] = [
        {"id": "P1", "description": "Head nurse"},
        {"id": "Alice", "description": ""},
        {"id": "Bob", "description": ""},
    ]
    case = _case(
        **{
            "assert": [
                {"path": "people.items", "delta": 1},
                {"path": "people.items[].id", "added": ["Alice"]},
            ],
            "changes": ["people.items"],
        }
    )

    result = grade(load_cases(_write(tmp_path, case))[0], RunOutcome(proposed=sloppy, initial=SCHEDULE))

    assert [check.passed for check in result.checks[1:3]] == [True, False]
    assert "Bob" in result.failures()[0].detail


def test_expected_diff_compares_the_complete_collection_delta(tmp_path: Path):
    added = {"id": "P3", "description": "Float nurse"}
    changed = copy.deepcopy(SCHEDULE)
    changed["people"]["items"].append(added)
    case = _case(
        expected_diff=[{"path": "people.items", "added": [added]}],
        changes=["people.items"],
    )
    loaded = load_cases(_write(tmp_path, case))[0]

    assert grade(loaded, RunOutcome(proposed=changed, initial=SCHEDULE)).passed

    changed["people"]["items"].append({"id": "P4", "description": ""})
    result = grade(loaded, RunOutcome(proposed=changed, initial=SCHEDULE))
    assert not result.passed
    assert "P4" in result.failures()[0].detail


@pytest.mark.parametrize("extend_custom", [False, True], ids=["preserve-custom", "extend-custom"])
def test_calendar_scope_cases_reject_the_opposite_custom_group_behavior(extend_custom):
    initial = FIXTURE_SCHEDULES["small-clinic"]
    changed = copy.deepcopy(initial)
    changed["dates"]["range"]["endDate"] = "2026-01-18"
    weekdays = ["05", "06", "07", "08", "09", "12", "13", "14", "15", "16"]
    changed["dates"]["groups"].extend(
        [
            {
                "id": "WORKDAY",
                "description": "Taiwan workdays imported from the current holiday calendar",
                "members": weekdays,
            },
            {
                "id": "FREEDAY",
                "description": "Taiwan freedays imported from the current holiday calendar",
                "members": ["10", "11", "17", "18"],
            },
        ]
    )
    if extend_custom:
        changed["dates"]["groups"][0]["members"] = weekdays
    name = "dates-range-renew-custom-group-small" if extend_custom else "dates-range-renew-small"
    path = CASES_PATH / "basics" / "03-structure"
    case = load_cases(path / f"{name}.json")[0]
    opposite = load_cases(
        path / f"{'dates-range-renew-small' if extend_custom else 'dates-range-renew-custom-group-small'}.json"
    )[0]
    outcome = RunOutcome(
        proposed=changed,
        initial=initial,
        intermediate_answers=["Should I renew Taiwan holiday date groups?"],
        intermediate_proposals=[False],
        proposal_turns=[False, True],
    )
    assert grade(case, outcome).passed
    assert not grade(opposite, outcome).passed


def test_expected_diff_supports_replacing_a_complete_object(tmp_path: Path):
    before = SCHEDULE["people"]["items"][0]
    after = {**before, "description": "Lead nurse"}
    changed = copy.deepcopy(SCHEDULE)
    changed["people"]["items"][0] = after
    case = _case(
        expected_diff=[{"path": "people.items", "removed": [before], "added": [after]}],
        changes=["people.items"],
    )

    assert grade(load_cases(_write(tmp_path, case))[0], RunOutcome(proposed=changed, initial=SCHEDULE)).passed


def test_expected_diff_uses_json_strings_for_yaml_infinity(tmp_path: Path):
    changed = copy.deepcopy(SCHEDULE)
    added = {"type": "shift count", "weight": float("-inf")}
    changed["preferences"].append(added)
    case = _case(
        expected_diff=[{"path": "preferences", "added": [{"type": "shift count", "weight": "-.inf"}]}],
        changes=["preferences"],
    )

    assert grade(load_cases(_write(tmp_path, case))[0], RunOutcome(proposed=changed, initial=SCHEDULE)).passed


def test_hard_staffing_ignores_ineffective_weight_but_keeps_count_and_qualification(tmp_path: Path):
    requirement = {
        "type": "shift type requirement",
        "shiftType": ["N"],
        "date": ["ALL"],
        "requiredNumPeople": 1,
        "qualifiedPeople": ["P1"],
    }
    case = load_cases(
        _write(
            tmp_path, _case(expected_diff=[{"path": "preferences", "added": [requirement]}], changes=["preferences"])
        )
    )[0]
    changed = copy.deepcopy(SCHEDULE)
    changed["preferences"].append({**requirement, "weight": -1000})
    assert grade(case, RunOutcome(proposed=changed, initial=SCHEDULE)).passed
    for key, value in (("requiredNumPeople", 0), ("qualifiedPeople", ["P2"]), ("preferredNumPeople", 2)):
        modified = copy.deepcopy(changed)
        modified["preferences"][-1][key] = value
        assert not grade(case, RunOutcome(proposed=modified, initial=SCHEDULE)).passed


def test_preferred_staffing_weight_remains_semantic(tmp_path: Path):
    requirement = {"type": "shift type requirement", "requiredNumPeople": 1, "preferredNumPeople": 2, "weight": -10}
    case = load_cases(
        _write(
            tmp_path, _case(expected_diff=[{"path": "preferences", "added": [requirement]}], changes=["preferences"])
        )
    )[0]
    changed = copy.deepcopy(SCHEDULE)
    changed["preferences"].append({**requirement, "weight": -1})
    assert not grade(case, RunOutcome(proposed=changed, initial=SCHEDULE)).passed


def test_optional_new_descriptions_do_not_allow_changes_to_existing_rules(tmp_path: Path):
    added = {"type": "shift request", "person": ["P2"], "date": ["ALL"], "shiftType": ["N"], "weight": 1}
    case = load_cases(
        _write(
            tmp_path,
            _case(
                expected_diff=[{"path": "preferences", "added": [added], "allow_added_description": True}],
                changes=["preferences"],
            ),
        )
    )[0]
    changed = copy.deepcopy(SCHEDULE)
    changed["preferences"].append({**added, "description": "P2 night preference"})
    assert grade(case, RunOutcome(proposed=changed, initial=SCHEDULE)).passed
    changed["preferences"][0]["description"] = "Unexpected rewrite"
    assert not grade(case, RunOutcome(proposed=changed, initial=SCHEDULE)).passed


@pytest.mark.parametrize(
    "entry",
    [
        {"added": [{"description": "Requested label"}]},
        {"added": [{}], "removed": [{}]},
        {"before": "old", "after": "new"},
    ],
)
def test_optional_description_flag_cannot_hide_requested_or_existing_fields(tmp_path: Path, entry):
    with pytest.raises(EvalCaseError, match="optional descriptions"):
        load_cases(
            _write(
                tmp_path,
                _case(
                    expected_diff=[{"path": "preferences", **entry, "allow_added_description": True}],
                    changes=["preferences"],
                ),
            )
        )


def test_expected_diff_normalizes_unordered_members_and_optional_defaults(tmp_path: Path):
    changed = copy.deepcopy(SCHEDULE)
    changed["people"]["items"].append({"id": "P3"})
    changed["people"]["groups"][0]["members"] = ["P2", "P1"]
    expected_group = {"id": "Day People", "members": ["P1", "P2"]}
    case = _case(
        expected_diff=[
            {"path": "people.items", "added": [{"id": "P3", "description": "", "history": []}]},
            {
                "path": "people.groups",
                "removed": [SCHEDULE["people"]["groups"][0]],
                "added": [expected_group],
            },
        ],
        changes=["people.items", "people.groups"],
    )

    assert grade(load_cases(_write(tmp_path, case))[0], RunOutcome(proposed=changed, initial=SCHEDULE)).passed


def test_expected_diff_supports_replacing_or_adding_a_value(tmp_path: Path):
    changed = copy.deepcopy(SCHEDULE)
    changed["description"] = "Ward B"
    changed["export"] = {"format": "csv"}
    case = _case(
        expected_diff=[
            {"path": "description", "before": "Ward A", "after": "Ward B"},
            {"path": "export", "before": None, "after": {"format": "csv"}},
        ],
        changes=["description", "export"],
    )

    assert grade(load_cases(_write(tmp_path, case))[0], RunOutcome(proposed=changed, initial=SCHEDULE)).passed


def test_count_reads_list_length_or_match_count(tmp_path: Path):
    case = _case(**{"assert": [{"path": "people.items", "count": 2}], "changes": ["people"]})
    other = _case(**{"assert": [{"path": "people.items[?id=P1]", "count": 1}], "changes": ["people"]})
    outcome = RunOutcome(proposed=SCHEDULE, initial=SCHEDULE)

    assert grade(load_cases(_write(tmp_path / "a", case))[0], outcome).passed
    assert grade(load_cases(_write(tmp_path / "b", other))[0], outcome).passed


def test_list_comparison_is_ordered_and_entry_by_entry(tmp_path: Path):
    ordered = copy.deepcopy(SCHEDULE)
    ordered["preferences"].append({"type": "shift type successions", "person": ["P1"], "pattern": ["N", "D"]})
    reversed_pattern = copy.deepcopy(SCHEDULE)
    reversed_pattern["preferences"].append({"type": "shift type successions", "person": ["P1"], "pattern": ["D", "N"]})
    case = _case(
        **{
            "assert": [{"path": "preferences[?type=shift type successions].pattern", "equals": ["N", "D"]}],
            "changes": ["preferences"],
        }
    )
    loaded = load_cases(_write(tmp_path, case))[0]

    # N then D is a different rule from D then N, so order has to count.
    assert grade(loaded, RunOutcome(proposed=ordered, initial=SCHEDULE)).passed
    assert not grade(loaded, RunOutcome(proposed=reversed_pattern, initial=SCHEDULE)).passed


def test_text_comparison_ignores_case_and_surrounding_space(tmp_path: Path):
    case = _case(
        **{"assert": [{"path": "people.items[?id=P1].description", "equals": " head NURSE "}], "changes": ["people"]}
    )

    result = grade(load_cases(_write(tmp_path, case))[0], RunOutcome(proposed=SCHEDULE, initial=SCHEDULE))

    assert result.passed


def test_a_change_outside_the_allowed_paths_fails(tmp_path: Path):
    changed = copy.deepcopy(SCHEDULE)
    changed["dates"]["range"]["endDate"] = "2026-04-01"
    case = _case(**{"assert": [{"path": "description", "equals": "Ward A"}], "changes": ["description"]})

    result = grade(load_cases(_write(tmp_path, case))[0], RunOutcome(proposed=changed, initial=SCHEDULE))

    assert not result.passed
    # No allowed path runs through `dates`, so the whole section is reported.
    assert "also changed dates" in result.failures()[0].detail


def test_a_change_inside_the_allowed_paths_passes(tmp_path: Path):
    changed = copy.deepcopy(SCHEDULE)
    changed["people"]["items"][1]["description"] = "Night nurse"
    case = _case(
        **{
            "assert": [{"path": "people.items[?id=P2].description", "equals": "Night nurse"}],
            "changes": ["people.items"],
        }
    )

    assert grade(load_cases(_write(tmp_path, case))[0], RunOutcome(proposed=changed, initial=SCHEDULE)).passed


def test_unchanged_assertion_uses_the_input_fixture(tmp_path: Path):
    case = load_cases(
        _write(
            tmp_path,
            _case(
                **{
                    "assert": [{"path": "people.items[?id=P1].description", "unchanged": True}],
                    "changes": ["people.items"],
                },
            ),
        )
    )[0]
    assert grade(case, RunOutcome(proposed=SCHEDULE, initial=SCHEDULE)).passed
    changed = copy.deepcopy(SCHEDULE)
    changed["people"]["items"][0]["description"] = "Changed"
    assert not grade(case, RunOutcome(proposed=changed, initial=SCHEDULE)).passed


def test_a_sibling_of_an_allowed_path_is_still_guarded(tmp_path: Path):
    changed = copy.deepcopy(SCHEDULE)
    changed["people"]["items"][1]["description"] = "Night nurse"
    changed["people"]["groups"][0]["members"] = ["P1", "P2"]
    case = _case(
        **{
            "assert": [{"path": "people.items[?id=P2].description", "equals": "Night nurse"}],
            "changes": ["people.items"],
        }
    )

    result = grade(load_cases(_write(tmp_path, case))[0], RunOutcome(proposed=changed, initial=SCHEDULE))

    assert not result.passed
    assert "people.groups" in result.failures()[0].detail


def test_a_missing_proposal_fails_an_edit_case(tmp_path: Path):
    case = _case(**{"assert": [{"path": "description", "equals": "Ward A"}], "changes": ["description"]})

    result = grade(load_cases(_write(tmp_path, case))[0], RunOutcome(proposed=None, initial=SCHEDULE))

    assert not result.passed


def test_an_unexpected_proposal_fails_a_question_case(tmp_path: Path):
    case = _case(expect_proposal=False, answer_contains=["2"])

    result = grade(
        load_cases(_write(tmp_path, case))[0],
        RunOutcome(answer="There are 2 people.", proposed=SCHEDULE, initial=SCHEDULE),
    )

    assert not result.passed


def test_answer_values_come_from_the_fixture(tmp_path: Path):
    case = _case(expect_proposal=False, answer_contains=["{people_count} people"])
    loaded = load_cases(_write(tmp_path, case))[0]

    values = computed_values(SCHEDULE)
    passing = grade(loaded, RunOutcome(answer="There are 2 people here."), values)
    failing = grade(loaded, RunOutcome(answer="There are 9 people here."), values)

    assert values["people_count"] == 2
    assert passing.passed
    assert not failing.passed


def test_unknown_person_refusal_accepts_contracted_does_not_exist():
    case = next(case for case in load_cases(CASES_PATH) if case.id == "reject-unknown-person")

    result = grade(case, RunOutcome(answer="P999 doesn't exist, so I made no change."))

    assert result.passed


def test_optional_tool_usage_grades_required_forbidden_and_bounded_calls(tmp_path: Path):
    case = _case(
        expect_proposal=False,
        tool_usage={
            "required": ["edit"],
            "forbidden": ["write"],
            "max_total": 2,
            "max_per_tool": {"edit": 1},
        },
    )
    loaded = load_cases(_write(tmp_path, case))[0]
    passing = RunOutcome(
        activity=[
            {"kind": "tool", "name": "read", "ok": True},
            {"kind": "tool", "name": "edit", "ok": True},
        ]
    )
    failing = RunOutcome(
        activity=[
            {"kind": "tool", "name": "edit", "ok": False},
            {"kind": "tool", "name": "edit", "ok": True},
            {"kind": "tool", "name": "write", "ok": True},
        ]
    )

    assert grade(loaded, passing).passed
    result = grade(loaded, failing)
    assert not result.passed
    descriptions = {check.description: check for check in result.checks}
    assert descriptions["does not use write tool"].detail == "used 1 time(s)"
    assert descriptions["uses at most 2 tool call(s)"].detail == "used 3"
    assert descriptions["uses edit at most 1 time(s)"].detail == "used 2"


def test_a_failed_required_tool_does_not_count_as_successful_use(tmp_path: Path):
    case = _case(expect_proposal=False, tool_usage={"required": ["read"]})
    loaded = load_cases(_write(tmp_path, case))[0]

    result = grade(loaded, RunOutcome(activity=[{"kind": "tool", "name": "read", "ok": False}]))

    assert not result.passed
    assert result.failures()[0].description == "uses successful read tool"


def test_validation_error_limit_distinguishes_repair_from_other_tool_errors(tmp_path: Path):
    case = load_cases(_write(tmp_path, _case(expect_proposal=False, tool_usage={"max_validation_errors": 0})))[0]
    prefix = "Trusted schedule check after this command:"
    unrelated = [
        {"kind": "tool", "name": "optimizer", "ok": False, "result": "API unavailable"},
        {"kind": "tool", "name": "read", "ok": False, "result": "File missing"},
        {"kind": "tool", "name": "edit", "ok": True, "result": prefix + "\nCandidate passed."},
        {
            "kind": "tool",
            "name": "bash",
            "ok": False,
            "result": "Command exited with code 1\n"
            + prefix
            + "\nThe candidate passed trusted server-side validation.",
        },
        {
            "kind": "tool",
            "name": "bash",
            "ok": False,
            "result": "Command exited with code 1\n" + prefix + "\nschedule.yaml is unchanged.",
        },
    ]
    assert grade(case, RunOutcome(activity=unrelated)).passed
    repaired = unrelated + [
        {"kind": "tool", "name": "edit", "ok": False, "result": prefix + "\nUnsupported expression: x = 3"},
        {"kind": "tool", "name": "edit", "ok": True, "result": prefix + "\nCandidate passed."},
    ]
    result = grade(case, RunOutcome(activity=repaired))
    assert not result.passed
    assert result.failures()[0].detail == "observed 1"


@pytest.mark.parametrize(
    ("tool_usage", "message"),
    [
        ("read", "must be an object"),
        ({"unknown": []}, "unknown fields"),
        ({"required": "read"}, "must be a list"),
        ({"required": ["read", "read"]}, "repeats a tool name"),
        ({"required": ["read"], "forbidden": ["read"]}, "requires and forbids"),
        ({"max_total": -1}, "must be a non-negative integer"),
        ({"max_validation_errors": True}, "must be a non-negative integer"),
        ({"max_validation_errors": -1}, "must be a non-negative integer"),
        ({"max_per_tool": {"read": True}}, "must map tool names"),
    ],
)
def test_invalid_tool_usage_is_rejected(tmp_path: Path, tool_usage: object, message: str):
    with pytest.raises(EvalCaseError, match=message):
        load_cases(_write(tmp_path, _case(expect_proposal=False, tool_usage=tool_usage)))


def test_required_tool_call_checks_successful_json_arguments(tmp_path: Path):
    case = load_cases(
        _write(
            tmp_path,
            _case(
                expect_proposal=False,
                tool_usage={"required_calls": [{"name": "optimizer", "arguments": {"action": "start"}}]},
            ),
        )
    )[0]
    activity = [{"kind": "tool", "name": "optimizer", "ok": True, "arguments": '{"action":"status"}'}]
    assert not grade(case, RunOutcome(activity=activity)).passed
    activity[0]["arguments"] = '{"action":"start","timeout_seconds":300}'
    assert grade(case, RunOutcome(activity=activity)).passed
    activity[0]["ok"] = False
    assert not grade(case, RunOutcome(activity=activity)).passed


@pytest.mark.parametrize(
    ("entry", "message"),
    [
        ({"id": "a", "fixture": "f", "question": "q"}, "missing `expect_proposal`"),
        (_case(**{"assert": []}), "asserts nothing"),
        (_case(**{"assert": [{"path": "description", "equals": "x"}]}), "names no part it may change"),
        (_case(expect_proposal=False, **{"assert": [{"path": "description", "equals": "x"}]}), "can never run"),
        (_case(**{"assert": [{"path": "description"}]}), "exactly one of"),
        (_case(**{"assert": [{"path": "description", "equals": "x", "count": 1}]}), "exactly one of"),
    ],
)
def test_an_ungradable_case_is_rejected(tmp_path: Path, entry: dict, message: str):
    with pytest.raises(EvalCaseError, match=message):
        load_cases(_write(tmp_path, entry))


def test_loads_multi_turn_cases_and_tags(tmp_path: Path):
    entry = _case(
        user_turns=["Expand the range.", "Yes."],
        intermediate_answer_contains=[["Taiwan", ["holiday", "holidays"]]],
        tags=["difficult", "tuning"],
        **{"assert": [{"path": "dates.range.endDate", "equals": "2026-03-14"}]},
        changes=["dates.range"],
    )

    case = load_cases(_write(tmp_path, entry))[0]

    assert case.user_turns == ("Expand the range.", "Yes.")
    assert case.intermediate_answer_contains == (("Taiwan", ("holiday", "holidays")),)
    assert case.tags == ("difficult", "tuning")


@pytest.mark.parametrize(
    "intermediate_answer_contains",
    [
        ["Taiwan"],
        [[1]],
        [[""]],
        [[[]]],
        [[["holiday", 1]]],
    ],
)
def test_rejects_invalid_intermediate_answer_expectations(tmp_path: Path, intermediate_answer_contains: object):
    entry = _case(
        user_turns=["Expand the range.", "Yes."],
        intermediate_answer_contains=intermediate_answer_contains,
        **{"assert": [{"path": "dates.range.endDate", "equals": "2026-03-14"}]},
        changes=["dates.range"],
    )

    with pytest.raises(EvalCaseError, match="invalid `intermediate_answer_contains`"):
        load_cases(_write(tmp_path, entry))


def test_loads_nested_dataset_and_category_path(tmp_path: Path):
    case_path = tmp_path / "basics" / "03-structure" / "case.json"
    case_path.parent.mkdir(parents=True)
    case_path.write_text(json.dumps(_case(expect_proposal=False)), encoding="utf-8")

    case = load_cases(tmp_path)[0]

    assert case.category == "basics/03-structure"


def test_a_multi_turn_case_can_designate_an_earlier_proposal(tmp_path: Path):
    entry = _case(
        user_turns=["Change it.", "What changed?"],
        proposal_turn=1,
        **{"assert": [{"path": "description", "equals": "changed"}]},
        changes=["description"],
    )
    case = load_cases(_write(tmp_path, entry))[0]
    proposed = copy.deepcopy(SCHEDULE)
    proposed["description"] = "changed"

    result = grade(
        case,
        RunOutcome(proposed=proposed, initial=SCHEDULE, proposal_turns=[True, False]),
    )

    assert case.proposal_turn == 1
    assert result.passed


def test_loads_multiple_proposal_turns_and_lifecycle_actions(tmp_path: Path):
    entry = _case(
        user_turns=["Change it.", "Revise it.", "Done?"],
        proposal_turns=[1, 2],
        turn_actions=[{"after_turn": 2, "action": "approve"}],
        **{"assert": [{"path": "description", "equals": "changed"}]},
        changes=["description"],
    )

    case = load_cases(_write(tmp_path, entry))[0]

    assert case.proposal_turns == (1, 2)
    assert case.proposal_turn == 2
    assert case.turn_actions[0].action == "approve"


def test_loads_external_schedule_update_action(tmp_path: Path):
    entry = _case(
        user_turns=["Change it.", "Continue."],
        turn_actions=[{"after_turn": 1, "action": "update", "schedule_patch": {"description": "External"}}],
        **{"assert": [{"path": "description", "equals": "changed"}]},
        changes=["description"],
    )

    case = load_cases(_write(tmp_path, entry))[0]

    assert case.turn_actions[0].schedule_patch == (("description", "External"),)


@pytest.mark.parametrize("proposal_turn", [0, 3, True, "1"])
def test_invalid_proposal_turn_is_rejected(tmp_path: Path, proposal_turn: object):
    entry = _case(
        user_turns=["Change it.", "Okay."],
        proposal_turn=proposal_turn,
        **{"assert": [{"path": "description", "equals": "changed"}]},
        changes=["description"],
    )

    with pytest.raises(EvalCaseError, match="must identify user turns"):
        load_cases(_write(tmp_path, entry))


@pytest.mark.parametrize(
    "overrides",
    [
        {"proposal_turn": 1, "proposal_turns": [1]},
        {"proposal_turns": [2, 1]},
        {"proposal_turns": [1, 1]},
        {"turn_actions": "approve"},
        {"turn_actions": [{"after_turn": 2, "action": "approve"}]},
        {"turn_actions": [{"after_turn": 1, "action": "update"}]},
    ],
)
def test_invalid_lifecycle_configuration_is_rejected(tmp_path: Path, overrides: dict):
    entry = _case(
        user_turns=["Change it.", "Continue."],
        **{"assert": [{"path": "description", "equals": "changed"}]},
        changes=["description"],
        **overrides,
    )

    with pytest.raises(EvalCaseError):
        load_cases(_write(tmp_path, entry))


def test_a_file_name_that_disagrees_with_its_case_id_is_rejected(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    entry = _case(**{"assert": [{"path": "description", "equals": "x"}], "changes": ["description"]})
    (tmp_path / "another-name.json").write_text(json.dumps(entry), encoding="utf-8")

    with pytest.raises(EvalCaseError, match="holds case id"):
        load_cases(tmp_path)


@pytest.mark.parametrize("target", ["weight", "selector"])
def test_weight_notation_oracle_rejects_deleting_the_other_axis(target):
    case = next(case for case in load_cases(CASES_PATH) if case.id == f"weight-shorthand-exact-{target}")
    initial = FIXTURE_SCHEDULES["weight-units"]
    by_weight = copy.deepcopy(initial)
    by_weight["preferences"] = [p for p in initial["preferences"] if p.get("weight") != 11_000_000_000]
    by_selector = copy.deepcopy(initial)
    by_selector["preferences"] = [p for p in initial["preferences"] if p.get("person") != ["11b"]]
    correct, wrong = (by_weight, by_selector) if target == "weight" else (by_selector, by_weight)
    assert grade(case, RunOutcome(proposed=correct, initial=initial)).passed
    assert not grade(case, RunOutcome(proposed=wrong, initial=initial)).passed


def test_ambiguous_weight_case_rejects_guessing_and_wrong_clarified_target():
    case = next(case for case in load_cases(CASES_PATH) if case.id == "weight-shorthand-clarify-selector")
    initial = FIXTURE_SCHEDULES["weight-units"]
    correct = copy.deepcopy(initial)
    correct["preferences"] = [p for p in initial["preferences"] if p.get("weight") != 11_000_000_000]
    outcome = RunOutcome(
        initial=initial,
        proposed=correct,
        proposal_turns=[False, True],
        intermediate_answers=["Does 11b mean the numeric weight or the group selector?"],
    )
    assert grade(case, outcome).passed
    outcome.proposal_turns = [True, True]
    assert not grade(case, outcome).passed
    outcome.proposal_turns = [False, True]
    wrong = copy.deepcopy(initial)
    wrong["preferences"] = [p for p in initial["preferences"] if p.get("person") != ["11b"]]
    outcome.proposed = wrong
    assert not grade(case, outcome).passed


def test_the_dataset_only_uses_registered_fixtures():
    cases = load_cases(CASES_PATH)

    assert {case.fixture for case in cases} == set(FIXTURE_SCHEDULES)
    assert len(cases) == len({case.id for case in cases})


def test_new_schedule_fixture_matches_the_frontend_empty_state():
    assert FIXTURE_SCHEDULES["new-schedule"] == {
        "apiVersion": "alpha",
        "description": "",
        "dates": {"range": {}, "items": [], "groups": []},
        "people": {"items": [], "groups": []},
        "shiftTypes": {"items": [], "groups": []},
        "preferences": [],
    }


def test_every_case_is_stored_as_one_readable_file():
    files = sorted(CASES_PATH.rglob("*.json"))

    assert len(files) == len(load_cases(CASES_PATH))
    for file in files:
        text = file.read_text(encoding="utf-8")
        # Indented JSON keeps a change to one assertion out of the rest of the diff.
        assert text.startswith("{\n  "), f"{file.name} is not formatted"
        assert text.endswith("\n")


def test_every_dataset_path_and_placeholder_resolves_against_its_fixture():
    for case in load_cases(CASES_PATH):
        schedule = FIXTURE_SCHEDULES[case.fixture]
        values = computed_values(schedule)
        for assertion in case.assertions:
            resolve(schedule, assertion.path)
        for expected_diff in case.expected_diff:
            found = resolve(schedule, expected_diff.path)
            if not expected_diff.compares_value:
                assert len(found) == 1 and isinstance(found[0], list), f"{case.id} diff path must select one list"
        imported = (
            _load_yaml(load_attachment_fixtures([case.import_attachment])[0].data) if case.import_attachment else {}
        )
        for changed in case.changes:
            assert resolve(schedule, changed) or resolve(imported, changed) or changed == "export", (
                f"{case.id} may change a missing part {changed}"
            )
        for expected in case.answer_contains:
            options = [expected] if isinstance(expected, str) else list(expected)
            assert all(option.format(**values).strip() for option in options), f"{case.id} expects an empty value"


def test_no_edit_case_is_satisfied_by_a_proposal_that_changes_nothing():
    for case in load_cases(CASES_PATH):
        if not case.expect_proposal:
            continue
        schedule = FIXTURE_SCHEDULES[case.fixture]
        outcome = RunOutcome(proposed=copy.deepcopy(schedule), initial=schedule)
        assert not grade(case, outcome, computed_values(schedule)).passed, f"{case.id} asserts nothing"


def test_the_dataset_covers_every_preference_type():
    covered = {kind for case in load_cases(CASES_PATH) for kind in covered_preference_types(case)}

    assert covered == {
        "at most one shift per day",
        "shift request",
        "shift type successions",
        "shift type requirement",
        "shift count",
        "shift affinity",
    }


def test_the_dataset_covers_every_editable_section():
    covered = {path for case in load_cases(CASES_PATH) for path in covered_paths(case)}

    for section in (
        "description",
        "dates.range",
        "dates.groups[].members",
        "people.items[].id",
        "people.items[].history",
        "people.groups[].members",
        "shiftTypes.items[].id",
        "shiftTypes.groups[].members",
        "export.formatting[].people",
        "export.extraColumns",
        "export.extraRows",
    ):
        assert section in covered, f"{section} is not covered"


def test_the_dataset_has_a_focused_case_for_every_exposed_tool():
    required_tools = {
        name for case in load_cases(CASES_PATH) if case.tool_usage is not None for name in case.tool_usage.required
    }

    assert required_tools == {READ_TOOL, BASH_TOOL, EDIT_TOOL, WRITE_TOOL}


def test_every_case_sits_in_a_category_directory():
    cases = load_cases(CASES_PATH)

    assert {case.category for case in cases} == {
        "basics/00-tools",
        "basics/00-summary",
        "basics/01-reading",
        "basics/02-basic-edit",
        "basics/03-structure",
        "basics/04-preferences",
        "basics/05-export",
        "basics/06-refusal",
        "basics/07-multi-turn",
        "basics/08-proposal-lifecycle",
        "basics/09-holdout",
        "basics/10-app-ui",
        "basics/11-attachments",
        "basics/12-optimizer-results",
        "basics/13-weight-notation",
        "basics/14-attachment-inspection",
    }
    assert all(
        not case.expect_proposal for case in cases if case.category.endswith(("00-summary", "01-reading", "06-refusal"))
    )
    assert all(
        case.expect_proposal
        for case in cases
        if case.category.removeprefix("basics/").startswith(("02", "03", "04", "05"))
    )


def test_every_attachment_fixture_name_is_known():
    known = attachment_fixture_names()

    for case in load_cases(CASES_PATH):
        assert set(case.attachments) <= known, f"{case.id} names an unknown attachment fixture"


def test_reading_questions_cannot_be_answered_from_the_prompt_summary():
    """A summary-answerable question measures copying, not reading."""
    summaries = {
        "cross-year-unit": describe_schedule(CROSS_YEAR_UNIT_PATH.read_text(encoding="utf-8")),
        "new-schedule": describe_schedule(NEW_SCHEDULE_PATH.read_text(encoding="utf-8")),
        "small-clinic": describe_schedule(SMALL_CLINIC_PATH.read_text(encoding="utf-8")),
        "ward87": describe_schedule(WARD_PATH.read_text(encoding="utf-8")),
    }

    for case in load_cases(CASES_PATH):
        if case.optimizer_completion:
            continue
        if not case.answer_contains:
            continue
        values = computed_values(FIXTURE_SCHEDULES[case.fixture])
        # A value may be offered in several wordings, so one of them counts.
        expected = [
            [option.format(**values) for option in ([value] if isinstance(value, str) else value)]
            for value in case.answer_contains
        ]
        in_summary = [options for options in expected if any(o in summaries[case.fixture] for o in options)]
        assert len(in_summary) < len(expected), f"{case.id} is answerable from the summary alone"


def test_every_membership_check_also_pins_the_collection_size():
    """A `contains` without a size passes when extra entries are added too."""
    for case in load_cases(CASES_PATH):
        schedule = FIXTURE_SCHEDULES[case.fixture]
        sized = {a.path for a in case.assertions if a.kind in {"count", "delta", "added", "removed"}}
        for assertion in case.assertions:
            if assertion.kind != "contains" or assertion.path in sized:
                continue
            found = resolve(schedule, assertion.path)
            # Text fields are exempt, because `contains` means substring there.
            assert found and not isinstance(found[0], list), (
                f"{case.id} checks membership of {assertion.path} without pinning its size"
            )


def _references(schedule: dict, token: str) -> set[str]:
    """Name every container that holds this token, outside its own entry."""
    found: set[str] = set()
    for section in ("people", "shiftTypes", "dates"):
        for group in schedule.get(section, {}).get("groups", []):
            if token in group.get("members", []):
                found.add(f"{section}.groups")
    for preference in schedule.get("preferences", []):
        if any(isinstance(value, list) and token in value for value in preference.values()):
            found.add("preferences")
    for person in schedule.get("people", {}).get("items", []):
        if token in (person.get("history") or []):
            found.add("people.items")
    return found


def test_every_removal_case_asserts_the_references_it_orphans():
    """Removing an entry that other parts still name must clear those names."""
    for case in load_cases(CASES_PATH):
        removed = [value for assertion in case.assertions if assertion.kind == "removed" for value in assertion.value]
        for token in removed:
            for container in _references(FIXTURE_SCHEDULES[case.fixture], token):
                assert any(assertion.path.startswith(container) for assertion in case.assertions), (
                    f"{case.id} removes {token} but says nothing about {container}"
                )


@pytest.mark.parametrize(
    "privacy",
    [
        "Anonymize YAML is a separate download. Browser data remains unchanged. Free-text descriptions remain unchanged.",
        "Anonymize YAML doesn't modify your current roster. It does not scrub personal names from free-text descriptions.",
        "Anonymize YAML leaves local data intact. Descriptions are preserved as-is.",
        "Anonymize YAML does **not** change the schedule data in your browser. Free-text descriptions remain unchanged.",
    ],
)
def test_restore_anonymization_case_accepts_equivalent_explanations(privacy):
    case = next(case for case in load_cases(CASES_PATH) if case.id == "guide-restore-and-anonymize")
    answer = (
        "Upload merges or replaces? In Save and Load, Download a YAML backup. Upload replaces the current schedule. "
        "Review the version warning and confirm, or cancel to keep the roster. "
        "Undo with Ctrl+Z or Cmd+Z. " + privacy
    )
    assert grade(case, RunOutcome(answer=answer)).passed


@pytest.mark.parametrize(
    "wrong_fact",
    [
        "Upload merges the older YAML into the current schedule.",
        "Browser data is changed by anonymization.",
        "Free-text descriptions are anonymized and personal names are removed.",
        "You cannot undo an upload.",
    ],
)
def test_restore_anonymization_case_rejects_wrong_or_missing_fact(wrong_fact):
    case = next(case for case in load_cases(CASES_PATH) if case.id == "guide-restore-and-anonymize")
    parts = [
        "In Save and Load, Download a YAML backup.",
        "Upload replaces the current schedule.",
        "Review the version warning and confirm, or cancel to keep the roster.",
        "Undo with Ctrl+Z or Cmd+Z.",
        "Anonymize YAML is a separate download.",
        "Browser data remains unchanged.",
        "Free-text descriptions remain unchanged.",
    ]
    index = {"Upload": 1, "Browser": 5, "Free-text": 6, "You": 3}[wrong_fact.split()[0]]
    parts[index] = wrong_fact
    assert not grade(case, RunOutcome(answer=" ".join(parts))).passed


def test_restore_case_question_heading_cannot_replace_an_actual_replacement_explanation():
    case = next(case for case in load_cases(CASES_PATH) if case.id == "guide-restore-and-anonymize")
    answer = (
        "Upload merges or replaces? The current schedule will be merged. "
        "Use Save and Load, Download for backup, and confirm the version warning or cancel. "
        "Undo with Ctrl+Z or Cmd+Z. Anonymize YAML leaves browser data unchanged. "
        "Free-text descriptions remain unchanged."
    )
    assert not grade(case, RunOutcome(answer=answer)).passed


@pytest.mark.parametrize("mutation", [None, "target", "operator", "existing-rule", "validation-repair"])
def test_count_batch_case_checks_semantics_and_validation_trajectory(mutation):
    case = next(case for case in load_cases(CASES_PATH) if case.id == "pref-count-batch-first-valid")
    original = FIXTURE_SCHEDULES[case.fixture]
    proposed = copy.deepcopy(original)
    additions = copy.deepcopy(list(case.expected_diff[0].added))
    for preference in additions:
        preference["countShiftTypes"].reverse()
        preference["countShiftTypeCoefficients"].reverse()
    proposed["preferences"].extend(additions)
    activity = []
    if mutation == "target":
        proposed["preferences"][-1]["target"] = 3
    elif mutation == "operator":
        proposed["preferences"][-1]["expression"] = "x <= T"
    elif mutation == "existing-rule":
        proposed["preferences"].pop(0)
    elif mutation == "validation-repair":
        activity = [
            {
                "kind": "tool",
                "name": "edit",
                "ok": False,
                "result": "Trusted schedule check after this command:\nUnsupported expression: x = 3",
            }
        ]
    result = grade(case, RunOutcome(initial=original, proposed=proposed, activity=activity))
    assert result.passed == (mutation is None)


@pytest.mark.parametrize(
    "files,expected",
    [
        ({}, False),
        ({"sample.csv": "wrong"}, False),
        ({"sample.csv": hashlib.sha256(b"name,date\n").hexdigest()}, True),
    ],
    ids=["missing", "wrong-bytes", "exact-bytes"],
)
def test_download_grader_requires_captured_file_bytes(files, expected):
    case = EvalCase(
        id="zip",
        fixture="small-clinic",
        question="Download",
        expect_proposal=False,
        download_files={"sample.csv": "name,date\n"},
    )
    result = grade(
        case, RunOutcome(answer="Download /workspace/download.zip", activity=[{"kind": "download", "files": files}]), {}
    )
    assert result.passed is expected


@pytest.mark.parametrize("drop_rule", [False, True], ids=["exact-upload", "missing-rule"])
def test_import_grader_checks_every_uploaded_rule(drop_rule):
    case = next(case for case in load_cases(CASES_PATH) if case.id == "import-complete-uploaded-yaml")
    proposed = _load_yaml(load_attachment_fixtures([case.import_attachment])[0].data)
    if drop_rule:
        proposed["preferences"].pop()
    result = grade(case, RunOutcome(initial=FIXTURE_SCHEDULES[case.fixture], proposed=proposed))
    assert result.passed is not drop_rule
