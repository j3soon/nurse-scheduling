"""Tests for the thin adapter between Pi Bash and a disposable sandbox."""

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

import asyncio
import re

from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.sandbox import CommandResult
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend
from nurse_scheduling.ai.sandbox_bash import SandboxBashTool


def test_sandbox_bash_exposes_pi_tool_definition():
    tool = SandboxBashTool(FakeSandboxBackend("fake-1"), 10)

    definition = tool.definitions[0]["function"]

    assert definition["name"] == BASH_TOOL
    assert "last 2000 lines or 50KB" in definition["description"]
    assert set(definition["parameters"]["properties"]) == {"command", "timeout"}


def test_sandbox_bash_combines_output_and_formats_nonzero_exit_like_pi():
    backend = FakeSandboxBackend(
        "fake-1",
        command_handler=lambda *_: CommandResult("stdout\n", "stderr\n", 7),
    )
    tool = SandboxBashTool(backend, 10)

    outcome = asyncio.run(tool.execute(BASH_TOOL, '{"command":"rg missing"}'))

    assert outcome.text == "stdout\nstderr\n\n\nCommand exited with code 7"
    assert not outcome.ok
    assert backend.commands == [("rg missing", None)]


def test_sandbox_bash_caps_model_timeout_at_the_server_limit():
    backend = FakeSandboxBackend(
        "fake-1",
        command_handler=lambda *_: CommandResult("", "", 124, timed_out=True),
    )
    tool = SandboxBashTool(backend, 10)

    outcome = asyncio.run(tool.execute(BASH_TOOL, '{"command":"sleep 30","timeout":30}'))

    assert outcome.text == "Command timed out after 10 seconds"
    assert not outcome.ok
    assert backend.commands == [("sleep 30", 10)]


def test_sandbox_bash_persists_full_output_when_pi_truncates_it():
    full_output = "".join(f"line-{line}\n" for line in range(3_000))
    backend = FakeSandboxBackend(
        "fake-1",
        command_handler=lambda *_: CommandResult(full_output, "", 0),
    )
    tool = SandboxBashTool(backend, 10)

    outcome = asyncio.run(tool.execute(BASH_TOOL, '{"command":"seq 3000"}'))

    match = re.search(r"Full output: (/tmp/pi-bash-[a-f0-9]{16}\.log)", outcome.text)
    assert match is not None
    assert outcome.text.startswith("line-1000\n")
    assert "line-2999" in outcome.text
    assert backend.files[match.group(1)] == full_output.encode()
    assert outcome.ok


def test_sandbox_bash_rejects_bad_envelopes_without_running_a_command():
    backend = FakeSandboxBackend("fake-1")
    tool = SandboxBashTool(backend, 10)

    invalid_json = asyncio.run(tool.execute(BASH_TOOL, "{"))
    missing_command = asyncio.run(tool.execute(BASH_TOOL, '{"timeout":2}'))
    unknown = asyncio.run(tool.execute("e2b_run", '{"command":"rg x"}'))

    assert not invalid_json.ok
    assert not missing_command.ok
    assert not unknown.ok
    assert backend.commands == []
