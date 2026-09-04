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
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from e2b.exceptions import FileNotFoundException, SandboxException, TimeoutException
from e2b.sandbox.commands.command_handle import CommandExitException

from nurse_scheduling.ai.sandbox import SandboxError, SandboxFileNotFoundError, managed_sandbox
from nurse_scheduling.ai.sandbox import e2b as e2b_module
from nurse_scheduling.ai.sandbox.e2b import (
    COMMAND_TIMEOUT_EXIT_CODE,
    E2BSandboxBackend,
    E2BSandboxFactory,
    E2BSandboxState,
)


class FakeE2BSandbox:
    def __init__(self) -> None:
        self.sandbox_id = "sandbox-123"
        self.files = SimpleNamespace(
            write=AsyncMock(),
            read=AsyncMock(return_value=bytearray(b"schedule")),
            exists=AsyncMock(return_value=True),
        )
        self.commands = SimpleNamespace(
            run=AsyncMock(return_value=SimpleNamespace(stdout="ok\n", stderr="", exit_code=0))
        )
        self.pause = AsyncMock(return_value=True)
        self.connect = AsyncMock(return_value=self)
        self.kill = AsyncMock(return_value=True)


def make_backend(
    sandbox: FakeE2BSandbox,
    *,
    pause_request_timeout_seconds: float = 5,
    control_request_timeout_seconds: float = 2,
    defer_cleanup=None,
) -> E2BSandboxBackend:
    return E2BSandboxBackend(
        sandbox,
        command_timeout_seconds=3,
        retry_backoff_seconds=0,
        pause_request_timeout_seconds=pause_request_timeout_seconds,
        control_request_timeout_seconds=control_request_timeout_seconds,
        defer_cleanup=defer_cleanup,
    )


async def wait_for_state(e2b_backend: E2BSandboxBackend, state: E2BSandboxState) -> None:
    async with asyncio.timeout(1):
        while e2b_backend.lifecycle_state is not state:
            await asyncio.sleep(0.001)


def test_factory_creates_a_secure_internet_disabled_auto_pause_sandbox():
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
    metadata = captured.pop("metadata")
    assert metadata["nurse_scheduling_ai_managed"] == "true"
    assert float(metadata["nurse_scheduling_ai_hard_deadline"]) > 0
    assert captured == {
        "template": "template-name",
        "timeout": 13,
        "secure": True,
        "allow_internet_access": False,
        "lifecycle": {
            "on_timeout": {"action": "pause", "keep_memory": True},
            "auto_resume": True,
        },
        "api_key": "secret-key",
    }
    assert "envs" not in captured


def test_factory_redacts_provider_creation_failures():
    attempts = 0

    async def create_sandbox(**_kwargs):
        nonlocal attempts
        attempts += 1
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
    assert attempts == 1


def test_factory_cancellation_kills_a_sandbox_created_by_the_in_flight_request():
    async def exercise() -> FakeE2BSandbox:
        entered = asyncio.Event()
        release = asyncio.Event()
        sandbox = FakeE2BSandbox()

        async def create_sandbox(**_kwargs):
            entered.set()
            await release.wait()
            return sandbox

        factory = E2BSandboxFactory(
            api_key="secret-key",
            template="template-name",
            turn_timeout_seconds=10,
            command_timeout_seconds=3,
            create_sandbox=create_sandbox,
        )
        task = asyncio.create_task(factory.create())
        await entered.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        return sandbox

    sandbox = asyncio.run(exercise())
    sandbox.kill.assert_awaited_once_with(request_timeout=2)


def test_backend_reads_writes_and_runs_in_the_workspace_as_user():
    async def exercise() -> tuple[FakeE2BSandbox, object]:
        sandbox = FakeE2BSandbox()
        e2b_backend = make_backend(sandbox)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        assert await e2b_backend.read_file("/workspace/schedule.yaml") == b"schedule"
        result = await e2b_backend.run("rg P1 schedule.yaml")
        await e2b_backend.close()
        return sandbox, result

    sandbox, result = asyncio.run(exercise())
    sandbox.files.write.assert_awaited_once_with("/workspace/schedule.yaml", b"schedule", user="user")
    sandbox.files.read.assert_awaited_once_with("/workspace/schedule.yaml", format="bytes", user="user")
    sandbox.commands.run.assert_awaited_once_with("rg P1 schedule.yaml", user="user", cwd="/workspace", timeout=3)
    assert result.stdout == "ok\n"
    assert result.exit_code == 0


