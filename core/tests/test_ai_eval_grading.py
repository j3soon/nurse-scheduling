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
import json
from pathlib import Path

import pytest

from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.pi.edit import EDIT_TOOL
from nurse_scheduling.ai.pi.read import READ_TOOL
from nurse_scheduling.ai.pi.write import WRITE_TOOL
from nurse_scheduling.ai.schedule_context import describe_schedule
from nurse_scheduling.loader import _load_yaml

from .ai_eval.grading import (
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


def test_resolves_fields_indexes_and_selectors():
    assert resolve(SCHEDULE, "dates.range.startDate") == ["2026-03-01"]
    assert resolve(SCHEDULE, "people.items[0].id") == ["P1"]
    assert resolve(SCHEDULE, "people.items[?id=P1].description") == ["Head nurse"]
    assert resolve(SCHEDULE, "people.items[?id=P9]") == []


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


@pytest.mark.parametrize(
    ("tool_usage", "message"),
    [
        ("read", "must be an object"),
        ({"unknown": []}, "unknown fields"),
        ({"required": "read"}, "must be a list"),
        ({"required": ["read", "read"]}, "repeats a tool name"),
        ({"required": ["read"], "forbidden": ["read"]}, "requires and forbids"),
        ({"max_total": -1}, "must be a non-negative integer"),
        ({"max_per_tool": {"read": True}}, "must map tool names"),
    ],
)
def test_invalid_tool_usage_is_rejected(tmp_path: Path, tool_usage: object, message: str):
    with pytest.raises(EvalCaseError, match=message):
        load_cases(_write(tmp_path, _case(expect_proposal=False, tool_usage=tool_usage)))


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


def test_the_dataset_only_uses_registered_fixtures():
    cases = load_cases(CASES_PATH)

    assert {case.fixture for case in cases} == {"cross-year-unit", "new-schedule", "small-clinic", "ward87"}
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
        for changed in case.changes:
            assert resolve(schedule, changed) or changed == "export", f"{case.id} may change a missing part {changed}"
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
    }
    assert all(
        not case.expect_proposal for case in cases if case.category.endswith(("00-summary", "01-reading", "06-refusal"))
    )
    assert all(
        case.expect_proposal
        for case in cases
        if case.category.removeprefix("basics/").startswith(("02", "03", "04", "05"))
    )


def test_reading_questions_cannot_be_answered_from_the_prompt_summary():
    """A summary-answerable question measures copying, not reading."""
    summaries = {
        "cross-year-unit": describe_schedule(CROSS_YEAR_UNIT_PATH.read_text(encoding="utf-8")),
        "new-schedule": describe_schedule(NEW_SCHEDULE_PATH.read_text(encoding="utf-8")),
        "small-clinic": describe_schedule(SMALL_CLINIC_PATH.read_text(encoding="utf-8")),
        "ward87": describe_schedule(WARD_PATH.read_text(encoding="utf-8")),
    }

    for case in load_cases(CASES_PATH):
        if not case.answer_contains:
            continue
        values = computed_values(FIXTURE_SCHEDULES[case.fixture])
        # A value may be offered in several wordings, so one of them counts.
        expected = [
            [option.format(**values) for option in ([value] if isinstance(value, str) else value)]
            for value in case.answer_contains
        ]
        in_summary = [options for options in expected if any(o in summaries[case.fixture] for o in options)]
        if case.category.endswith("00-summary"):
            assert len(in_summary) == len(expected), f"{case.id} is not answerable from the summary"
        else:
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
