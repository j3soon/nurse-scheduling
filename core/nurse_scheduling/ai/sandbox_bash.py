"""Adapt Pi's Bash behavior to a disposable sandbox and our agent loop."""

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

import secrets
from typing import Any

from .agent import AgentToolOutcome
from .pi.bash import (
    BASH_TOOL,
    BASH_TOOL_DESCRIPTION,
    BashArgumentError,
    bash_parameters,
    parse_bash_input,
    prepare_bash_output,
    render_bash_result,
)
from .sandbox import SandboxBackend

FULL_OUTPUT_DIRECTORY = "/tmp"


class SandboxBashTool:
    """Keep application policy outside the Pi-derived Bash implementation."""

    def __init__(self, sandbox: SandboxBackend, command_timeout_seconds: float) -> None:
        if command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds must be positive")
        self._sandbox = sandbox
        self._command_timeout_seconds = command_timeout_seconds

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": BASH_TOOL,
                    "description": BASH_TOOL_DESCRIPTION,
                    "parameters": bash_parameters(),
                },
            }
        ]

    async def execute(self, name: str, arguments: str) -> AgentToolOutcome:
        """Run one validated Pi-compatible Bash call inside the sandbox."""
        if name != BASH_TOOL:
            return AgentToolOutcome(f"Unknown tool `{name}`. Available tool: {BASH_TOOL}.", False)
        try:
            call = parse_bash_input(arguments)
        except BashArgumentError as exc:
            return AgentToolOutcome(str(exc), False)

        requested_timeout = call.timeout
        effective_timeout = (
            min(requested_timeout, self._command_timeout_seconds) if requested_timeout is not None else None
        )
        result = await self._sandbox.run(call.command, timeout_seconds=effective_timeout)
        full_output = result.stdout + result.stderr
        prepared = prepare_bash_output(full_output)
        full_output_path: str | None = None
        if prepared.truncation.truncated:
            full_output_path = f"{FULL_OUTPUT_DIRECTORY}/pi-bash-{secrets.token_hex(8)}.log"
            await self._sandbox.write_file(full_output_path, full_output)

        rendered = render_bash_result(
            prepared,
            full_output_path=full_output_path,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            timeout_seconds=effective_timeout or self._command_timeout_seconds,
        )
        return AgentToolOutcome(rendered.text, rendered.ok)