def test_backend_distinguishes_a_missing_file_from_a_service_failure():
    async def exercise() -> None:
        sandbox = FakeE2BSandbox()
        sandbox.files.read.side_effect = FileNotFoundException("missing")
        e2b_backend = make_backend(sandbox)

        with pytest.raises(SandboxFileNotFoundError, match="Sandbox file not found"):
            await e2b_backend.read_file("/workspace/missing.txt")
        await e2b_backend.close()

    asyncio.run(exercise())


def test_retries_a_replay_safe_file_request_with_logged_backoff(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    async def exercise() -> FakeE2BSandbox:
        sandbox = FakeE2BSandbox()
        sandbox.files.write.side_effect = [
            SandboxException("500: temporary failure"),
            SandboxException("500: temporary failure"),
            None,
        ]
        e2b_backend = E2BSandboxBackend(
            sandbox,
            command_timeout_seconds=3,
            retry_backoff_seconds=0.25,
        )
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await e2b_backend.close()
        return sandbox

    caplog.set_level(logging.WARNING, logger="nurse_scheduling.ai.sandbox.e2b")
    monkeypatch.setattr(e2b_module.asyncio, "sleep", record_delay)
    sandbox = asyncio.run(exercise())

    assert sandbox.files.write.await_count == 3
    assert delays == [0.25, 0.5]
    assert "operation=write_file" in caplog.text
    assert "attempt=1 max_attempts=3" in caplog.text
    assert "error_type=SandboxException" in caplog.text
    assert "temporary failure" not in caplog.text


def test_does_not_retry_an_optional_pause_failure(caplog: pytest.LogCaptureFixture):
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend]:
        attempted = asyncio.Event()
        sandbox = FakeE2BSandbox()

        async def fail_pause(**_kwargs):
            attempted.set()
            raise SandboxException("500: temporary failure")

        sandbox.pause.side_effect = fail_pause
        e2b_backend = make_backend(sandbox)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await attempted.wait()
        await asyncio.sleep(0)
        await e2b_backend.close()
        return sandbox, e2b_backend

    caplog.set_level(logging.WARNING, logger="nurse_scheduling.ai.sandbox.e2b")
    sandbox, backend = asyncio.run(exercise())

    assert sandbox.pause.await_count == 1
    assert backend.lifecycle_metrics.pause_count == 0
    assert "sandbox pause failed" in caplog.text


def test_pause_deadline_reconciles_before_the_next_operation(caplog: pytest.LogCaptureFixture):
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend, float]:
        sandbox = FakeE2BSandbox()
        pause_attempts = 0

        async def pause_forever(**_kwargs):
            nonlocal pause_attempts
            pause_attempts += 1
            if pause_attempts == 1:
                await asyncio.Event().wait()
            return True

        sandbox.pause.side_effect = pause_forever
        e2b_backend = make_backend(sandbox, pause_request_timeout_seconds=0.01)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await wait_for_state(e2b_backend, E2BSandboxState.PAUSE_UNKNOWN)
        started = asyncio.get_running_loop().time()
        await e2b_backend.read_file("/workspace/schedule.yaml")
        elapsed = asyncio.get_running_loop().time() - started
        await wait_for_state(e2b_backend, E2BSandboxState.PAUSED)
        await e2b_backend.close()
        return sandbox, e2b_backend, elapsed

    caplog.set_level(logging.WARNING, logger="nurse_scheduling.ai.sandbox.e2b")
    sandbox, backend, elapsed = asyncio.run(exercise())

    assert elapsed < 0.5
    assert sandbox.pause.await_args_list[0].kwargs == {"keep_memory": True, "request_timeout": 0.01}
    assert sandbox.pause.await_count == 2
    sandbox.files.exists.assert_awaited_once_with("/workspace", user="user")
    assert backend.lifecycle_metrics.pause_count == 1
    assert backend.lifecycle_metrics.resume_count == 1
    assert "sandbox pause timed out" in caplog.text


