"""Tests for model-readable frontend schedule schema guidance."""

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

import inspect
from copy import deepcopy

import pytest
from pydantic import BaseModel

from nurse_scheduling import models
from nurse_scheduling.ai.pi.bash import DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES
from nurse_scheduling.ai.schema import (
    SCHEMA_PATHS,
    SCHEMA_REFERENCE_GROUPS,
    SCHEMA_TOPICS,
    render_schedule_reference,
)
from nurse_scheduling.ai.validation import validate_frontend_schedule_yaml
from nurse_scheduling.loader import _load_yaml

from .ai_test_helper import SCHEDULE_BYTE_LIMIT, base_schedule_payload, schedule_yaml

EXAMPLE_PATHS = tuple(path for path, topic in SCHEMA_TOPICS.items() if topic.example is not None)
MODEL_TOPIC_COVERAGE = {
    models.NurseSchedulingData: ("schedule",),
    models.DateContainer: ("dates",),
    models.DateRange: ("dates.range",),
    models.DateGroup: ("dates.groups",),
    models.PeopleContainer: ("people",),
    models.Person: ("people.items",),
    models.PeopleGroup: ("people.groups",),
    models.ShiftTypesContainer: ("shiftTypes",),
    models.ShiftType: ("shiftTypes.items",),
    models.ShiftTypeGroup: ("shiftTypes.groups",),
    models.MaxOneShiftPerDayPreference: ("preferences.at most one shift per day",),
    models.ShiftRequestPreference: ("preferences.shift request",),
    models.ShiftTypeSuccessionsPreference: ("preferences.shift type successions",),
    models.ShiftTypeRequirementsPreference: ("preferences.shift type requirement",),
    models.ShiftCountPreference: ("preferences.shift count",),
    models.ShiftAffinityPreference: ("preferences.shift affinity",),
    models.ExportConfig: ("export",),
    models.BaseExportFormattingRule: ("export.formatting",),
    models.ExportPersonFormattingRule: ("export.formatting", "export.formatting.row"),
    models.ExportDateFormattingRule: ("export.formatting", "export.formatting.column"),
    models.ExportHistoryHeaderFormattingRule: ("export.formatting", "export.formatting.history header"),
    models.ExportPreferenceCondition: ("export.formatting.condition.preference",),
    models.ExportFormattingCondition: ("export.formatting.condition",),
    models.ExportFormattingNote: ("export.formatting.note",),
    models.ExportCellFormattingRule: ("export.formatting", "export.formatting.cell"),
    models.ExportExtraColumn: ("export.extraColumns",),
    models.ExportExtraRow: ("export.extraRows",),
}
CANONICAL_FIELD_REQUIREMENTS = {
    "schedule": {
        "required": ("apiVersion", "dates", "people", "shiftTypes", "preferences"),
        "optional": ("appVersion", "description", "export"),
    },
    "dates": {"required": ("range",), "optional": ("items", "groups")},
    "dates.range": {"required": ("startDate", "endDate")},
    "dates.groups": {"required": ("id", "description", "members")},
    "people": {"required": ("items",), "optional": ("groups",)},
    "people.items": {"required": ("id", "description"), "optional": ("history",)},
    "people.groups": {"required": ("id", "description", "members")},
    "shiftTypes": {"required": ("items",), "optional": ("groups",)},
    "shiftTypes.items": {"required": ("id", "description")},
    "shiftTypes.groups": {"required": ("id", "description", "members")},
    "preferences.at most one shift per day": {"write": ("type",), "optional": ("description",)},
    "preferences.shift request": {
        "write": ("type",),
        "required": ("person", "date", "shiftType"),
        "optional": ("description", "weight"),
    },
    "preferences.shift type successions": {
        "write": ("type",),
        "required": ("person", "pattern", "date"),
        "optional": ("description", "weight"),
    },
    "preferences.shift type requirement": {
        "write": ("type",),
        "required": ("shiftType", "requiredNumPeople", "qualifiedPeople", "date"),
        "optional": ("description", "shiftTypeCoefficients", "preferredNumPeople", "weight"),
    },
    "preferences.shift count": {
        "write": ("type",),
        "required": ("person", "countDates", "countShiftTypes", "expression", "target"),
        "optional": ("description", "countShiftTypeCoefficients", "weight"),
    },
    "preferences.shift affinity": {
        "write": ("type",),
        "required": ("date", "people1", "people2", "shiftTypes"),
        "optional": ("description", "weight"),
    },
    "export": {"optional": ("formatting", "extraColumns", "extraRows")},
    "export.formatting": {
        "optional": ("description", "backgroundColor", "bottomBorderColor", "rightBorderColor", "fontColor")
    },
    "export.formatting.row": {"required": ("type", "people")},
    "export.formatting.people header": {"required": ("type", "people")},
    "export.formatting.history": {"required": ("type", "people")},
    "export.formatting.column": {"required": ("type", "dates")},
    "export.formatting.date header": {"required": ("type", "dates")},
    "export.formatting.history header": {"required": ("type",)},
    "export.formatting.cell": {
        "required": ("type", "people", "dates", "shiftTypes"),
        "optional": ("appendText", "note", "when"),
    },
    "export.formatting.condition": {"required": ("preference",)},
    "export.formatting.condition.preference": {
        "required": ("types",),
        "optional": ("requestShape", "satisfied", "weightRange"),
    },
    "export.formatting.note": {"required": ("text",)},
    "export.extraColumns": {
        "required": ("type", "header", "countShiftTypes", "countDates"),
        "optional": ("description", "rightBorderColor", "countShiftTypeCoefficients"),
    },
    "export.extraRows": {
        "required": ("type", "header", "countShiftTypes", "countPeople"),
        "optional": ("description", "bottomBorderColor"),
    },
}
FRONTEND_FLAT_LIST_FIELDS = {
    "dates.groups": ("members",),
    "people.items": ("history",),
    "people.groups": ("members",),
    "shiftTypes.groups": ("members",),
    "preferences.shift request": ("person", "date", "shiftType"),
    "preferences.shift type successions": ("person", "pattern", "date"),
    "preferences.shift type requirement": ("shiftType", "qualifiedPeople", "date"),
    "preferences.shift count": ("person", "countDates", "countShiftTypes"),
    "preferences.shift affinity": ("date", "people1", "people2", "shiftTypes"),
    "export.formatting.row": ("people",),
    "export.formatting.people header": ("people",),
    "export.formatting.history": ("people",),
    "export.formatting.column": ("dates",),
    "export.formatting.date header": ("dates",),
    "export.formatting.cell": ("people", "dates", "shiftTypes"),
    "export.extraColumns": ("countShiftTypes", "countDates"),
    "export.extraRows": ("countShiftTypes", "countPeople"),
}


