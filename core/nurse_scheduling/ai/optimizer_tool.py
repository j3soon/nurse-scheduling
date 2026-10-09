"""Model-facing optimizer arguments and replies above typed job operations."""

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

import json
from typing import Any

from .agent_types import AgentToolOutcome
from .optimizer import OPTIMIZER_TOOL, WORKSPACE_OPTIMIZER_RESULT, OptimizerError, SessionOptimization, SessionOptimizer


def optimizer_start_message(job_id: str, source_sha256: str) -> str:
    """Render the startup acknowledgement shared by production and controlled evaluations."""
    return (
        f"Started optimizer job {job_id} in the background for schedule SHA-256 {source_sha256}. "
        "The assistant will be woken when it finishes. The user can keep chatting meanwhile."
    )


async def execute_optimizer_tool(
    optimizer: SessionOptimizer, session_id: str, schedule_yaml: str, arguments: str
) -> AgentToolOutcome:
    """Parse model arguments, call a job operation, and format the existing reply."""
    try:
        raw = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return AgentToolOutcome("Optimizer arguments must be valid JSON.", False)
    if not isinstance(raw, dict):
        return AgentToolOutcome("Optimizer arguments must be a JSON object.", False)
    action = raw.get("action", "start")
    try:
        if action == "start":
            timeout = raw.get("timeout_seconds")
            if timeout is not None and (isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0):
                return AgentToolOutcome("timeout_seconds must be a positive integer.", False)
            job = await optimizer.start(session_id, schedule_yaml, timeout)
            return AgentToolOutcome(optimizer_start_message(job.id, job.source_sha256), True)
        if action == "status":
            return AgentToolOutcome(_job_summary(optimizer.status(session_id)), True)
        if action == "finish_now":
            job, requested = await optimizer.finish_now(session_id)
            text = (
                f"Asked optimizer job {job.id} to finish with its best available result. Current state: {job.payload.state}."
                if requested
                else _job_summary(job)
            )
            return AgentToolOutcome(text, True)
    except OptimizerError as exc:
        return AgentToolOutcome(str(exc), False)
    return AgentToolOutcome("action must be one of: start, status, finish_now.", False)


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
                f"A completed workbook is available at {WORKSPACE_OPTIMIZER_RESULT} in the next assistant turn. "
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
