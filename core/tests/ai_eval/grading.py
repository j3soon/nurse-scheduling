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
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Most cases grade only the produced schedule or answer. Focused capability cases
# may also assert a small, intentional tool trajectory.
_STEP = re.compile(r"\.?([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]|\[\?([^=\]]+)=([^\]]*)\]|(\[\])")
_ASSERTION_KINDS = ("equals", "contains", "count", "delta", "added", "removed", "absent", "present")
_TOOL_USAGE_KEYS = {"required", "forbidden", "max_total", "max_per_tool"}


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
class ExpectedDiff:
    """The complete semantic change expected at one schedule path."""

    path: str
    added: tuple[Any, ...] = ()
    removed: tuple[Any, ...] = ()
    before: Any = None
    after: Any = None
    compares_value: bool = False

    def describe(self) -> str:
        return f"{self.path} has the expected semantic diff"


@dataclass(frozen=True)
class ToolUsageExpectation:
    """Optional trajectory checks for cases designed to exercise model tools."""

    required: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    max_total: int | None = None
    max_per_tool: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class EvalCase:
    """One question with verifiable criteria for the schedule it should produce."""

    id: str
    fixture: str
    question: str
    expect_proposal: bool
    proposal_turn: int | None = None
    user_turns: tuple[str, ...] = ()
    intermediate_answer_contains: tuple[tuple[str | tuple[str, ...], ...], ...] = ()
    tags: tuple[str, ...] = ()
    category: str = ""
    assertions: tuple[Assertion, ...] = ()
    expected_diff: tuple[ExpectedDiff, ...] = ()
    changes: tuple[str, ...] = ()
    answer_contains: tuple[str | tuple[str, ...], ...] = ()
    tool_usage: ToolUsageExpectation | None = None
    note: str = ""

    def __post_init__(self) -> None:
        """Keep direct test construction compatible with single-turn cases."""
        if not self.user_turns:
            object.__setattr__(self, "user_turns", (self.question,))
        if self.expect_proposal and self.proposal_turn is None:
            object.__setattr__(self, "proposal_turn", len(self.user_turns))


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
    intermediate_answers: list[str] = field(default_factory=list)
    intermediate_proposals: list[bool] = field(default_factory=list)
    proposal_turns: list[bool] = field(default_factory=list)


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
    for required in ("id", "fixture", "expect_proposal"):
        if required not in entry:
            raise EvalCaseError(f"{source} is missing `{required}`.")
    raw_turns = entry.get("user_turns")
    if raw_turns is None:
        if "question" not in entry:
            raise EvalCaseError(f"{source} is missing `question` or `user_turns`.")
        raw_turns = [entry["question"]]
    if (
        not isinstance(raw_turns, list)
        or not raw_turns
        or not all(isinstance(turn, str) and turn for turn in raw_turns)
    ):
        raise EvalCaseError(f"{source} `user_turns` must be a non-empty list of strings.")
    raw_intermediate = entry.get("intermediate_answer_contains", [])
    if not isinstance(raw_intermediate, list) or len(raw_intermediate) > len(raw_turns) - 1:
        raise EvalCaseError(f"{source} has invalid `intermediate_answer_contains`.")
    intermediate = tuple(
        tuple(tuple(value) if isinstance(value, list) else value for value in expected) for expected in raw_intermediate
    )
    raw_tags = entry.get("tags", [])
    if not isinstance(raw_tags, list) or not all(isinstance(tag, str) and tag for tag in raw_tags):
        raise EvalCaseError(f"{source} `tags` must be a list of strings.")
    assertions = tuple(_build_assertion(raw, source) for raw in entry.get("assert", []))
    expected_diff = tuple(_build_expected_diff(raw, source) for raw in entry.get("expected_diff", []))
    proposal_turn = entry.get("proposal_turn")
    if proposal_turn is None and entry["expect_proposal"]:
        proposal_turn = len(raw_turns)
    if proposal_turn is not None and (
        isinstance(proposal_turn, bool)
        or not isinstance(proposal_turn, int)
        or not 1 <= proposal_turn <= len(raw_turns)
    ):
        raise EvalCaseError(f"{source} `proposal_turn` must identify one user turn.")
    if bool(entry["expect_proposal"]) != (proposal_turn is not None):
        raise EvalCaseError(f"{source} `proposal_turn` must agree with `expect_proposal`.")
    if entry["expect_proposal"] and not assertions and not expected_diff:
        raise EvalCaseError(f"{source} expects a proposal but asserts nothing about it.")
    if entry["expect_proposal"] and not entry.get("changes"):
        raise EvalCaseError(f"{source} expects a proposal but names no part it may change.")
    if not entry["expect_proposal"] and (assertions or expected_diff):
        raise EvalCaseError(f"{source} expects no proposal, so its schedule criteria can never run.")
    return EvalCase(
        id=str(entry["id"]),
        fixture=str(entry["fixture"]),
        question=str(raw_turns[0]),
        expect_proposal=bool(entry["expect_proposal"]),
        proposal_turn=proposal_turn,
        user_turns=tuple(raw_turns),
        intermediate_answer_contains=intermediate,
        tags=tuple(raw_tags),
        category=category,
        assertions=assertions,
        expected_diff=expected_diff,
        changes=tuple(entry.get("changes", ())),
        answer_contains=tuple(
            tuple(value) if isinstance(value, list) else value for value in entry.get("answer_contains", ())
        ),
        tool_usage=_build_tool_usage(entry.get("tool_usage"), source),
        note=str(entry.get("note", "")),
    )