def test_retries_a_bounded_resume_probe_before_failing():
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend, float]:
        sandbox = FakeE2BSandbox()
        e2b_backend = make_backend(sandbox, control_request_timeout_seconds=0.01)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await wait_for_state(e2b_backend, E2BSandboxState.PAUSED)

        async def exists_forever(*_args, **_kwargs):
            await asyncio.Event().wait()

        sandbox.files.exists.side_effect = exists_forever
        started = asyncio.get_running_loop().time()
        with pytest.raises(SandboxError, match="could not resume"):
            await e2b_backend.read_file("/workspace/schedule.yaml")
        elapsed = asyncio.get_running_loop().time() - started
        await e2b_backend.close()
        return sandbox, e2b_backend, elapsed

    sandbox, backend, elapsed = asyncio.run(exercise())

    assert elapsed < 0.5
    assert sandbox.files.exists.await_count == 3
    assert backend.lifecycle_state is E2BSandboxState.CLOSED


def test_retries_auto_resume_before_the_next_operation(caplog: pytest.LogCaptureFixture):
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend]:
        sandbox = FakeE2BSandbox()
        e2b_backend = make_backend(sandbox)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await wait_for_state(e2b_backend, E2BSandboxState.PAUSED)
        sandbox.files.exists.side_effect = [SandboxException("500: temporary failure"), True]
        await e2b_backend.read_file("/workspace/schedule.yaml")
        await e2b_backend.close()
        return sandbox, e2b_backend

    caplog.set_level(logging.WARNING, logger="nurse_scheduling.ai.sandbox.e2b")
    sandbox, backend = asyncio.run(exercise())

    assert sandbox.files.exists.await_count == 2
    assert backend.lifecycle_metrics.resume_count == 1
    assert "operation=resume" in caplog.text


def test_retries_idempotent_sandbox_destruction(caplog: pytest.LogCaptureFixture):
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend]:
        sandbox = FakeE2BSandbox()
        sandbox.kill.side_effect = [SandboxException("500: temporary failure"), True]
        e2b_backend = make_backend(sandbox)
        await e2b_backend.close()
        return sandbox, e2b_backend

    caplog.set_level(logging.WARNING, logger="nurse_scheduling.ai.sandbox.e2b")
    sandbox, backend = asyncio.run(exercise())

    assert sandbox.kill.await_count == 2
    assert backend.lifecycle_state is E2BSandboxState.CLOSED
    assert "operation=kill" in caplog.text


def test_defers_cleanup_when_kill_retries_are_exhausted():
    async def exercise() -> tuple[FakeE2BSandbox, list[str]]:
        deferred: list[str] = []
        sandbox = FakeE2BSandbox()
        sandbox.kill.side_effect = SandboxException("500: unavailable")
        e2b_backend = make_backend(sandbox, defer_cleanup=deferred.append)

        with pytest.raises(SandboxError, match="could not destroy"):
            await e2b_backend.close()
        return sandbox, deferred

    sandbox, deferred = asyncio.run(exercise())

    assert sandbox.kill.await_count == 3
    assert deferred == ["sandbox-123"]


def test_defers_cleanup_when_close_is_cancelled_during_kill():
    async def exercise() -> list[str]:
        deferred: list[str] = []
        kill_started = asyncio.Event()
        sandbox = FakeE2BSandbox()

        async def kill(**_kwargs):
            kill_started.set()
            await asyncio.Event().wait()

        sandbox.kill.side_effect = kill
        e2b_backend = make_backend(sandbox, defer_cleanup=deferred.append)
        close_task = asyncio.create_task(e2b_backend.close())
        await kill_started.wait()
        close_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await close_task
        return deferred

    assert asyncio.run(exercise()) == ["sandbox-123"]


def test_does_not_retry_an_ambiguous_command_failure():
    async def exercise() -> FakeE2BSandbox:
        sandbox = FakeE2BSandbox()
        sandbox.commands.run.side_effect = SandboxException("500: unknown command outcome")
        e2b_backend = make_backend(sandbox)
        with pytest.raises(SandboxError, match="could not run"):
            await e2b_backend.run("python edit.py")
        await e2b_backend.close()
        return sandbox

    sandbox = asyncio.run(exercise())

    sandbox.commands.run.assert_awaited_once()


def test_backend_explicitly_pauses_with_warm_memory_after_an_operation():
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend]:
        sandbox = FakeE2BSandbox()
        e2b_backend = make_backend(sandbox)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await wait_for_state(e2b_backend, E2BSandboxState.PAUSED)
        await e2b_backend.close()
        return sandbox, e2b_backend

    sandbox, e2b_backend = asyncio.run(exercise())
    sandbox.pause.assert_awaited_once_with(keep_memory=True, request_timeout=5)
    sandbox.connect.assert_not_awaited()
    assert e2b_backend.lifecycle_metrics.pause_count == 1
    assert e2b_backend.lifecycle_metrics.suspended_seconds > 0


