"""Build and compare reproducible system-prompt variants."""

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

import hashlib
from dataclasses import dataclass
from pathlib import Path

from nurse_scheduling.ai.system_prompt import (
    PROMPT_STEPS_PATH,
    compose_system_prompt,
    load_system_prompt_entries,
    load_system_prompt_sections,
)

STEPS_PATH = PROMPT_STEPS_PATH


@dataclass(frozen=True)
class PromptStep:
    """One prompt section and the cases intended to show its marginal benefit."""

    id: str
    file: str
    starts_with: str
    cases: tuple[str, ...]
    hypothesis: str
    sha256: str
    evidence: tuple[dict[str, str], ...] = ()
    gaps: tuple[str, ...] = ()


def load_prompt_steps(path: Path = STEPS_PATH) -> tuple[PromptStep, ...]:
    """Fail if the evidence ledger no longer matches the production prompt."""
    raw = load_system_prompt_entries(path)
    steps = tuple(
        PromptStep(
            **{
                **item,
                "cases": tuple(item["cases"]),
                "evidence": tuple(item.get("evidence", ())),
                "gaps": tuple(item.get("gaps", ())),
            }
        )
        for item in raw
    )
    sections = load_system_prompt_sections(raw)
    for index, (step, section) in enumerate(zip(steps, sections, strict=True), 1):
        if not step.id or not step.starts_with or not step.hypothesis or not (step.cases or step.gaps):
            raise ValueError(f"Prompt step {index} needs an ID, anchor, hypothesis, and cases or gaps")
        if not section.startswith(step.starts_with):
            raise ValueError(f"Prompt step {index} ({step.id}) no longer matches its section")
        if hashlib.sha256(section.encode()).hexdigest() != step.sha256:
            raise ValueError(f"Prompt step {index} ({step.id}) changed. Update its hypothesis and evidence")
        if any(record.get("case") not in step.cases for record in step.evidence):
            raise ValueError(f"Prompt step {index} evidence must name one of its targeted cases")
    return steps


def prompt_at_step(step: int, *, omit: int | None = None) -> str:
    """Return the first ``step`` sections, optionally leaving one out."""
    return compose_system_prompt(step, omit=omit)
