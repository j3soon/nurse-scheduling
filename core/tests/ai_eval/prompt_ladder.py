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
import inspect
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from nurse_scheduling.ai.system_prompt import (
    PROMPT_STEPS_PATH,
    compose_system_prompt,
    load_system_prompt_entries,
    load_system_prompt_sections,
)

from .attachment_fixtures import load_attachment_fixtures
from .grading import EvalCase

STEPS_PATH = PROMPT_STEPS_PATH


@dataclass(frozen=True)
class PromptStep:
    """One prompt section and the cases intended to show its marginal benefit."""

    id: str
    file: str
    cases: tuple[str, ...]
    hypothesis: str
    sha256: str
    evidence: tuple[dict[str, Any], ...] = ()
    comparison_mode: str = "adjacent"


def load_prompt_steps(path: Path = STEPS_PATH) -> tuple[PromptStep, ...]:
    """Fail if the evidence ledger no longer matches the production prompt."""
    raw = load_system_prompt_entries(path)
    steps = tuple(
        PromptStep(
            **{
                **item,
                "cases": tuple(item["cases"]),
                "evidence": tuple(item.get("evidence", ())),
            }
        )
        for item in raw
    )
    sections = load_system_prompt_sections(raw)
    for index, (step, section) in enumerate(zip(steps, sections, strict=True), 1):
        if not step.id or not step.hypothesis:
            raise ValueError(f"Prompt step {index} needs an ID and hypothesis")
        if step.comparison_mode not in {"adjacent", "ablation"}:
            raise ValueError(f"Prompt step {index} has an invalid comparison mode")
        if hashlib.sha256(section.encode()).hexdigest() != step.sha256:
            raise ValueError(f"Prompt step {index} ({step.id}) changed. Update its hypothesis and evidence")
        if any(record.get("case") not in step.cases for record in step.evidence):
            raise ValueError(f"Prompt step {index} evidence must name one of its targeted cases")
    return steps


def prompt_at_step(step: int, *, omit: int | None = None) -> str:
    """Return the first ``step`` sections, optionally leaving one out."""
    return compose_system_prompt(step, omit=omit)


def case_digest(case: EvalCase) -> str:
    """Bind a receipt to the parsed input and grading contract, not JSON formatting."""
    fields = asdict(case)
    for optional in (
        "optimizer_completion",
        "optimizer_completion_only",
        "answer_json",
        "download_files",
        "import_attachment",
    ):
        if not fields[optional]:
            fields.pop(optional)
    if any(isinstance(value, dict) for value in case.answer_json.values()):
        from .grading import _answer_json_matches

        fields["nested_json_oracle_sha256"] = hashlib.sha256(
            inspect.getsource(_answer_json_matches).encode()
        ).hexdigest()
    if case.import_attachment:
        from .grading import _check_import_schedule

        fields["import_oracle_sha256"] = hashlib.sha256(inspect.getsource(_check_import_schedule).encode()).hexdigest()
    helper_names = set()
    if case.optimizer_completion:
        from nurse_scheduling.ai.result_context import _project_context

        from .optimizer_fixtures import RESULT_SOURCES, fixture_digest

        fields["optimizer_fixture_sha256"] = fixture_digest(case.optimizer_completion)
        fields["request_context_sha256"] = hashlib.sha256(inspect.getsource(_project_context).encode()).hexdigest()
        helper_names.update(("inspect_optimizer_result.py", "inspect_xlsx.py"))
        from nurse_scheduling.loader import _load_yaml

        if any(
            p["type"] in {"shift type requirement", "shift type successions"}
            for p in _load_yaml(RESULT_SOURCES[case.optimizer_completion].read_bytes()).get("preferences", [])
        ):
            from nurse_scheduling.ai.result_context import build_result_context
            from nurse_scheduling.preference_audit import audit_staffing_and_successions
            from nurse_scheduling.preference_types import (
                iter_succession_patterns,
                staffing_expression,
            )

            fields["policy_context_sha256"] = hashlib.sha256(
                Path(build_result_context.__code__.co_filename).read_text(encoding="utf-8").encode()
            ).hexdigest()
            fields["policy_audit_sha256"] = hashlib.sha256(
                Path(audit_staffing_and_successions.__code__.co_filename).read_text(encoding="utf-8").encode()
                + inspect.getsource(iter_succession_patterns).encode()
                + inspect.getsource(staffing_expression).encode()
            ).hexdigest()
    if "request-inspection" in case.tags:
        from nurse_scheduling.ai.attachment_tools.inspect_optimizer_result import _weight, _weight_arguments
        from nurse_scheduling.ai.result_context import _project_context

        fields["request_context_sha256"] = hashlib.sha256(inspect.getsource(_project_context).encode()).hexdigest()
        fields["request_weight_parser_sha256"] = hashlib.sha256(
            inspect.getsource(_weight).encode() + inspect.getsource(_weight_arguments).encode()
        ).hexdigest()
        helper_names.add("inspect_shift_requests.py")
    if "request-tier-inventory" in case.tags:
        helper_names.add("inspect_request_tiers.py")
    if not case.semantic_check:
        # An optional oracle must not invalidate receipts for unrelated cases.
        fields.pop("semantic_check")
    if case.semantic_check == "optimizer-start-source":
        from .grading import _check_optimizer_start_source

        fields["optimizer_input_oracle_sha256"] = hashlib.sha256(
            inspect.getsource(_check_optimizer_start_source).encode()
        ).hexdigest()
    if case.semantic_check == "yaml-generator":
        fields["generator_sha256"] = [
            hashlib.sha256(attachment.data).hexdigest() for attachment in load_attachment_fixtures(case.attachments)
        ]
    elif case.attachments:
        attachments = load_attachment_fixtures(case.attachments)
        fields["attachments_sha256"] = [hashlib.sha256(attachment.data).hexdigest() for attachment in attachments]
        for attachment in attachments:
            if attachment.media_type == "application/pdf":
                helper_names.add("inspect_pdf.py")
            elif attachment.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                helper_names.add("inspect_xlsx.py")
    if "xlsx-overview" in case.tags:
        helper_names.add("inspect_xlsx.py")
    if "pdf-find" in case.tags:
        helper_names.add("inspect_pdf.py")
    if helper_names:
        from nurse_scheduling.ai.sandbox_agent import (
            INSPECTION_HELPERS,
            REFERENCE_ATTACHMENT_TOOLS,
            inspection_helper_catalog,
        )

        fields["inspection_helpers_sha256"] = {
            name: hashlib.sha256(
                REFERENCE_ATTACHMENT_TOOLS[f"/reference/tools/{name}"].read_text(encoding="utf-8").encode()
            ).hexdigest()
            for name in sorted(helper_names)
        }
        fields["helper_catalog_sha256"] = hashlib.sha256(
            inspect.getsource(inspection_helper_catalog).encode()
            + json.dumps(
                {name: INSPECTION_HELPERS[name] for name in sorted(helper_names)},
                sort_keys=True,
            ).encode()
        ).hexdigest()
    return hashlib.sha256(json.dumps(fields, sort_keys=True, default=str).encode()).hexdigest()