def _field_guidance(path: str, field: str) -> str:
    return " ".join(item for item in SCHEMA_TOPICS[path].fields if f"`{field}`" in item)


def test_schema_paths_are_unique():
    assert len(SCHEMA_PATHS) == len(set(SCHEMA_PATHS))
    assert set(SCHEMA_PATHS) == set(SCHEMA_TOPICS)
    assert EXAMPLE_PATHS


def test_task_sized_references_cover_every_topic_once_and_fit_one_bash_result():
    grouped_paths = [path for paths in SCHEMA_REFERENCE_GROUPS.values() for path in paths]

    assert sorted(grouped_paths) == sorted(SCHEMA_PATHS)
    assert len(grouped_paths) == len(set(grouped_paths))
    for group, paths in SCHEMA_REFERENCE_GROUPS.items():
        reference = render_schedule_reference(group)
        assert reference is not None
        assert len(reference.encode("utf-8")) <= DEFAULT_MAX_BYTES
        assert len(reference.splitlines()) <= DEFAULT_MAX_LINES
        assert all(f"Path: {path}\n" in reference for path in paths)
        assert reference.count("Selector fidelity:") == 1


def test_export_reference_includes_common_fields_and_nested_condition_shape():
    reference = render_schedule_reference("export")

    assert reference is not None
    for field in ("backgroundColor", "bottomBorderColor", "rightBorderColor", "fontColor"):
        assert f"`{field}`" in reference
    assert "requestShape" in reference
    assert "satisfied: true" in reference
    assert "weightRange" in reference


def test_export_column_guidance_preserves_day_of_month_selector():
    topic = SCHEMA_TOPICS["export.formatting.column"]

    assert "day-of-month request" in " ".join(topic.rules)
    assert "quoted two-digit selector `01`" in " ".join(topic.rules)
    assert "dates: ['01']" in (topic.example or "")


def test_every_concrete_yaml_pydantic_model_is_mapped_to_reference_topics():
    yaml_models = {
        model
        for _, model in inspect.getmembers(models, inspect.isclass)
        if issubclass(model, BaseModel) and model.__module__ == models.__name__
    }

    assert yaml_models == {*MODEL_TOPIC_COVERAGE, models.BasePreference}


@pytest.mark.parametrize("model", MODEL_TOPIC_COVERAGE, ids=lambda model: model.__name__)
def test_reference_topics_name_every_authoritative_pydantic_field(model: type[BaseModel]):
    paths = MODEL_TOPIC_COVERAGE[model]
    guidance = " ".join(text for path in paths for text in (*SCHEMA_TOPICS[path].fields, *SCHEMA_TOPICS[path].rules))
    classified_fields = {
        field for path in paths for fields in CANONICAL_FIELD_REQUIREMENTS[path].values() for field in fields
    }

    assert all(f"`{field}`" in guidance for field in model.model_fields)
    assert classified_fields == model.model_fields.keys()


@pytest.mark.parametrize("path", CANONICAL_FIELD_REQUIREMENTS)
def test_reference_marks_every_canonical_field_required_or_optional(path: str):
    for status, fields in CANONICAL_FIELD_REQUIREMENTS[path].items():
        for field in fields:
            assert status in _field_guidance(path, field), f"{path}.{field} should be marked {status}"


