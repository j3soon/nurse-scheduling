"""Tests for the thin adapter between selected Pi tools and a disposable sandbox."""

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

import pytest

from nurse_scheduling.ai.pi.bash import BASH_TOOL
from nurse_scheduling.ai.pi.read import READ_TOOL
from nurse_scheduling.ai.pi.write import WRITE_TOOL
from nurse_scheduling.ai.sandbox import CommandResult, SandboxError
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend
from nurse_scheduling.ai.sandbox_tools import SandboxPiTools


def test_sandbox_adapter_exposes_only_selected_pi_tool_definitions():
    tools = SandboxPiTools(FakeSandboxBackend("fake-1"), 10)

    definitions = [definition["function"] for definition in tools.definitions]

    assert [definition["name"] for definition in definitions] == [READ_TOOL, BASH_TOOL, WRITE_TOOL]
    assert "2000 lines or 50KB" in definitions[0]["description"]
    assert "last 2000 lines or 50KB" in definitions[1]["description"]
    assert "overwrites if it does" in definitions[2]["description"]


def test_sandbox_read_resolves_relative_paths_and_formats_ranges_like_pi():
    backend = FakeSandboxBackend("fake-1", initial_files={"/workspace/notes.txt": b"one\ntwo\nthree"})
    tools = SandboxPiTools(backend, 10)

    outcome = asyncio.run(tools.execute(READ_TOOL, '{"path":"notes.txt","limit":2}'))

    assert outcome.text == "one\ntwo\n\n[1 more lines in file. Use offset=3 to continue.]"
    assert outcome.ok


def test_sandbox_read_reports_a_missing_file_without_failing_the_sandbox():
    backend = FakeSandboxBackend("fake-1")
    tools = SandboxPiTools(backend, 10)

    outcome = asyncio.run(tools.execute(READ_TOOL, '{"path":"missing.txt"}'))

    assert outcome.text == "Sandbox file not found: /workspace/missing.txt"
    assert not outcome.ok
    assert not backend.closed


def test_sandbox_write_resolves_relative_paths_and_overwrites_the_complete_file():
    backend = FakeSandboxBackend("fake-1", initial_files={"/workspace/notes.txt": b"old"})
    tools = SandboxPiTools(backend, 10)

    outcome = asyncio.run(tools.execute(WRITE_TOOL, '{"path":"notes.txt","content":"new"}'))

    assert outcome.text == "Successfully wrote to notes.txt"
    assert outcome.ok
    assert backend.files["/workspace/notes.txt"] == b"new"


def test_sandbox_bash_combines_output_and_formats_nonzero_exit_like_pi():
    backend = FakeSandboxBackend(
        "fake-1",
        command_handler=lambda *_: CommandResult("stdout\n", "stderr\n", 7),
    )
    tools = SandboxPiTools(backend, 10)

    outcome = asyncio.run(tools.execute(BASH_TOOL, '{"command":"rg missing"}'))

    assert outcome.text == "stdout\nstderr\n\n\nCommand exited with code 7"
    assert not outcome.ok
    assert backend.commands == [("rg missing", None)]


def test_sandbox_bash_caps_model_timeout_at_the_server_limit():
    backend = FakeSandboxBackend(
        "fake-1",
        command_handler=lambda *_: CommandResult("", "", 124, timed_out=True),
    )
    tools = SandboxPiTools(backend, 10)

    outcome = asyncio.run(tools.execute(BASH_TOOL, '{"command":"sleep 30","timeout":30}'))

    assert outcome.text == "Command timed out after 10 seconds"
    assert not outcome.ok
    assert backend.commands == [("sleep 30", 10)]


def test_sandbox_bash_persists_full_output_when_pi_truncates_it():
    full_output = "".join(f"line-{line}\n" for line in range(3_000))
    backend = FakeSandboxBackend(
        "fake-1",
        command_handler=lambda *_: CommandResult(full_output, "", 0),
    )
    tools = SandboxPiTools(backend, 10)

    outcome = asyncio.run(tools.execute(BASH_TOOL, '{"command":"seq 3000"}'))

    match = re.search(r"Full output: (/tmp/pi-bash-[a-f0-9]{16}\.log)", outcome.text)
    assert match is not None
    assert outcome.text.startswith("line-1000\n")
    assert "line-2999" in outcome.text
    assert backend.files[match.group(1)] == full_output.encode()
    assert outcome.ok


def test_sandbox_adapter_rejects_bad_envelopes_without_touching_the_sandbox():
    backend = FakeSandboxBackend("fake-1")
    tools = SandboxPiTools(backend, 10)

    invalid_json = asyncio.run(tools.execute(BASH_TOOL, "{"))
    missing_path = asyncio.run(tools.execute(READ_TOOL, '{}'))
    missing_content = asyncio.run(tools.execute(WRITE_TOOL, '{"path":"new.txt"}'))
    unknown = asyncio.run(tools.execute("e2b_run", '{"command":"rg x"}'))

    assert not invalid_json.ok
    assert not missing_path.ok
    assert not missing_content.ok
    assert not unknown.ok
    assert backend.commands == []
    assert backend.files == {}


def test_sandbox_service_failures_still_fail_the_turn():
    class FailingReadBackend(FakeSandboxBackend):
        async def read_file(self, path: str) -> bytes:
            raise SandboxError(f"service failed reading {path}")

    tools = SandboxPiTools(FailingReadBackend("fake-1"), 10)

    with pytest.raises(SandboxError, match="service failed reading"):
        asyncio.run(tools.execute(READ_TOOL, '{"path":"notes.txt"}'))