def evidence_input_digest(step: PromptStep, case: EvalCase, fixture_digest: str) -> str:
    """Keep one portable fingerprint for the clause and its test inputs."""
    inputs = {
        "clause": step.sha256,
        "case": case_digest(case),
        "fixture": fixture_digest,
    }
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


def validate_prompt_evidence(
    steps: tuple[PromptStep, ...],
    cases: Mapping[str, EvalCase],
    fixture_digests: Mapping[str, str],
) -> None:
    """Require a clean repeated witness for each shipped clause.

    Enforce this in CI, not candidate loading. New prompt variants must remain runnable
    before they have evidence. Bind each receipt to its own clause and case, while
    keeping full prompt contexts and run metadata in ignored evaluation artifacts.
    """
    for step in steps:
        if not step.evidence:
            raise ValueError(f"Prompt step {step.id} has no benefit witness")
        for record in step.evidence:
            label = f"Prompt step {step.id} evidence"
            if record.get("infrastructure_errors") != 0:
                raise ValueError(f"{label} is inconclusive due to infrastructure errors")
            if not isinstance(record.get("model"), str) or not record["model"]:
                raise ValueError(f"{label} needs the evaluated model")
            before, after, _ = _receipt_counts(record, label)
            if before == after:
                ratio, target = record.get("cost_ratio"), record.get("cost_target")
                if not (
                    isinstance(ratio, (int, float))
                    and isinstance(target, (int, float))
                    and 0 < ratio <= target < 1
                    and record.get("cost_metric")
                    in {
                        "tool-calls",
                        "turns",
                        "uncached-tokens",
                        "completion-tokens",
                        "total-tokens",
                        "seconds",
                    }
                ):
                    raise ValueError(f"{label} shows no measured benefit")
            for observation in (record, *record.get("controls", [])):
                if observation.get("case") not in step.cases or observation.get("case") not in cases:
                    raise ValueError(f"{label} names an unlinked testcase")
                case = cases[observation["case"]]
                if case.fixture not in fixture_digests or observation.get("input_sha256") != evidence_input_digest(
                    step, case, fixture_digests[case.fixture]
                ):
                    raise ValueError(f"{label} has stale clause, testcase, or fixture inputs")
                # A targeted extension need not rerun controls already verified in
                # a smaller paired batch. Each observation still needs 3–10 trials.
                _receipt_counts(observation, label)


def _receipt_counts(record: dict[str, Any], label: str) -> tuple[int, int, int]:
    try:
        before, before_total = (int(value) for value in record["before"].split("/"))
        after, after_total = (int(value) for value in record["after"].split("/"))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"{label} needs paired pass counts") from exc
    if (
        not 3 <= before_total <= 10
        or before_total != after_total
        or not 0 <= before <= before_total
        or after != after_total
    ):
        raise ValueError(f"{label} needs three to ten paired runs with all after attempts passing")
    if record.get("infrastructure_errors", 0) != 0:
        raise ValueError(f"{label} is inconclusive due to infrastructure errors")
    return before, after, before_total
