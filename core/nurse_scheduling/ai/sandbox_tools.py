"""Adapt selected Pi tools to a disposable sandbox and our agent loop."""

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

import posixpath
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
from .pi.edit import (
    EDIT_TOOL,
    EDIT_TOOL_DESCRIPTION,
    EditApplyError,
    EditArgumentError,
    apply_edit,
    edit_parameters,
    parse_edit_input,
    render_edit_result,
)
from .pi.read import (
    READ_TOOL,
    READ_TOOL_DESCRIPTION,
    ReadArgumentError,
    parse_read_input,
    read_parameters,
    render_read_result,
)
from .pi.write import (
    WRITE_TOOL,
    WRITE_TOOL_DESCRIPTION,
    WriteArgumentError,
    parse_write_input,
    render_write_result,
    write_parameters,
)
from .sandbox import SandboxBackend, SandboxFileNotFoundError

FULL_OUTPUT_DIRECTORY = "/tmp"
SANDBOX_WORKSPACE = "/workspace"
TOOL_NAMES = (READ_TOOL, BASH_TOOL, EDIT_TOOL, WRITE_TOOL)


class SandboxPiTools:
    """Keep sandbox and application policy outside the Pi-derived behavior."""

    def __init__(self, sandbox: SandboxBackend, command_timeout_seconds: float) -> None:
        if command_timeout_seconds <= 0:
            raise ValueError("command_timeout_seconds must be positive")
        self._sandbox = sandbox
        self._command_timeout_seconds = command_timeout_seconds

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return [
            _tool_definition(READ_TOOL, READ_TOOL_DESCRIPTION, read_parameters()),
            _tool_definition(BASH_TOOL, BASH_TOOL_DESCRIPTION, bash_parameters()),
            _tool_definition(EDIT_TOOL, EDIT_TOOL_DESCRIPTION, edit_parameters()),
            _tool_definition(WRITE_TOOL, WRITE_TOOL_DESCRIPTION, write_parameters()),
        ]

    async def execute(self, name: str, arguments: str) -> AgentToolOutcome:
        """Run one validated Pi-compatible tool call inside the sandbox."""
        if name == READ_TOOL:
            return await self._read(arguments)
        if name == BASH_TOOL:
            return await self._bash(arguments)
        if name == EDIT_TOOL:
            return await self._edit(arguments)
        if name == WRITE_TOOL:
            return await self._write(arguments)
        return AgentToolOutcome(
            f"Unknown tool `{name}`. Available tools: {', '.join(TOOL_NAMES)}.",
            False,
        )

    async def _read(self, arguments: str) -> AgentToolOutcome:
        try:
            call = parse_read_input(arguments)
        except ReadArgumentError as exc:
            return AgentToolOutcome(str(exc), False)
        try:
            content = await self._sandbox.read_file(_resolve_path(call.path))
        except SandboxFileNotFoundError as exc:
            return AgentToolOutcome(str(exc), False)
        try:
            result = render_read_result(content, call)
        except ReadArgumentError as exc:
            return AgentToolOutcome(str(exc), False)
        return AgentToolOutcome(result.text, True)

    async def _bash(self, arguments: str) -> AgentToolOutcome:
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

    async def _edit(self, arguments: str) -> AgentToolOutcome:
        try:
            call = parse_edit_input(arguments)
        except EditArgumentError as exc:
            return AgentToolOutcome(str(exc), False)
        path = _resolve_path(call.path)
        try:
            content = await self._sandbox.read_file(path)
        except SandboxFileNotFoundError as exc:
            return AgentToolOutcome(str(exc), False)
        try:
            edited = apply_edit(content, call)
        except EditApplyError as exc:
            return AgentToolOutcome(str(exc), False)
        await self._sandbox.write_file(path, edited)
        return AgentToolOutcome(render_edit_result(call.path, len(call.edits)), True)

    async def _write(self, arguments: str) -> AgentToolOutcome:
        try:
            call = parse_write_input(arguments)
        except WriteArgumentError as exc:
            return AgentToolOutcome(str(exc), False)
        await self._sandbox.write_file(_resolve_path(call.path), call.content)
        return AgentToolOutcome(render_write_result(call.path), True)


def _tool_definition(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def _resolve_path(path: str) -> str:
    if posixpath.isabs(path):
        return posixpath.normpath(path)
    return posixpath.normpath(posixpath.join(SANDBOX_WORKSPACE, path))