def test_immediate_activity_cancels_a_pending_pause():
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend]:
        sandbox = FakeE2BSandbox()
        e2b_backend = make_backend(sandbox)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await e2b_backend.read_file("/workspace/schedule.yaml")
        await wait_for_state(e2b_backend, E2BSandboxState.PAUSED)
        await e2b_backend.close()
        return sandbox, e2b_backend

    sandbox, e2b_backend = asyncio.run(exercise())
    sandbox.pause.assert_awaited_once_with(keep_memory=True, request_timeout=5)
    assert e2b_backend.lifecycle_metrics.pause_count == 1


def test_activity_cancels_an_in_progress_pause_before_running():
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend, float]:
        entered = asyncio.Event()
        cancelled = asyncio.Event()
        sandbox = FakeE2BSandbox()

        async def pause(*, keep_memory: bool, request_timeout: float):
            assert keep_memory
            assert request_timeout == 5
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        sandbox.pause.side_effect = pause
        e2b_backend = make_backend(sandbox)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await entered.wait()
        assert e2b_backend.lifecycle_state is E2BSandboxState.PAUSING

        started = asyncio.get_running_loop().time()
        await asyncio.gather(
            e2b_backend.run("echo ready"),
            e2b_backend.read_file("/workspace/schedule.yaml"),
        )
        elapsed = asyncio.get_running_loop().time() - started
        await cancelled.wait()
        await e2b_backend.close()
        return sandbox, e2b_backend, elapsed

    sandbox, backend, elapsed = asyncio.run(exercise())

    assert elapsed < 0.5
    sandbox.commands.run.assert_awaited_once()
    sandbox.files.read.assert_awaited_once()
    assert backend.lifecycle_metrics.pause_count == 0
    assert backend.lifecycle_metrics.pause_cancel_count == 1
    assert backend.lifecycle_state is E2BSandboxState.CLOSED


def test_next_operation_resumes_the_same_sandbox_once_before_running():
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend]:
        sandbox = FakeE2BSandbox()
        e2b_backend = make_backend(sandbox)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await wait_for_state(e2b_backend, E2BSandboxState.PAUSED)
        await asyncio.gather(
            e2b_backend.run("rg P1 schedule.yaml"),
            e2b_backend.read_file("/workspace/schedule.yaml"),
        )
        await e2b_backend.close()
        return sandbox, e2b_backend

    sandbox, e2b_backend = asyncio.run(exercise())
    sandbox.files.exists.assert_awaited_once_with("/workspace", user="user")
    sandbox.connect.assert_not_awaited()
    sandbox.commands.run.assert_awaited_once()
    metrics = e2b_backend.lifecycle_metrics
    assert metrics.pause_count >= 1
    assert metrics.resume_count == 1
    assert metrics.resume_wait_seconds >= 0


def test_nonzero_command_exit_is_returned_instead_of_raised():
    async def exercise():
        sandbox = FakeE2BSandbox()
        sandbox.commands.run.side_effect = CommandExitException(
            stderr="not found\n", stdout="", exit_code=2, error=None
        )
        e2b_backend = make_backend(sandbox)
        result = await e2b_backend.run("rg missing schedule.yaml")
        await e2b_backend.close()
        return result

    result = asyncio.run(exercise())
    assert result.exit_code == 2
    assert result.stderr == "not found\n"
    assert not result.timed_out


def test_command_timeout_returns_a_failure_and_destroys_the_sandbox():
    async def exercise() -> tuple[FakeE2BSandbox, object, E2BSandboxBackend]:
        sandbox = FakeE2BSandbox()
        sandbox.commands.run.side_effect = TimeoutException("deadline exceeded")
        e2b_backend = make_backend(sandbox)
        result = await e2b_backend.run("sleep 99", timeout_seconds=2)
        return sandbox, result, e2b_backend

    sandbox, result, backend = asyncio.run(exercise())
    assert result.exit_code == COMMAND_TIMEOUT_EXIT_CODE
    assert result.timed_out
    assert result.stderr == ""
    sandbox.kill.assert_awaited_once_with(request_timeout=2)
    with pytest.raises(SandboxError, match="is closed"):
        asyncio.run(backend.run("echo late"))


