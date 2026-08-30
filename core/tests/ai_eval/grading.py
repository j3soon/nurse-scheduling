"""Verifiable success criteria for experimental AI evaluation cases."""

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
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Cases are graded on the schedule a run produced, not on the tool calls it made,
# so a correct answer reached a different way still passes.
_STEP = re.compile(r"\.?([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]|\[\?([^=\]]+)=([^\]]*)\]|(\[\])")
_ASSERTION_KINDS = ("equals", "one_of", "contains", "count", "delta", "added", "removed", "absent", "present")


class EvalCaseError(ValueError):
    """One case in the dataset is unusable."""


@dataclass(frozen=True)
class Assertion:
    """One check over the schedule a run produced."""

    path: str
    kind: str
    value: Any = None

    def describe(self) -> str:
        if self.kind in {"absent", "present"}:
            return f"{self.path} {self.kind}"
        return f"{self.path} {self.kind} {self.value!r}"


@dataclass(frozen=True)
class EvalCase:
    """One question with verifiable criteria for the schedule it should produce."""

    id: str
    fixture: str
    question: str
    expect_proposal: bool
    category: str = ""
    assertions: tuple[Assertion, ...] = ()
    changes: tuple[str, ...] = ()
    answer_contains: tuple[str | tuple[str, ...], ...] = ()
    note: str = ""


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one criterion."""

    description: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class CaseResult:
    """Every criterion applied to one run."""

    case_id: str
    checks: tuple[CheckResult, ...] = ()

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if not check.passed)


@dataclass
class RunOutcome:
    """What one evaluation run produced, independent of how it was obtained."""

    answer: str = ""
    proposed: Any = None
    initial: Any = None
    activity: list[dict[str, Any]] = field(default_factory=list)


def load_cases(path: Path) -> list[EvalCase]:
    """Read every case, from one directory of JSON files or from one file.

    A file per case keeps a change to one case out of every other case's diff,
    and makes the file name the case id. The directory holding a case names its
    category, which is what groups the cases a path cannot describe, such as a
    refusal.
    """
    files = sorted(path.rglob("*.json")) if path.is_dir() else [path]
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for file in files:
        try:
            entry = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise EvalCaseError(f"{file.name} is not valid JSON. {error}") from error
        case = _build_case(entry, file.name, file.parent.name if path.is_dir() else "")
        if path.is_dir() and case.id != file.stem:
            raise EvalCaseError(f"{file.name} holds case id {case.id}.")
        if case.id in seen:
            raise EvalCaseError(f"{file.name} repeats case id {case.id}.")
        seen.add(case.id)
        cases.append(case)
    return cases


def _build_case(entry: dict[str, Any], source: str, category: str) -> EvalCase:
    """Convert one dataset entry into a case, or explain why it cannot be graded."""
    for required in ("id", "fixture", "question", "expect_proposal"):
        if required not in entry:
            raise EvalCaseError(f"{source} is missing `{required}`.")
    assertions = tuple(_build_assertion(raw, source) for raw in entry.get("assert", []))
    if entry["expect_proposal"] and not assertions:
        raise EvalCaseError(f"{source} expects a proposal but asserts nothing about it.")
    if entry["expect_proposal"] and not entry.get("changes"):
        raise EvalCaseError(f"{source} expects a proposal but names no part it may change.")
    if not entry["expect_proposal"] and assertions:
        raise EvalCaseError(f"{source} expects no proposal, so its assertions can never run.")
    return EvalCase(
        id=str(entry["id"]),
        fixture=str(entry["fixture"]),
        question=str(entry["question"]),
        expect_proposal=bool(entry["expect_proposal"]),
        category=category,
        assertions=assertions,
        changes=tuple(entry.get("changes", ())),
        answer_contains=tuple(
            tuple(value) if isinstance(value, list) else value for value in entry.get("answer_contains", ())
        ),
        note=str(entry.get("note", "")),
    )


def _build_assertion(raw: dict[str, Any], source: str) -> Assertion:
    """Convert one criterion, rejecting an unknown or ambiguous kind."""
    if "path" not in raw:
        raise EvalCaseError(f"{source} has an assertion without a path.")
    kinds = [kind for kind in _ASSERTION_KINDS if kind in raw]
    if len(kinds) != 1:
        raise EvalCaseError(
            f"{source} assertion on {raw['path']} must use exactly one of: {', '.join(_ASSERTION_KINDS)}."
        )
    return Assertion(path=str(raw["path"]), kind=kinds[0], value=raw[kinds[0]])


def grade(case: EvalCase, outcome: RunOutcome, computed: dict[str, Any] | None = None) -> CaseResult:
    """Apply every criterion of one case to what the run produced."""
    checks: list[CheckResult] = []
    proposed = outcome.proposed is not None
    checks.append(
        CheckResult(
            description=f"proposal {'expected' if case.expect_proposal else 'not expected'}",
            passed=proposed == case.expect_proposal,
            detail="" if proposed == case.expect_proposal else f"a proposal was {'not ' if not proposed else ''}made",
        )
    )
    if case.expect_proposal and proposed:
        checks.extend(_check_assertion(outcome, assertion) for assertion in case.assertions)
        checks.append(_check_nothing_else_changed(outcome, case.changes))
    checks.extend(_check_answer(outcome.answer, expected, computed or {}) for expected in case.answer_contains)
    return CaseResult(case_id=case.id, checks=tuple(checks))


def _check_assertion(outcome: RunOutcome, assertion: Assertion) -> CheckResult:
    """Resolve one path and compare what it found."""
    try:
        found = resolve(outcome.proposed, assertion.path)
        if assertion.kind in {"delta", "added", "removed"}:
            return _check_against_initial(outcome, assertion, found)
    except EvalCaseError as error:
        return CheckResult(assertion.describe(), False, str(error))

    if assertion.kind == "absent":
        return CheckResult(assertion.describe(), not found, f"found {found!r}" if found else "")
    if assertion.kind == "present":
        return CheckResult(assertion.describe(), bool(found), "" if found else "nothing matched")
    if assertion.kind == "count":
        total = len(_collection(found))
        return CheckResult(assertion.describe(), total == assertion.value, f"found {total}")
    if not found:
        return CheckResult(assertion.describe(), False, "nothing matched")
    if assertion.kind == "equals":
        passed = any(_matches(value, assertion.value) for value in found)
    elif assertion.kind == "one_of":
        passed = any(any(_matches(value, option) for option in assertion.value) for value in found)
    else:
        passed = any(_contains(value, assertion.value) for value in found)
    return CheckResult(assertion.describe(), passed, "" if passed else f"found {found!r}")


def _check_against_initial(outcome: RunOutcome, assertion: Assertion, found: list[Any]) -> CheckResult:
    """Compare a collection with the same collection before the run.

    A size read from the fixture would have to be rewritten whenever the fixture
    changes, so a case states how much it should change instead.
    """
    before = _collection(resolve(outcome.initial, assertion.path))
    after = _collection(found)
    if assertion.kind == "delta":
        change = len(after) - len(before)
        return CheckResult(assertion.describe(), change == assertion.value, f"changed by {change:+d}")

    before_keys = Counter(_key(item) for item in before)
    after_keys = Counter(_key(item) for item in after)
    difference = (after_keys - before_keys) if assertion.kind == "added" else (before_keys - after_keys)
    expected = Counter(_key(item) for item in assertion.value)
    if difference == expected:
        return CheckResult(assertion.describe(), True)
    # Report the values themselves rather than the keys used to compare them.
    lookup = {_key(item): item for item in (after if assertion.kind == "added" else before)}
    found = sorted(str(lookup.get(key, key)) for key in difference.elements())
    return CheckResult(assertion.describe(), False, f"{assertion.kind} {found}")


def _collection(found: list[Any]) -> list[Any]:
    """Read one resolved list as a collection, or treat the matches as one."""
    return found[0] if len(found) == 1 and isinstance(found[0], list) else found


def _key(value: Any) -> str:
    """Give any resolved value a comparable identity, including a mapping."""
    return json.dumps(value, sort_keys=True, default=str)


def _check_nothing_else_changed(outcome: RunOutcome, changes: tuple[str, ...]) -> CheckResult:
    """Confirm the proposal touched only the parts the case allows it to touch.

    Naming what may change, rather than listing what may not, means a part left
    out of the case is guarded rather than ignored.
    """
    allowed = tuple(tuple(path.split(".")) for path in changes)
    touched = _touched_outside(outcome.initial, outcome.proposed, (), allowed)
    description = f"changes only {', '.join(changes)}"
    return CheckResult(description, not touched, "" if not touched else f"also changed {', '.join(touched)}")


def _touched_outside(before: Any, after: Any, path: tuple[str, ...], allowed: tuple[tuple[str, ...], ...]) -> list[str]:
    """List every part outside the allowed paths that the proposal changed."""
    if any(_under(path, entry) for entry in allowed):
        return []
    if isinstance(before, dict) and isinstance(after, dict) and any(_through(path, entry) for entry in allowed):
        touched: list[str] = []
        for key in sorted(set(before) | set(after)):
            touched.extend(_touched_outside(before.get(key), after.get(key), (*path, key), allowed))
        return touched
    if before == after:
        return []
    return [".".join(path) or "(whole schedule)"]


def _under(path: tuple[str, ...], allowed: tuple[str, ...]) -> bool:
    """Report whether a path is the allowed path or sits inside it."""
    return len(path) >= len(allowed) and path[: len(allowed)] == allowed


def _through(path: tuple[str, ...], allowed: tuple[str, ...]) -> bool:
    """Report whether an allowed path continues below this one."""
    return len(path) < len(allowed) and allowed[: len(path)] == path


def _check_answer(answer: str, expected: str | Sequence[str], computed: dict[str, Any]) -> CheckResult:
    """Confirm the answer mentions a value derived from the fixture.

    A case may offer several wordings of the same value, because a correct
    answer can say eighty-seven where the fixture says 87.
    """
    options = [expected] if isinstance(expected, str) else list(expected)
    resolved = [option.format(**computed) if computed else option for option in options]
    passed = any(option.casefold() in answer.casefold() for option in resolved)
    described = " or ".join(repr(option) for option in resolved)
    return CheckResult(f"answer mentions {described}", passed, "" if passed else "not mentioned")


def resolve(node: Any, path: str) -> list[Any]:
    """Read every value one path selects, supporting `items[0]` and `items[?id=P1]`."""
    if not path:
        raise EvalCaseError("An empty path selects nothing.")
    position = 0
    current = [node]
    while position < len(path):
        match = _STEP.match(path, position)
        if match is None:
            raise EvalCaseError(f"Path {path!r} is malformed at position {position}.")
        position = match.end()
        name, index, key, value, expand = match.groups()
        if expand is not None:
            current = [item for entry in current for item in (entry if isinstance(entry, list) else [entry])]
        elif name is not None:
            current = [entry[name] for entry in current if isinstance(entry, dict) and name in entry]
        elif index is not None:
            current = [entry[int(index)] for entry in current if isinstance(entry, list) and int(index) < len(entry)]
        else:
            # A selector filters list entries or narrows the current set, so
            # `preferences[?type=shift request][?person=P3]` selects one entry.
            candidates = [item for entry in current for item in (entry if isinstance(entry, list) else [entry])]
            current = [item for item in candidates if isinstance(item, dict) and _selects(item.get(key), value)]
    return current


def _matches(found: Any, expected: Any) -> bool:
    """Compare one value, ignoring case and surrounding space for text.

    Lists compare entry by entry and in order, because a succession pattern of
    N then D is a different rule from D then N.
    """
    if isinstance(found, list) or isinstance(expected, list):
        if not isinstance(found, list) or not isinstance(expected, list) or len(found) != len(expected):
            return False
        return all(_matches(a, b) for a, b in zip(found, expected))
    if isinstance(found, str) and isinstance(expected, str):
        return found.strip().casefold() == expected.strip().casefold()
    if isinstance(found, bool) or isinstance(expected, bool):
        return found is expected
    if isinstance(found, (int, float)) and isinstance(expected, (int, float)):
        return float(found) == float(expected)
    return str(found).strip().casefold() == str(expected).strip().casefold()


def _selects(found: Any, expected: Any) -> bool:
    """Match a selector exactly, or by membership when the field holds a list.

    Substring matching would silently select the wrong entity, since a group id
    such as `Day People` is a prefix of `Day People w/o A`.
    """
    if isinstance(found, list):
        return any(_matches(item, expected) for item in found)
    return _matches(found, expected)


def _contains(found: Any, expected: Any) -> bool:
    """Check membership for a list and substring for text."""
    if isinstance(found, list):
        return any(_matches(item, expected) for item in found)
    if isinstance(found, str) and isinstance(expected, str):
        return expected.strip().casefold() in found.strip().casefold()
    return _matches(found, expected)


def computed_values(schedule: Any) -> dict[str, Any]:
    """Derive answer values from the fixture, so no expected number is typed by hand."""
    people = _section(schedule, "people")
    shift_types = _section(schedule, "shiftTypes")
    dates = _section(schedule, "dates")
    date_range = dates.get("range") if isinstance(dates.get("range"), dict) else {}
    preferences = schedule.get("preferences") if isinstance(schedule, dict) else []
    return {
        "people_count": len(people.get("items", [])),
        "people_group_count": len(people.get("groups", [])),
        "shift_type_count": len(shift_types.get("items", [])),
        "shift_type_group_count": len(shift_types.get("groups", [])),
        "date_group_count": len(dates.get("groups", [])),
        "preference_count": len(preferences if isinstance(preferences, list) else []),
        "start_date": date_range.get("startDate", ""),
        "end_date": date_range.get("endDate", ""),
        "year": str(date_range.get("startDate", ""))[:4],
    }


def _section(schedule: Any, name: str) -> dict[str, Any]:
    section = schedule.get(name) if isinstance(schedule, dict) else None
    return section if isinstance(section, dict) else {}


def covered_paths(case: EvalCase) -> set[str]:
    """Report the schedule paths a case exercises, read from its own criteria.

    Deriving coverage keeps it honest. A hand-written label drifts from the
    assertions beside it and a typo silently covers nothing.
    """
    sources = [assertion.path for assertion in case.assertions] + list(case.changes)
    return {_generalize(path) for path in sources if path}


def covered_preference_types(case: EvalCase) -> set[str]:
    """Report the preference types a case exercises, from its type selectors."""
    types: set[str] = set()
    for assertion in case.assertions:
        if not assertion.path.startswith("preferences"):
            continue
        types.update(match.group(1) for match in re.finditer(r"\[\?type=([^\]]+)\]", assertion.path))
    return types


def _generalize(path: str) -> str:
    """Reduce one path to the shape it addresses, dropping selectors and indexes."""
    # Chained selectors narrow one collection, so they describe one shape.
    return re.sub(r"(?:\[\])+", "[]", re.sub(r"\[[^\]]*\]", "[]", path))
