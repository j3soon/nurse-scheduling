"""Tests for provider-neutral AI sandbox contracts and lifecycle handling."""

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
from contextlib import nullcontext

import pytest

from nurse_scheduling.ai.sandbox import (
    CommandResult,
    SandboxCleanupError,
    managed_sandbox,
    managed_sandbox_factory,
)
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory


def test_fake_backend_supports_one_complete_lifecycle():
    async def exercise() -> FakeSandboxBackend:
        def command_handler(command: str, timeout: float | None, backend: FakeSandboxBackend) -> CommandResult:
            assert command == "edit schedule"
            assert timeout == 3
            backend.files["/workspace/schedule.yaml"] = b"people: [P1]\n"
            return CommandResult("updated\n", "", 0, duration_seconds=0.2)

        backend = FakeSandboxBackend("fake-1", command_handler=command_handler)
        await backend.write_file("/workspace/schedule.yaml", "people: []\n")
        result = await backend.run("edit schedule", timeout_seconds=3)
        assert result == CommandResult("updated\n", "", 0, duration_seconds=0.2)
        assert await backend.read_file("/workspace/schedule.yaml") == b"people: [P1]\n"
        await backend.close()
        await backend.close()
        return backend

    backend = asyncio.run(exercise())
    assert backend.closed
    assert backend.close_calls == 2


def test_factory_creates_isolated_sandboxes_for_separate_turns():
    async def exercise() -> tuple[FakeSandboxBackend, FakeSandboxBackend]:
        factory = FakeSandboxFactory()
        first = await factory.create()
        await first.write_file("/workspace/only-first", b"data")
        second = await factory.create()
        return first, second

    first, second = asyncio.run(exercise())
    assert first.sandbox_id != second.sandbox_id
    assert "/workspace/only-first" not in second.files


def test_managed_factory_runs_optional_cleanup_supervision_hooks():
    async def exercise() -> list[str]:
        events: list[str] = []

        class ManagedFactory(FakeSandboxFactory):
            async def start_cleanup(self) -> None:
                events.append("start")

            async def stop_cleanup(self) -> None:
                events.append("stop")

        async with managed_sandbox_factory(ManagedFactory()):
            events.append("body")
        return events

    assert asyncio.run(exercise()) == ["start", "body", "stop"]


def test_backend_returns_unbounded_output_for_the_ai_tool_layer_to_limit():
    async def exercise() -> CommandResult:
        backend = FakeSandboxBackend(
            "fake-1",
            command_handler=lambda *_: CommandResult("a" * 100, "b" * 100, 0),
        )
        return await backend.run("large output")

    result = asyncio.run(exercise())
    assert result.stdout == "a" * 100
    assert result.stderr == "b" * 100


def test_command_timeout_is_a_structured_result():
    async def exercise() -> CommandResult:
        backend = FakeSandboxBackend(
            "fake-1",
            command_handler=lambda *_: CommandResult("", "Command timed out after 2 seconds.", 124, timed_out=True),
        )
        return await backend.run("sleep forever", timeout_seconds=2)

    result = asyncio.run(exercise())
    assert result.exit_code == 124
    assert result.timed_out


def test_managed_sandbox_closes_after_success_and_failure():
    async def exercise(raises: bool) -> FakeSandboxBackend:
        factory = FakeSandboxFactory()
        with pytest.raises(RuntimeError) if raises else nullcontext():
            async with managed_sandbox(factory):
                if raises:
                    raise RuntimeError("agent failed")
        return factory.created[0]

    assert asyncio.run(exercise(False)).closed
    assert asyncio.run(exercise(True)).closed


def test_cleanup_failure_does_not_mask_the_turn_failure():
    async def exercise() -> None:
        factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, close_error=OSError("offline")))
        with pytest.raises(ValueError, match="validation failed"):
            async with managed_sandbox(factory):
                raise ValueError("validation failed")

    asyncio.run(exercise())


def test_cleanup_failure_after_success_is_reported():
    async def exercise() -> None:
        factory = FakeSandboxFactory(lambda sandbox_id: FakeSandboxBackend(sandbox_id, close_error=OSError("offline")))
        with pytest.raises(SandboxCleanupError, match="could not be destroyed"):
            async with managed_sandbox(factory):
                pass

    asyncio.run(exercise())


def test_cancelling_a_turn_still_closes_its_sandbox():
    async def exercise() -> FakeSandboxBackend:
        factory = FakeSandboxFactory()
        entered = asyncio.Event()

        async def turn() -> None:
            async with managed_sandbox(factory):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(turn())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return factory.created[0]

    assert asyncio.run(exercise()).closed


def test_cancellation_during_cleanup_waits_for_close_and_stays_cancelled():
    async def exercise() -> FakeSandboxBackend:
        close_started = asyncio.Event()
        release_close = asyncio.Event()

        class DelayedCloseBackend(FakeSandboxBackend):
            async def close(self) -> None:
                self.close_calls += 1
                close_started.set()
                await release_close.wait()
                self.closed = True

        factory = FakeSandboxFactory(DelayedCloseBackend)

        async def turn() -> None:
            async with managed_sandbox(factory):
                pass

        task = asyncio.create_task(turn())
        await close_started.wait()
        task.cancel()
        release_close.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        return factory.created[0]

    backend = asyncio.run(exercise())
    assert backend.closed
    assert backend.close_calls == 1