def test_close_is_idempotent():
    async def exercise() -> FakeE2BSandbox:
        sandbox = FakeE2BSandbox()
        e2b_backend = make_backend(sandbox)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await e2b_backend.close()
        await e2b_backend.close()
        await asyncio.sleep(0.02)
        return sandbox

    sandbox = asyncio.run(exercise())
    sandbox.kill.assert_awaited_once_with(request_timeout=2)
    sandbox.pause.assert_not_awaited()


def test_managed_cleanup_cancels_a_terminal_pause_before_it_starts():
    async def exercise() -> FakeE2BSandbox:
        sandbox = FakeE2BSandbox()
        e2b_backend = make_backend(sandbox)
        factory = SimpleNamespace(create=AsyncMock(return_value=e2b_backend))
        async with managed_sandbox(factory):
            await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await asyncio.sleep(0)
        return sandbox

    sandbox = asyncio.run(exercise())
    sandbox.pause.assert_not_awaited()
    sandbox.kill.assert_awaited_once_with(request_timeout=2)


def test_close_waits_for_a_running_operation_before_destroying():
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend]:
        entered = asyncio.Event()
        release = asyncio.Event()
        sandbox = FakeE2BSandbox()

        async def run_command(*_args, **_kwargs):
            entered.set()
            await release.wait()
            return SimpleNamespace(stdout="ok\n", stderr="", exit_code=0)

        sandbox.commands.run.side_effect = run_command
        e2b_backend = make_backend(sandbox)
        run_task = asyncio.create_task(e2b_backend.run("sleep briefly"))
        await entered.wait()
        close_task = asyncio.create_task(e2b_backend.close())
        await asyncio.sleep(0)
        sandbox.kill.assert_not_awaited()
        release.set()
        await run_task
        await close_task
        return sandbox, e2b_backend

    sandbox, e2b_backend = asyncio.run(exercise())
    sandbox.kill.assert_awaited_once_with(request_timeout=2)
    assert e2b_backend.lifecycle_state is E2BSandboxState.CLOSED


def test_close_cancels_an_in_progress_pause_then_kills():
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend]:
        entered = asyncio.Event()
        sandbox = FakeE2BSandbox()

        async def pause(*, keep_memory: bool, request_timeout: float):
            assert keep_memory
            assert request_timeout == 5
            entered.set()
            await asyncio.Event().wait()

        sandbox.pause.side_effect = pause
        e2b_backend = make_backend(sandbox)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await entered.wait()
        assert e2b_backend.lifecycle_state is E2BSandboxState.PAUSING
        close_task = asyncio.create_task(e2b_backend.close())
        await asyncio.wait_for(close_task, timeout=0.5)
        return sandbox, e2b_backend

    sandbox, e2b_backend = asyncio.run(exercise())
    sandbox.pause.assert_awaited_once_with(keep_memory=True, request_timeout=5)
    sandbox.kill.assert_awaited_once_with(request_timeout=2)
    assert e2b_backend.lifecycle_state is E2BSandboxState.CLOSED


def test_close_waits_for_an_in_progress_auto_resume_then_destroys():
    async def exercise() -> tuple[FakeE2BSandbox, E2BSandboxBackend]:
        entered = asyncio.Event()
        release = asyncio.Event()
        sandbox = FakeE2BSandbox()

        async def exists(path: str, *, user: str):
            assert path == "/workspace"
            assert user == "user"
            entered.set()
            await release.wait()
            return True

        sandbox.files.exists.side_effect = exists
        e2b_backend = make_backend(sandbox)
        await e2b_backend.write_file("/workspace/schedule.yaml", b"schedule")
        await wait_for_state(e2b_backend, E2BSandboxState.PAUSED)
        read_task = asyncio.create_task(e2b_backend.read_file("/workspace/schedule.yaml"))
        await entered.wait()
        assert e2b_backend.lifecycle_state is E2BSandboxState.RESUMING
        close_task = asyncio.create_task(e2b_backend.close())
        await asyncio.sleep(0)
        sandbox.kill.assert_not_awaited()
        release.set()
        await read_task
        await close_task
        return sandbox, e2b_backend

    sandbox, e2b_backend = asyncio.run(exercise())
    sandbox.files.exists.assert_awaited_once()
    sandbox.connect.assert_not_awaited()
    sandbox.kill.assert_awaited_once_with(request_timeout=2)
    assert e2b_backend.lifecycle_state is E2BSandboxState.CLOSED
