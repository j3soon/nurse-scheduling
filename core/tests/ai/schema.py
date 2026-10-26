"""Parse the ordered, human-reviewed AI testcase format."""

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

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
TESTCASES = ROOT / "testcases"
KINDS = {"date", "yaml", "user", "tool", "assistant", "schedule"}


class DefinitionError(ValueError):
    """A testcase cannot run because its definition is invalid."""


@dataclass(frozen=True)
class Step:
    """One validated step, retaining its one-based source position."""

    number: int
    kind: str
    value: Any
    options: dict[str, Any]


@dataclass(frozen=True)
class Case:
    """One conversation with ordered configuration and assertions."""

    path: Path
    steps: tuple[Step, ...]


def load_yaml(text: str) -> Any:
    """Read UTF-8 YAML values without accepting duplicate mapping keys."""
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = False
    return yaml.load(text)


def fixture_path(name: Any, fixtures: Path = FIXTURES, *, root: Path | None = None) -> Path:
    """Resolve a fixture within its permitted root."""
    if not isinstance(name, str) or not name.strip():
        raise DefinitionError("fixture names must be nonempty strings")
    path = (fixtures / name).resolve()
    root = (root or fixtures).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise DefinitionError(f"fixture does not exist inside {root}: {name}")
    return path


def schedule_fixture(name: Any, fixtures: Path) -> Path:
    """Reuse schedule YAML within core/tests, keeping attachments in fixtures."""
    root = ROOT.parent if fixtures.resolve() == FIXTURES.resolve() else fixtures
    path = fixture_path(name, fixtures, root=root)
    if not isinstance(load_yaml(path.read_text(encoding="utf-8")), dict):
        raise DefinitionError("schedule fixture must contain a YAML mapping")
    return path


def _strings(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        raise DefinitionError(f"{label} must be a nonempty list of nonempty strings")


def _schedule(value: Any, fixtures: Path) -> None:
    if not isinstance(value, dict) or len(value) != 1:
        raise DefinitionError("schedule requires exactly one of unchanged, added, or equals")
    if "unchanged" in value:
        if value["unchanged"] is not True:
            raise DefinitionError("schedule.unchanged must be true")
    elif "equals" in value:
        value["equals"] = schedule_fixture(value["equals"], fixtures)
    elif "added" in value:
        added = value["added"]
        if not isinstance(added, dict) or not added:
            raise DefinitionError("schedule.added must map dotted list paths to objects")
        for path, objects in added.items():
            if not isinstance(path, str) or any(not part for part in path.split(".")):
                raise DefinitionError("schedule.added paths must contain nonempty dotted mapping keys")
            if (
                not isinstance(objects, list)
                or not objects
                or any(not isinstance(item, dict) or not item for item in objects)
            ):
                raise DefinitionError(f"schedule.added.{path} must be a nonempty list of nonempty objects")
    else:
        raise DefinitionError("unknown schedule assertion")


def _step(number: int, raw: Any, fixtures: Path) -> Step:
    if not isinstance(raw, dict) or len(KINDS.intersection(raw)) != 1:
        raise DefinitionError("each step requires exactly one of date, yaml, user, tool, assistant, schedule")
    kind = next(iter(KINDS.intersection(raw)))
    value = raw[kind]
    options = {key: item for key, item in raw.items() if key != kind}
    if kind != "tool" and set(options) - ({"attachment"} if kind == "user" else set()):
        raise DefinitionError(f"unexpected fields for {kind}: {list(options)}")
    if kind == "date":
        try:
            value = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        except (TypeError, ValueError) as error:
            raise DefinitionError("date must be an ISO 8601 datetime with a timezone") from error
        if value.utcoffset() is None:
            raise DefinitionError("date must include a timezone")
    elif kind == "yaml":
        value = schedule_fixture(value, fixtures)
    elif kind in {"user", "tool"}:
        if not isinstance(value, str) or not value.strip():
            raise DefinitionError(f"{kind} must be a nonempty string")
        if kind == "user" and "attachment" in options:
            names = options["attachment"]
            names = [names] if isinstance(names, str) else names
            _strings(names, "attachment")
            options["attachment"] = tuple(fixture_path(name, fixtures) for name in names)
    elif kind == "assistant":
        if (
            not isinstance(value, dict)
            or set(value) - {"contains_any", "case_sensitive", "judge", "count"}
            or not {"contains_any", "judge"}.intersection(value)
        ):
            raise DefinitionError("assistant requires contains_any, judge, or both")
        if "contains_any" in value:
            _strings(value["contains_any"], "contains_any")
        elif "case_sensitive" in value:
            raise DefinitionError("case_sensitive requires contains_any")
        if "case_sensitive" in value and type(value["case_sensitive"]) is not bool:
            raise DefinitionError("case_sensitive must be a boolean")
        if "judge" in value and (not isinstance(value["judge"], str) or not value["judge"].strip()):
            raise DefinitionError("assistant.judge must be a nonempty rubric string")
        if "count" in value:
            if "judge" not in value:
                raise DefinitionError("assistant.count requires judge")
            if value["count"] is not None and (type(value["count"]) is not int or value["count"] < 1):
                raise DefinitionError("assistant.count must be a positive integer or null")
    else:
        _schedule(value, fixtures)
    return Step(number, kind, value, options)


def load_case(path: Path, fixtures: Path = FIXTURES) -> Case:
    """Validate the complete definition before any provider is initialized."""
    number = 0
    try:
        raw = load_yaml(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or set(raw) != {"steps"} or not isinstance(raw["steps"], list) or not raw["steps"]:
            raise DefinitionError("testcase requires a nonempty steps list and no other top-level fields")
        steps = []
        has_user = False
        configured = False
        schedule_modes = set()
        schedule_count = 0
        for number, entry in enumerate(raw["steps"], start=1):
            step = _step(number, entry, fixtures)
            if step.kind == "user":
                has_user, configured = True, False
                schedule_modes = set()
                schedule_count = 0
            elif step.kind in {"date", "yaml"}:
                configured = True
            elif not has_user or configured:
                raise DefinitionError("assertions must follow a user turn before the next configuration step")
            elif step.kind == "schedule":
                schedule_modes.update(step.value)
                schedule_count += 1
                if len(schedule_modes) > 1 or (schedule_modes != {"added"} and schedule_count > 1):
                    raise DefinitionError(
                        "schedule.unchanged and schedule.equals cannot be combined with other schedule assertions"
                    )
            steps.append(step)
        if not has_user or steps[-1].kind in {"date", "yaml"}:
            raise DefinitionError("testcase must contain a user turn and cannot end with configuration")
        return Case(path.resolve(), tuple(steps))
    except (DefinitionError, YAMLError, OSError) as error:
        raise DefinitionError(f"{path}: step {number}: {error}") from error