@pytest.mark.parametrize(
    ("path", "field"),
    tuple((path, field) for path, fields in FRONTEND_FLAT_LIST_FIELDS.items() for field in fields),
)
def test_frontend_flat_list_restrictions_are_documented(path: str, field: str):
    assert "flat" in _field_guidance(path, field)


@pytest.mark.parametrize(
    "path", ("dates.groups", "people.items", "people.groups", "shiftTypes.items", "shiftTypes.groups")
)
def test_frontend_required_descriptions_are_documented(path: str):
    assert "required `description`" in _field_guidance(path, "description")


def test_frontend_singleton_and_scalar_restrictions_are_documented():
    shift_request = SCHEMA_TOPICS["preferences.shift request"]
    shift_count = SCHEMA_TOPICS["preferences.shift count"]

    assert "exactly one" in _field_guidance("preferences.shift request", "person")
    assert "exactly one" in _field_guidance("preferences.shift request", "shiftType")
    assert "scalar" in _field_guidance("preferences.shift count", "expression")
    assert "scalar" in _field_guidance("preferences.shift count", "target")
    assert shift_request.example is not None
    assert shift_count.example is not None


def test_schema_separates_the_two_counting_preferences():
    """Staffing per shift and shifts per person read alike until the schema says otherwise."""
    reference = render_schedule_reference("preferences")

    assert reference is not None
    assert "counts how many people a shift type needs on a date" in reference
    assert "counts how many shifts one person works across dates" in reference
    assert "number of people a shift type needs on a date" in reference
    assert "Do not express this as a `shift count` preference" in reference
    assert "Without `preferredNumPeople`, `requiredNumPeople` is an exact hard staffing count" in reference
    assert "requires a finite `weight`" in reference
    assert "not the people needed on a shift" in reference
    assert "use `shift type requirement` instead" in reference
    assert "map directly to `shiftType`, `requiredNumPeople`, `qualifiedPeople`, and `date`" in reference
    assert "Do not inspect unrelated shift requests or expand group members" in reference


def test_schema_documents_soft_affinity_default():
    reference = render_schedule_reference("preferences")

    assert reference is not None
    assert "omit `weight` to use the soft default 1" in reference
    assert "Do not infer a stronger weight from unrelated preferences" in reference
    assert "only when the user explicitly asks to require or forbid" in reference
    assert "does not require the two people to have identical schedules" in reference


def test_schema_documents_soft_shift_request_default():
    reference = render_schedule_reference("preferences")

    assert reference is not None
    assert "map directly to `person`, `date`, and `shiftType`" in reference
    assert "ordinary language such as wants or prefers" in reference
    assert "omit `weight` to use the soft default 1" in reference
    assert "Do not infer a stronger weight from unrelated requests" in reference
    assert "Use the user's exact weight when provided" in reference


def test_schema_guidance_preserves_selectors_and_defines_coefficient_pairs():
    core = render_schedule_reference("core")
    preferences = render_schedule_reference("preferences")
    export = render_schedule_reference("export")

    assert core is not None
    assert preferences is not None
    assert export is not None
    assert "Keep reserved selectors such as `ALL` literal" in core
    assert "shift type `D` is not group `Day`" in core
    assert "Quote a YAML string containing `: `" in core
    assert "[[D, 1], [N, 2]]" in preferences
    assert "not a mapping or a list of strings" in preferences
    assert "E followed by D is [E, D], not [Evening, Day]" in preferences
    assert "Use ALL to count every person" in export
    assert "countPeople: [ALL]" in export
    assert "same coordinated file edit" in core
    assert "every group membership" in core


def test_range_shrink_guidance_covers_date_scopes_in_one_search():
    reference = render_schedule_reference("core")

    assert reference is not None
    for field in (
        "`dates.groups[].members`",
        "preference `date` or `countDates`",
        "export formatting `dates`",
        "export extra-column `countDates`",
    ):
        assert field in reference
    assert "Search once with `rg`" in reference
    assert "Do not repeat that search by section" in reference
    assert "loses its entire date scope, delete that entry" in reference


@pytest.mark.parametrize("path", EXAMPLE_PATHS, ids=EXAMPLE_PATHS)
def test_every_returned_yaml_example_is_frontend_compatible(path: str):
    topic = SCHEMA_TOPICS[path]
    assert topic.example is not None
    fragment = _load_yaml(topic.example.encode("utf-8"))
    payload = deepcopy(base_schedule_payload())

    if "preferences" in fragment:
        preferences = fragment["preferences"]
        if path == "preferences.at most one shift per day":
            payload["preferences"] = preferences
        else:
            payload["preferences"] = [{"type": "at most one shift per day"}, *preferences]
    else:
        section = next(iter(fragment))
        payload[section].update(fragment[section])

    result = validate_frontend_schedule_yaml(schedule_yaml(payload), SCHEDULE_BYTE_LIMIT)

    assert result.valid, result.render()
