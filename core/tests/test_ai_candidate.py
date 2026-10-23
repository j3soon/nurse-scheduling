"""Tests for trusted review of complete AI schedule candidates."""

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

import difflib
import json
from io import StringIO

import pytest
from ruamel.yaml import YAML

from nurse_scheduling.ai.candidate import review_schedule_candidate

from .ai_test_helper import SCHEDULE_BYTE_LIMIT, base_schedule_payload, schedule_yaml


def test_unchanged_candidate_creates_no_proposal():
    schedule = schedule_yaml()

    review = review_schedule_candidate(schedule, schedule, SCHEDULE_BYTE_LIMIT)

    assert review.outcome.ok
    assert review.proposal is None


def test_valid_candidate_creates_structural_proposal():
    base = schedule_yaml()
    candidate = base.replace(
        "  - id: P1\n    description: ''",
        "  - id: P1\n    description: Head",
        1,
    )

    review = review_schedule_candidate(base, candidate, SCHEDULE_BYTE_LIMIT)

    assert review.outcome.ok
    assert review.proposal is not None
    assert review.proposal.text == candidate
    assert "people.items[0].description" in review.proposal.diff.render()


def test_candidate_with_new_validation_problem_is_rejected():
    base = schedule_yaml()

    review = review_schedule_candidate(base, "not: [valid", SCHEDULE_BYTE_LIMIT)

    assert not review.outcome.ok
    assert "cannot be applied" in review.outcome.text
    assert "introduces problems" in review.outcome.text
    assert review.proposal is None


def test_rebuilt_candidate_restores_only_the_required_rule():
    from nurse_scheduling.loader import _load_yaml

    from .ai_test_helper import base_schedule_payload

    payload = base_schedule_payload()
    payload["description"] = "Rebuilt schedule"
    payload["people"]["items"][0]["history"] = ["OFF"]
    payload["preferences"] = payload["preferences"][1:]
    candidate = schedule_yaml(payload)

    review = review_schedule_candidate(schedule_yaml(), candidate, SCHEDULE_BYTE_LIMIT)

    assert review.outcome.ok
    assert review.proposal is not None
    restored = _load_yaml(review.proposal.text.encode())
    required = restored["preferences"].pop(0)
    assert required == {"type": "at most one shift per day"}
    assert restored == payload
    assert "restored the required" in review.outcome.text


def _browser_style_yaml(payload: dict) -> str:
    # js-yaml indents sequences under their key. The default ruamel layout does not.
    yaml = YAML(typ="safe", pure=True)
    yaml.default_flow_style = False
    yaml.representer.sort_base_mapping_type_on_output = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    output = StringIO()
    yaml.dump(payload, output)
    return output.getvalue()


@pytest.mark.parametrize("layout", ["block", "indented", "flow"])
def test_required_rule_restoration_keeps_the_rest_of_the_text(layout):
    from nurse_scheduling.loader import _load_yaml

    payload = base_schedule_payload()
    payload["description"] = "Rebuilt schedule"
    payload["preferences"] = payload["preferences"][1:]
    if layout == "flow":
        rest = {key: value for key, value in payload.items() if key != "preferences"}
        body = schedule_yaml(rest) + f"preferences: {json.dumps(payload['preferences'])}\n"
    else:
        body = schedule_yaml(payload) if layout == "block" else _browser_style_yaml(payload)
    candidate = "# Ward roster kept by the model\n" + body

    review = review_schedule_candidate(schedule_yaml(), candidate, SCHEDULE_BYTE_LIMIT)

    assert review.outcome.ok
    assert review.proposal is not None
    restored = review.proposal.text
    assert _load_yaml(restored.encode()) == {
        **payload,
        "preferences": [{"type": "at most one shift per day"}, *payload["preferences"]],
    }
    changes = [
        line for line in difflib.ndiff(candidate.splitlines(), restored.splitlines()) if line[:2] in {"+ ", "- "}
    ]
    if layout == "flow":
        assert [line[:15] for line in changes] == ["- preferences: ", "+ preferences: "]
    else:
        indent = "  " if layout == "indented" else ""
        assert changes == [f"+ {indent}- type: at most one shift per day"]


def test_required_rule_restoration_does_not_hide_other_errors():
    from .ai_test_helper import base_schedule_payload

    payload = base_schedule_payload()
    payload["preferences"] = payload["preferences"][1:]
    payload["preferences"][0]["person"] = ["unknown-person"]

    review = review_schedule_candidate(schedule_yaml(), schedule_yaml(payload), SCHEDULE_BYTE_LIMIT)

    assert not review.outcome.ok
    assert review.proposal is None


def test_existing_required_rule_is_not_replaced_or_duplicated():
    from .ai_test_helper import base_schedule_payload

    payload = base_schedule_payload()
    payload["description"] = "Updated"
    payload["preferences"][0]["description"] = "Original required rule"
    candidate = schedule_yaml(payload)

    review = review_schedule_candidate(schedule_yaml(), candidate, SCHEDULE_BYTE_LIMIT)

    assert review.outcome.ok
    assert review.proposal.text == candidate
    assert "restored" not in review.outcome.text


def test_required_rule_restoration_respects_the_output_size_limit():
    from .ai_test_helper import base_schedule_payload

    payload = base_schedule_payload()
    payload["preferences"] = payload["preferences"][1:]
    candidate = schedule_yaml(payload)

    review = review_schedule_candidate(schedule_yaml(), candidate, len(candidate.encode()))

    assert not review.outcome.ok
    assert review.proposal is None
