"""Tests for the E2B Cloud implementation of the AI sandbox contract."""

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
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from e2b.exceptions import TimeoutException
from e2b.sandbox.commands.command_handle import CommandExitException

from nurse_scheduling.ai.sandbox import SandboxError
from nurse_scheduling.ai.sandbox.e2b import COMMAND_TIMEOUT_EXIT_CODE, E2BSandboxBackend, E2BSandboxFactory


class FakeE2BSandbox:
    def __init__(self) -> None:
        self.sandbox_id = "sandbox-123"
        self.files = SimpleNamespace(write=AsyncMock(), read=AsyncMock(return_value=bytearray(b"schedule")))
        self.commands = SimpleNamespace(
            run=AsyncMock(return_value=SimpleNamespace(stdout="ok\n", stderr="", exit_code=0))
        )
        self.kill = AsyncMock(return_value=True)


def test_factory_creates_a_secure_internet_disabled_kill_on_timeout_sandbox():
    async def exercise() -> tuple[E2BSandboxBackend, dict]:
        captured = {}
        sandbox = FakeE2BSandbox()

        async def create_sandbox(**kwargs):
            captured.update(kwargs)
            return sandbox

        factory = E2BSandboxFactory(
            api_key="secret-key",
            template="template-name",
            turn_timeout_seconds=12.1,
            command_timeout_seconds=3,
            create_sandbox=create_sandbox,
        )
        return await factory.create(), captured

    backend, captured = asyncio.run(exercise())
    assert backend.sandbox_id == "sandbox-123"
    assert captured == {
        "template": "template-name",
        "timeout": 13,
        "secure": True,
        "allow_internet_access": False,
        "lifecycle": {"on_timeout": "kill", "auto_resume": False},
        "api_key": "secret-key",
    }
    assert "envs" not in captured


def test_factory_redacts_provider_creation_failures():
    async def create_sandbox(**_kwargs):
        raise RuntimeError("request contained secret-key")

    async def exercise() -> None:
        factory = E2BSandboxFactory(
            api_key="secret-key",
            template="template-name",
            turn_timeout_seconds=10,
            command_timeout_seconds=3,
            create_sandbox=create_sandbox,
        )
        with pytest.raises(SandboxError) as raised:
            await factory.create()
        assert "secret-key" not in str(raised.value)

    asyncio.run(exercise())


def test_backend_reads_writes_and_runs_in_the_workspace_as_user():
    async def exercise() -> tuple[FakeE2BSandbox, object]:
        sandbox = FakeE2BSandbox()
        backend = E2BSandboxBackend(sandbox, command_timeout_seconds=3)
        await backend.write_file("/workspace/schedule.yaml", b"schedule")
        assert await backend.read_file("/workspace/schedule.yaml") == b"schedule"
        result = await backend.run("rg P1 schedule.yaml")
        return sandbox, result

    sandbox, result = asyncio.run(exercise())
    sandbox.files.write.assert_awaited_once_with("/workspace/schedule.yaml", b"schedule", user="user")
    sandbox.files.read.assert_awaited_once_with("/workspace/schedule.yaml", format="bytes", user="user")
    sandbox.commands.run.assert_awaited_once_with("rg P1 schedule.yaml", user="user", cwd="/workspace", timeout=3)
    assert result.stdout == "ok\n"
    assert result.exit_code == 0


def test_nonzero_command_exit_is_returned_instead_of_raised():
    async def exercise():
        sandbox = FakeE2BSandbox()
        sandbox.commands.run.side_effect = CommandExitException(
            stderr="not found\n", stdout="", exit_code=2, error=None
        )
        backend = E2BSandboxBackend(sandbox, command_timeout_seconds=3)
        return await backend.run("rg missing schedule.yaml")

    result = asyncio.run(exercise())
    assert result.exit_code == 2
    assert result.stderr == "not found\n"
    assert not result.timed_out


def test_command_timeout_returns_a_failure_and_destroys_the_sandbox():
    async def exercise() -> tuple[FakeE2BSandbox, object, E2BSandboxBackend]:
        sandbox = FakeE2BSandbox()
        sandbox.commands.run.side_effect = TimeoutException("deadline exceeded")
        backend = E2BSandboxBackend(sandbox, command_timeout_seconds=3)
        result = await backend.run("sleep 99", timeout_seconds=2)
        return sandbox, result, backend

    sandbox, result, backend = asyncio.run(exercise())
    assert result.exit_code == COMMAND_TIMEOUT_EXIT_CODE
    assert result.timed_out
    assert "2 seconds" in result.stderr
    sandbox.kill.assert_awaited_once()
    with pytest.raises(SandboxError, match="is closed"):
        asyncio.run(backend.run("echo late"))


def test_close_is_idempotent():
    async def exercise() -> FakeE2BSandbox:
        sandbox = FakeE2BSandbox()
        backend = E2BSandboxBackend(sandbox, command_timeout_seconds=3)
        await backend.close()
        await backend.close()
        return sandbox

    sandbox = asyncio.run(exercise())
    sandbox.kill.assert_awaited_once()
