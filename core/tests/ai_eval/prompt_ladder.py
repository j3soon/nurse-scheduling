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
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nurse_scheduling.ai.sandbox_agent import SANDBOX_SYSTEM_PROMPT

STEPS_PATH = Path(__file__).with_name("prompt_steps.json")


@dataclass(frozen=True)
class PromptStep:
    """One paragraph and the cases intended to show its marginal benefit."""

    id: str
    starts_with: str
    cases: tuple[str, ...]
    hypothesis: str
    sha256: str
    evidence: tuple[dict[str, str], ...] = ()
    gaps: tuple[str, ...] = ()


def prompt_paragraphs(prompt: str = SANDBOX_SYSTEM_PROMPT) -> tuple[str, ...]:
    """Preserve the production paragraph boundaries exactly."""
    return tuple(prompt.split("\n\n")) if prompt else ()


def load_prompt_steps(path: Path = STEPS_PATH) -> tuple[PromptStep, ...]:
    """Fail if the evidence ledger no longer matches the production prompt."""
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise TypeError("Prompt steps must be a JSON list")
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
    paragraphs = prompt_paragraphs()
    if len(steps) != len(paragraphs):
        raise ValueError(f"Prompt has {len(paragraphs)} paragraphs but ledger has {len(steps)} steps")
    if len({step.id for step in steps}) != len(steps):
        raise ValueError("Prompt step IDs must be unique")
    for index, (step, paragraph) in enumerate(zip(steps, paragraphs, strict=True), 1):
        if not step.id or not step.starts_with or not step.hypothesis or not (step.cases or step.gaps):
            raise ValueError(f"Prompt step {index} needs an ID, anchor, hypothesis, and cases or gaps")
        if not paragraph.startswith(step.starts_with):
            raise ValueError(f"Prompt step {index} ({step.id}) no longer matches its paragraph")
        if hashlib.sha256(paragraph.encode()).hexdigest() != step.sha256:
            raise ValueError(f"Prompt step {index} ({step.id}) changed. Update its hypothesis and evidence")
        if any(record.get("case") not in step.cases for record in step.evidence):
            raise ValueError(f"Prompt step {index} evidence must name one of its targeted cases")
    return steps


def prompt_at_step(step: int, *, omit: int | None = None) -> str:
    """Return the first ``step`` paragraphs, optionally leaving one out."""
    paragraphs = prompt_paragraphs()
    if step < 0 or step > len(paragraphs):
        raise ValueError(f"Prompt step must be between 0 and {len(paragraphs)}")
    if omit is not None and (omit < 1 or omit > step):
        raise ValueError("Omitted paragraph must be included in the selected prompt step")
    return "\n\n".join(paragraph for index, paragraph in enumerate(paragraphs[:step], 1) if index != omit)