def _build_tool_usage(raw: object, source: str) -> ToolUsageExpectation | None:
    """Validate optional tool-trajectory criteria without affecting outcome-only cases."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise EvalCaseError(f"{source} `tool_usage` must be an object.")
    unknown = set(raw) - _TOOL_USAGE_KEYS
    if unknown:
        raise EvalCaseError(f"{source} `tool_usage` has unknown fields: {', '.join(sorted(unknown))}.")

    required = _tool_names(raw.get("required", []), source, "required")
    forbidden = _tool_names(raw.get("forbidden", []), source, "forbidden")
    overlap = sorted(set(required) & set(forbidden))
    if overlap:
        raise EvalCaseError(f"{source} requires and forbids the same tools: {', '.join(overlap)}.")

    max_total = raw.get("max_total")
    if max_total is not None and (isinstance(max_total, bool) or not isinstance(max_total, int) or max_total < 0):
        raise EvalCaseError(f"{source} `tool_usage.max_total` must be a non-negative integer.")
    raw_per_tool = raw.get("max_per_tool", {})
    if not isinstance(raw_per_tool, dict) or not all(
        isinstance(name, str) and name and not isinstance(limit, bool) and isinstance(limit, int) and limit >= 0
        for name, limit in raw_per_tool.items()
    ):
        raise EvalCaseError(f"{source} `tool_usage.max_per_tool` must map tool names to non-negative integers.")
    return ToolUsageExpectation(required, forbidden, max_total, tuple(sorted(raw_per_tool.items())))


def _tool_names(raw: object, source: str, field_name: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(name, str) and name for name in raw):
        raise EvalCaseError(f"{source} `tool_usage.{field_name}` must be a list of tool names.")
    if len(raw) != len(set(raw)):
        raise EvalCaseError(f"{source} `tool_usage.{field_name}` repeats a tool name.")
    return tuple(raw)


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


def _build_expected_diff(raw: object, source: str) -> ExpectedDiff:
    """Validate one exact semantic collection diff."""
    if not isinstance(raw, dict) or not isinstance(raw.get("path"), str) or not raw["path"]:
        raise EvalCaseError(f"{source} has an expected diff without a path.")
    unknown = set(raw) - {"path", "added", "removed", "before", "after"}
    if unknown:
        raise EvalCaseError(f"{source} expected diff has unknown fields: {', '.join(sorted(unknown))}.")
    added = raw.get("added", [])
    removed = raw.get("removed", [])
    if not isinstance(added, list) or not isinstance(removed, list):
        raise EvalCaseError(f"{source} expected diff `added` and `removed` must be lists.")
    compares_value = "before" in raw or "after" in raw
    if compares_value and ("before" not in raw or "after" not in raw or added or removed):
        raise EvalCaseError(f"{source} expected diff must use either before/after or added/removed.")
    if not compares_value and not added and not removed:
        raise EvalCaseError(f"{source} expected diff must add or remove something.")
    return ExpectedDiff(
        path=raw["path"],
        added=tuple(added),
        removed=tuple(removed),
        before=raw.get("before"),
        after=raw.get("after"),
        compares_value=compares_value,
    )


def grade(case: EvalCase, outcome: RunOutcome, computed: dict[str, Any] | None = None) -> CaseResult:
    """Apply every criterion of one case to what the run produced."""
    checks: list[CheckResult] = []
    proposal_turns = outcome.proposal_turns
    if not proposal_turns and outcome.intermediate_proposals:
        proposal_turns = [*outcome.intermediate_proposals, outcome.proposed is not None]
    for index, proposed in enumerate(proposal_turns, start=1):
        expected = index == case.proposal_turn
        checks.append(
            CheckResult(
                description=f"turn {index} proposal {'expected' if expected else 'not expected'}",
                passed=proposed == expected,
                detail="" if proposed == expected else f"a proposal was {'not ' if not proposed else ''}made",
            )
        )
    for index, expected_values in enumerate(case.intermediate_answer_contains):
        answer = outcome.intermediate_answers[index] if index < len(outcome.intermediate_answers) else ""
        checks.extend(_check_answer(answer, expected, computed or {}) for expected in expected_values)
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
        checks.extend(_check_expected_diff(outcome, expected) for expected in case.expected_diff)
        checks.append(_check_nothing_else_changed(outcome, case.changes))
    checks.extend(_check_answer(outcome.answer, expected, computed or {}) for expected in case.answer_contains)
    if case.tool_usage is not None:
        checks.extend(_check_tool_usage(outcome.activity, case.tool_usage))
    return CaseResult(case_id=case.id, checks=tuple(checks))


def _check_expected_diff(outcome: RunOutcome, expected: ExpectedDiff) -> CheckResult:
    """Compare a complete value replacement or list multiset delta."""
    try:
        before = resolve(outcome.initial, expected.path)
        after = resolve(outcome.proposed, expected.path)
    except EvalCaseError as error:
        return CheckResult(expected.describe(), False, str(error))
    if expected.compares_value:
        actual_before = before[0] if len(before) == 1 else None
        actual_after = after[0] if len(after) == 1 else None
        passed = _key(actual_before) == _key(expected.before) and _key(actual_after) == _key(expected.after)
        detail = "" if passed else f"changed from {actual_before!r} to {actual_after!r}"
        return CheckResult(expected.describe(), passed, detail)
    if len(before) != 1 or not isinstance(before[0], list) or len(after) != 1 or not isinstance(after[0], list):
        return CheckResult(expected.describe(), False, "path must resolve to one list before and after")
    before_keys = Counter(_key(item) for item in before[0])
    after_keys = Counter(_key(item) for item in after[0])
    actual_added = after_keys - before_keys
    actual_removed = before_keys - after_keys
    wanted_added = Counter(_key(item) for item in expected.added)
    wanted_removed = Counter(_key(item) for item in expected.removed)
    passed = actual_added == wanted_added and actual_removed == wanted_removed
    if passed:
        return CheckResult(expected.describe(), True)
    detail = f"added {_counter_values(actual_added)!r}, removed {_counter_values(actual_removed)!r}"
    return CheckResult(expected.describe(), False, detail)


def _counter_values(values: Counter[str]) -> list[Any]:
    """Decode semantic keys for readable failure output."""
    return [json.loads(value) for value in values.elements()]


def _check_tool_usage(
    activity: Sequence[dict[str, Any]],
    expected: ToolUsageExpectation,
) -> list[CheckResult]:
    """Grade completed tool calls while distinguishing successful required use."""
    tool_events = [event for event in activity if event.get("kind") == "tool" and isinstance(event.get("name"), str)]
    counts = Counter(event["name"] for event in tool_events)
    successful = Counter(event["name"] for event in tool_events if event.get("ok") is True)
    checks = [
        CheckResult(
            f"uses successful {name} tool",
            successful[name] > 0,
            "not used successfully" if successful[name] == 0 else "",
        )
        for name in expected.required
    ]
    checks.extend(
        CheckResult(
            f"does not use {name} tool",
            counts[name] == 0,
            f"used {counts[name]} time(s)" if counts[name] else "",
        )
        for name in expected.forbidden
    )
    if expected.max_total is not None:
        within_total = len(tool_events) <= expected.max_total
        checks.append(
            CheckResult(
                f"uses at most {expected.max_total} tool call(s)",
                within_total,
                "" if within_total else f"used {len(tool_events)}",
            )
        )
    for name, limit in expected.max_per_tool:
        within_limit = counts[name] <= limit
        checks.append(
            CheckResult(
                f"uses {name} at most {limit} time(s)",
                within_limit,
                "" if within_limit else f"used {counts[name]}",
            )
        )
    return checks


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
    return json.dumps(_json_value(value), sort_keys=True, default=str)


def _json_value(value: Any, field_name: str = "") -> Any:
    """Represent YAML infinities with valid JSON strings in testcase expectations."""
    if isinstance(value, float) and math.isinf(value):
        return ".inf" if value > 0 else "-.inf"
    if isinstance(value, dict):
        default_weight = {
            "shift request": 1,
            "shift type successions": 1,
            "shift type requirement": -1,
            "shift count": -1,
            "shift affinity": 1,
        }.get(value.get("type"))
        return {
            key: _json_value(child, key)
            for key, child in value.items()
            if not (
                (key == "description" and child == "")
                or (key == "history" and child == [])
                or (key == "weight" and child == default_weight)
            )
        }
    if isinstance(value, list):
        normalized = [_json_value(child) for child in value]
        if field_name != "pattern":
            normalized.sort(key=lambda child: json.dumps(child, sort_keys=True, default=str))
        return normalized
    return value


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
    covered = {_generalize(path) for path in sources if path}
    for expected in case.expected_diff:
        covered.add(_generalize(expected.path))
        if expected.compares_value:
            covered.update(_value_paths(expected.path, expected.after))
        else:
            for value in (*expected.added, *expected.removed):
                covered.update(_value_paths(f"{expected.path}[]", value))
    return covered


def covered_preference_types(case: EvalCase) -> set[str]:
    """Report the preference types a case exercises, from its type selectors."""
    types: set[str] = set()
    for assertion in case.assertions:
        if not assertion.path.startswith("preferences"):
            continue
        types.update(match.group(1) for match in re.finditer(r"\[\?type=([^\]]+)\]", assertion.path))
    for expected in case.expected_diff:
        if expected.path != "preferences":
            continue
        for value in (*expected.added, *expected.removed):
            if isinstance(value, dict) and isinstance(value.get("type"), str):
                types.add(value["type"])
    return types


def _value_paths(path: str, value: Any) -> set[str]:
    """Describe every nested shape named by an exact expected value."""
    paths = {_generalize(path)}
    if isinstance(value, dict):
        for key, child in value.items():
            paths.update(_value_paths(f"{path}.{key}", child))
    elif isinstance(value, list):
        for child in value:
            paths.update(_value_paths(f"{path}[]", child))
    return paths


def _generalize(path: str) -> str:
    """Reduce one path to the shape it addresses, dropping selectors and indexes."""
    # Chained selectors narrow one collection, so they describe one shape.
    return re.sub(r"(?:\[\])+", "[]", re.sub(r"\[[^\]]*\]", "[]", path))
