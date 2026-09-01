"""The bounded Bash tool exposed over a raw disposable sandbox."""

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
from dataclasses import dataclass
from typing import Any

from .agent import AgentToolOutcome
from .sandbox import SandboxBackend

BASH_TOOL = "bash"


@dataclass(frozen=True)
class BashToolLimits:
    """AI-context limits that intentionally do not belong to a backend."""

    max_command_chars: int
    max_stdout_chars: int
    max_stderr_chars: int
    max_output_chars: int

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")


class SandboxBashTool:
    """Expose only Bash while bounding what reaches the model."""

    def __init__(self, sandbox: SandboxBackend, limits: BashToolLimits) -> None:
        self._sandbox = sandbox
        self._limits = limits

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": BASH_TOOL,
                    "description": (
                        "Run one foreground shell command in the temporary schedule workspace. "
                        "Use ordinary Bash, Python, rg, sed, grep, and diff commands."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": self._limits.max_command_chars,
                            }
                        },
                        "required": ["command"],
                        "additionalProperties": False,
                    },
                },
            }
        ]

    async def execute(self, name: str, arguments: str) -> AgentToolOutcome:
        """Validate one model call, execute it, and bound its context output."""
        if name != BASH_TOOL:
            return AgentToolOutcome(f"Unknown tool `{name}`. Available tool: {BASH_TOOL}.", False)
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError as exc:
            return AgentToolOutcome(f"Tool arguments are not valid JSON: {exc.msg}.", False)
        if not isinstance(parsed, dict) or set(parsed) != {"command"}:
            return AgentToolOutcome("Tool arguments must contain only the required `command` string.", False)
        command = parsed["command"]
        if not isinstance(command, str) or not command.strip():
            return AgentToolOutcome("`command` must be a non-empty string.", False)
        if len(command) > self._limits.max_command_chars:
            return AgentToolOutcome(
                f"`command` exceeds the AI tool limit of {self._limits.max_command_chars} characters.",
                False,
            )

        result = await self._sandbox.run(command)
        stdout, stderr = _bound_outputs(result.stdout, result.stderr, self._limits)
        rendered = (
            f"exit_code: {result.exit_code}\n"
            f"timed_out: {str(result.timed_out).lower()}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )
        return AgentToolOutcome(rendered, result.exit_code == 0 and not result.timed_out)


def _bound_outputs(stdout: str, stderr: str, limits: BashToolLimits) -> tuple[str, str]:
    """Bound both streams individually and together for model context."""
    stderr = _truncate(stderr, limits.max_stderr_chars, "stderr")
    stdout_budget = min(limits.max_stdout_chars, max(0, limits.max_output_chars - len(stderr)))
    stdout = _truncate(stdout, stdout_budget, "stdout")
    remaining = max(0, limits.max_output_chars - len(stdout))
    stderr = _truncate(stderr, remaining, "stderr")
    return stdout, stderr


def _truncate(value: str, max_chars: int, stream: str) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= 0:
        return ""
    marker = f"\n[{stream} truncated at {max_chars}-character AI limit]"
    if len(marker) >= max_chars:
        return marker[:max_chars]
    return value[: max_chars - len(marker)] + marker
