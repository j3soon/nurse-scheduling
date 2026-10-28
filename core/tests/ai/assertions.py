"""Check turn events and exact schedule changes."""

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

from copy import deepcopy
from difflib import unified_diff
from typing import Any

from nurse_scheduling.ai.optimizer import OPTIMIZER_TOOL

from .schema import Step, load_yaml


def _partial(expected: Any, observed: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(observed, dict) and all(
            key in observed and _partial(value, observed[key]) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(observed, list)
            and len(expected) == len(observed)
            and all(_partial(left, right) for left, right in zip(expected, observed, strict=True))
        )
    return type(expected) is type(observed) and expected == observed


def check_event(step: Step, events: list[dict], cursor: int) -> int:
    """Consume the next matching event, allowing unrelated events in between."""
    if step.kind == "optimizer":
        calls = [event for event in events if event["kind"] == "tool" and event["name"] == OPTIMIZER_TOOL]
        if calls:
            raise AssertionError(
                f"step {step.number}: expected no optimizer calls during this turn; observed {calls!r}"
            )
        return cursor
    for index in range(cursor, len(events)):
        event = events[index]
        if event["kind"] == "assistant" and (
            event.get("stop_reason") in {"error", "aborted", "length"} or event.get("context_omitted")
        ):
            continue
        if step.kind == "tool":
            matched = (
                event["kind"] == "tool" and event["name"] == step.value and _partial(step.options, event["arguments"])
            )
        else:
            expected = step.value.get("contains_any")
            text = event.get("text", "")
            if expected is not None and not step.value.get("case_sensitive", False):
                text, expected = text.casefold(), [part.casefold() for part in expected]
            matched = event["kind"] == "assistant" and (
                any(part in text for part in expected) if expected is not None else bool(text.strip())
            )
        if matched:
            return index + 1
    observed = repr([event for event in events[cursor:] if event["kind"] in {"tool", "assistant"}])
    if len(observed) > 1500:
        observed = observed[:1500] + "... (full events in evidence)"
    raise AssertionError(
        f"step {step.number}: expected {step.kind} {step.value!r} {step.options!r} after event {cursor}; observed {observed}"
    )


def _normalize_person_defaults(person: Any) -> Any:
    if not isinstance(person, dict):
        return person
    person = dict(person)
    if person.get("history") is None or person.get("history") == []:
        person.pop("history", None)
    if person.get("description") is None or person.get("description") == "":
        person.pop("description", None)
    return person


def _normalize_schedule_defaults(schedule: Any) -> Any:
    schedule = deepcopy(schedule)
    people = schedule.get("people") if isinstance(schedule, dict) else None
    if isinstance(people, dict) and isinstance(people.get("items"), list):
        people["items"] = [_normalize_person_defaults(person) for person in people["items"]]
    return schedule


def _normalize_fixture_defaults(schedule: Any) -> Any:
    """Compare optional empty fields as the frontend's defaults."""
    if not isinstance(schedule, dict):
        return schedule
    schedule.pop("appVersion", None)
    if schedule.get("description") in (None, ""):
        schedule.pop("description", None)
    for name in ("dates", "people", "shiftTypes", "export"):
        container = schedule.get(name)
        if not isinstance(container, dict):
            continue
        keys = {"export": ("formatting", "extraColumns", "extraRows"), "dates": ("items", "groups")}.get(
            name, ("groups",)
        )
        for key in keys:
            if container.get(key) == []:
                container.pop(key)
        if name == "export" and not container:
            schedule.pop(name)
    return schedule


def check_schedule(steps: list[Step], before: str, after: str) -> None:
    """Require a fixture, or remove declared additions and compare with the original."""
    if any(step.value.get("allow_changes") is True for step in steps):
        return
    expected = next((step.value["equals"] for step in steps if "equals" in step.value), None)
    if expected is not None:
        before = expected.read_text(encoding="utf-8")
    original = _normalize_schedule_defaults(load_yaml(before))
    remaining = _normalize_schedule_defaults(load_yaml(after))
    if expected is not None:
        original = _normalize_fixture_defaults(original)
        remaining = _normalize_fixture_defaults(remaining)
    for step in steps:
        for path, objects in step.value.get("added", {}).items():
            target = remaining
            try:
                for key in path.split("."):
                    target = target[key]
                if not isinstance(target, list):
                    raise TypeError
                for item in objects:
                    if path == "people.items":
                        item = _normalize_person_defaults(item)
                    index = next(
                        (i for i, actual in enumerate(target) if _partial(item, actual) and _partial(actual, item)),
                        None,
                    )
                    if index is None:
                        raise AssertionError(
                            f"step {step.number}: missing exact added object at {path}: {item!r}; observed {target!r}"
                        )
                    target.pop(index)
            except (KeyError, TypeError) as error:
                raise AssertionError(f"step {step.number}: expected a schedule list at {path}") from error
    if not _partial(original, remaining) or not _partial(remaining, original):
        diff = "".join(
            unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile="expected" if expected else "before",
                tofile="after",
            )
        )
        message = (
            f"schedule does not equal fixture {expected}"
            if expected
            else "unexpected schedule changes beyond declared additions (unchanged is the default)"
        )
        raise AssertionError(f"{message}:\n{diff}")
