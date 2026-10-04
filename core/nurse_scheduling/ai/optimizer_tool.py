"""Model-facing optimizer arguments, tool definitions, and result formatting."""

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

# This code is mostly AI generated.

import json
from typing import Any, Literal

from .agent_types import AgentToolResult
from .optimizer import (
    OPTIMIZER_TOOL,
    WORKSPACE_OPTIMIZER_RESULT,
    OptimizerError,
    SessionOptimization,
    SessionOptimizer,
    valid_optimizer_timeout,
)


def optimizer_start_message(job_id: str, source_sha256: str) -> str:
    """Render the startup acknowledgement shared by production and controlled evaluations."""
    return (
        f"Started optimizer job {job_id} in the background for schedule SHA-256 {source_sha256}. "
        "The assistant will be woken when it finishes. The user can keep chatting meanwhile."
    )


def parse_optimizer_arguments(arguments: str) -> tuple[Literal["start", "status", "finish_now"], int | None]:
    """Validate before workspace allocation or service calls, preserving tool wording."""
    try:
        raw = json.loads(arguments or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Optimizer arguments must be valid JSON.") from exc
    if not isinstance(raw, dict):
        raise TypeError("Optimizer arguments must be a JSON object.")
    action = raw.get("action", "start")
    if action not in ("start", "status", "finish_now"):
        raise ValueError("action must be one of: start, status, finish_now.")
    timeout = raw.get("timeout_seconds") if action == "start" else None
    if not valid_optimizer_timeout(timeout):
        raise ValueError("timeout_seconds must be a positive integer.")
    return action, timeout


async def execute_optimizer_tool(
    optimizer: SessionOptimizer, session_id: str, schedule_yaml: str, arguments: str
) -> AgentToolResult:
    """Adapt model input to domain operations and domain results to tool content."""
    try:
        action, timeout = parse_optimizer_arguments(arguments)
    except (TypeError, ValueError) as exc:
        return AgentToolResult(str(exc), False)
    try:
        if action == "start":
            job = await optimizer.start(session_id, schedule_yaml, timeout)
            if job is None:
                return AgentToolResult("This chat session expired while the optimizer job was starting.", False)
            text = optimizer_start_message(job.id, job.source_sha256)
        elif action == "status":
            text = _job_summary(optimizer.status(session_id))
        else:
            job, requested = await optimizer.finish_now(session_id)
            text = (
                f"Asked optimizer job {job.id} to finish with its best available result. Current state: {job.payload.state}."
                if requested
                else _job_summary(job)
            )
        return AgentToolResult(text, True)
    except OptimizerError as exc:
        return AgentToolResult(str(exc), False)


def optimizer_tool_definition(default_timeout_seconds: int = 300) -> dict[str, Any]:
    """Return the single model-facing contract for optimizer lifecycle actions."""
    return {
        "type": "function",
        "function": {
            "name": OPTIMIZER_TOOL,
            "description": (
                "Start the scheduling optimizer on the current working YAML, inspect its background status, or ask "
                "a running optimizer to finish with its best available solution. Start returns immediately. "
                "When asked only to optimize the current schedule, call start without preliminary schedule or reference reads. "
                f"A completed workbook is available at {WORKSPACE_OPTIMIZER_RESULT} in the next assistant run. "
                "Omit timeout_seconds to use the configured default."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["start", "status", "finish_now"]},
                    "timeout_seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "description": f"Optional optimizer time limit in seconds. Default: {default_timeout_seconds} seconds.",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    }


def _job_summary(job: SessionOptimization) -> str:
    details = job.payload.result or job.payload.error
    suffix = f" Result: {json.dumps(details, ensure_ascii=False)}" if details else ""
    return f"Optimizer job {job.id} is {job.payload.state}.{suffix}"
