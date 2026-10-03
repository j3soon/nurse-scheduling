"""Canonical request selectors for sandbox optimizer-result inspection."""

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

# This file is mostly AI generated.

import hashlib
import json
import logging
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from nurse_scheduling.constants import OFF, OFF_sid
from nurse_scheduling.loader import load_data
from nurse_scheduling.models import CompiledShiftRequest, CompiledShiftTypeRequirements, CompiledShiftTypeSuccessions
from nurse_scheduling.preference_audit import audit_staffing_and_successions

from .attachment_tools.inspect_optimizer_result import _read_assignments, inspect_result

MAX_REQUEST_AUDIT_BYTES = 4096
POLICY_AUDIT_SCOPE = (
    "Staffing equations (shortfall in coefficient units) and signed shift-succession windows including history. "
    "Other preferences are not audited."
)
logger = logging.getLogger(__name__)


def build_result_context(schedule_yaml: str, *, workbook: bytes | None = None) -> dict[str, Any]:
    """Project canonical selectors into a portable result-reader context."""
    data = load_data(schedule_yaml.encode())
    context = _project_context(data, schedule_yaml)
    if workbook is not None:
        try:
            with TemporaryDirectory() as directory:
                path = Path(directory) / "result.xlsx"
                path.write_bytes(workbook)
                policy = _policy_audit(data, context, path)
            if policy is not None:
                context["policy"] = policy
                context["policy_scope"] = POLICY_AUDIT_SCOPE
                context["workbook_sha256"] = hashlib.sha256(workbook).hexdigest()
        except Exception:
            logger.debug("Optimizer policy context unavailable", exc_info=True)
    return context


def _project_context(data, schedule_yaml: str) -> dict[str, Any]:
    compiled = data.compiled_schedule
    people = [person.id for person in data.people.items]
    shifts = [shift.id for shift in data.shiftTypes.items]
    dates = [date.isoformat() for date in compiled.dates]
    requests = []
    for index, (pref, resolved) in enumerate(zip(data.preferences, compiled.preferences, strict=True)):
        if not isinstance(resolved, CompiledShiftRequest) or pref.weight == 0:
            continue
        weight = pref.weight
        if isinstance(weight, float) and math.isinf(weight):
            weight = ".inf" if weight > 0 else "-.inf"
        requests.append(
            {
                "preference_index": index,
                "weight": weight,
                "people": [people[p] for p in resolved.people],
                "dates": [dates[d] for d in resolved.dates],
                "shift_types": [OFF if s == OFF_sid else shifts[s] for s in resolved.shift_types],
            }
        )
    return {
        "schema_version": 1,
        "source_sha256": hashlib.sha256(schedule_yaml.encode()).hexdigest(),
        "people": people,
        "dates": dates,
        "shift_types": shifts,
        "requests": requests,
    }


def _policy_audit(data, context, path):
    if not any(
        isinstance(pref, (CompiledShiftTypeRequirements, CompiledShiftTypeSuccessions))
        for pref in data.compiled_schedule.preferences
    ):
        return None
    assignments, _, _ = _read_assignments(path, context)
    shifts = {shift: s for s, shift in enumerate(context["shift_types"])}
    shifts[OFF] = OFF_sid
    policy = audit_staffing_and_successions(
        data,
        {
            (d, p): shifts[assignments[person][date]]
            for d, date in enumerate(context["dates"])
            for p, person in enumerate(context["people"])
        },
    )
    if len(json.dumps(policy, ensure_ascii=False, allow_nan=False).encode()) <= MAX_REQUEST_AUDIT_BYTES:
        return policy
    return None


def build_request_audit(schedule_yaml: str, workbook: bytes) -> dict[str, Any] | None:
    """Return bounded counts from the submitted snapshot, or leave inspection to the agent."""
    try:
        data = load_data(schedule_yaml.encode())
        context = _project_context(data, schedule_yaml)
        policy = None
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.xlsx"
            path.write_bytes(workbook)
            audit = inspect_result(path, context, context["source_sha256"], max_unmet=0)
            policy = _policy_audit(data, context, path)
        summary = {
            "scope": "Expanded shift-request person/date cells. Staffing and rest are not audited.",
            "source_sha256": audit["source_sha256"],
            "summary": audit["summary"],
        }
        if len(json.dumps(summary, ensure_ascii=False, allow_nan=False).encode()) <= MAX_REQUEST_AUDIT_BYTES:
            if policy is not None:
                extended = {
                    **summary,
                    "scope": "Expanded shift-request person/date cells. " + POLICY_AUDIT_SCOPE,
                    "policy": policy,
                }
                if len(json.dumps(extended, ensure_ascii=False, allow_nan=False).encode()) <= MAX_REQUEST_AUDIT_BYTES:
                    return extended
            return summary
    except Exception:
        # Optional reporting must not suppress an otherwise downloadable result.
        logger.debug("Optimizer request summary unavailable", exc_info=True)
    return None
