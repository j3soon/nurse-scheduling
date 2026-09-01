"""Tests for the AI-facing Bash policy layer over raw sandbox operations."""

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
import json

from nurse_scheduling.ai.bash_tool import BASH_TOOL, BashToolLimits, SandboxBashTool
from nurse_scheduling.ai.sandbox import CommandResult
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend


def _limits(**overrides: int) -> BashToolLimits:
    values = {
        "max_command_chars": 20,
        "max_stdout_chars": 40,
        "max_stderr_chars": 30,
        "max_output_chars": 50,
    }
    values.update(overrides)
    return BashToolLimits(**values)


def test_bash_tool_bounds_raw_backend_output_for_model_context():
    backend = FakeSandboxBackend(
        "fake-1",
        command_handler=lambda *_: CommandResult("a" * 100, "b" * 100, 2),
    )
    tool = SandboxBashTool(backend, _limits())

    outcome = asyncio.run(tool.execute(BASH_TOOL, json.dumps({"command": "rg people"})))

    stdout = outcome.text.split("stdout:\n", 1)[1].split("\nstderr:\n", 1)[0]
    stderr = outcome.text.split("\nstderr:\n", 1)[1]
    assert len(stdout) <= 40
    assert len(stderr) <= 30
    assert len(stdout) + len(stderr) <= 50
    assert "truncated" in stdout
    assert "truncated" in stderr
    assert not outcome.ok
    assert backend.commands == [("rg people", None)]


def test_bash_tool_rejects_invalid_arguments_without_using_the_backend():
    backend = FakeSandboxBackend("fake-1")
    tool = SandboxBashTool(backend, _limits())

    invalid_json = asyncio.run(tool.execute(BASH_TOOL, "{"))
    extra_argument = asyncio.run(tool.execute(BASH_TOOL, '{"command":"rg x","path":"/"}'))
    too_long = asyncio.run(tool.execute(BASH_TOOL, json.dumps({"command": "x" * 21})))
    unknown = asyncio.run(tool.execute("e2b_run", '{"command":"rg x"}'))

    assert not invalid_json.ok
    assert not extra_argument.ok
    assert not too_long.ok
    assert not unknown.ok
    assert backend.commands == []


def test_bash_tool_reports_structured_timeout_as_a_failed_call():
    backend = FakeSandboxBackend(
        "fake-1",
        command_handler=lambda *_: CommandResult("", "timed out", 124, timed_out=True),
    )
    tool = SandboxBashTool(backend, _limits())

    outcome = asyncio.run(tool.execute(BASH_TOOL, '{"command":"sleep 9"}'))

    assert not outcome.ok
    assert "exit_code: 124" in outcome.text
    assert "timed_out: true" in outcome.text


def test_backend_itself_still_has_the_complete_unbounded_output():
    backend = FakeSandboxBackend(
        "fake-1",
        command_handler=lambda *_: CommandResult("a" * 100, "b" * 100, 0),
    )
    tool = SandboxBashTool(backend, _limits())

    raw = asyncio.run(backend.run("raw"))
    bounded = asyncio.run(tool.execute(BASH_TOOL, '{"command":"bounded"}'))

    assert raw.stdout == "a" * 100
    assert raw.stderr == "b" * 100
    assert len(bounded.text) < len(raw.stdout) + len(raw.stderr)
