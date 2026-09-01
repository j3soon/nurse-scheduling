"""Opt-in live lifecycle check for the prebuilt E2B Cloud sandbox."""

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
import os

import pytest
from e2b import AsyncSandbox
from e2b.exceptions import SandboxNotFoundException

from nurse_scheduling.ai.sandbox import managed_sandbox
from nurse_scheduling.ai.sandbox.e2b import E2BSandboxBackend, E2BSandboxFactory, E2BSandboxState

E2B_API_KEY = os.getenv("E2B_API_KEY", "").strip()
RUN_LIVE = os.getenv("RUN_E2B_INTEGRATION", "") == "1"

pytestmark = pytest.mark.skipif(
    not E2B_API_KEY or not RUN_LIVE,
    reason="set E2B_API_KEY and RUN_E2B_INTEGRATION=1 for the live E2B check",
)


async def wait_until_paused(sandbox: E2BSandboxBackend) -> None:
    async with asyncio.timeout(10):
        while sandbox.lifecycle_state is not E2BSandboxState.PAUSED:
            await asyncio.sleep(0.05)


def test_prebuilt_e2b_template_supports_the_raw_backend_lifecycle():
    async def exercise() -> None:
        factory = E2BSandboxFactory(
            api_key=E2B_API_KEY,
            template=os.getenv("E2B_TEMPLATE", "nurse-scheduling-ai-sandbox"),
            turn_timeout_seconds=30,
            command_timeout_seconds=5,
        )
        async with managed_sandbox(factory, cleanup_timeout_seconds=10) as sandbox:
            await sandbox.write_file("/workspace/schedule.yaml", b"people:\n  - id: P1\n")
            await sandbox.write_file(
                "/reference/schedule-schema.md",
                "Schema overview\n\n---\n\nPath: people.items\nPeople available for scheduling.\n",
            )
            result = await sandbox.run(
                "rg -n 'P1' schedule.yaml && "
                'python3 -c "from ruamel.yaml import YAML; '
                "print(YAML(typ='safe').load(open('schedule.yaml'))['people'][0]['id'])\" && "
                "nsctl schema show people.items"
            )
            assert result.exit_code == 0
            assert result.stdout == (
                "2:  - id: P1\nP1\nPath: people.items\nPeople available for scheduling.\n\n"
            )
            assert await sandbox.read_file("/workspace/schedule.yaml") == b"people:\n  - id: P1\n"

    asyncio.run(exercise())


def test_explicit_pause_auto_resumes_the_same_sandbox():
    async def exercise() -> None:
        factory = E2BSandboxFactory(
            api_key=E2B_API_KEY,
            template=os.getenv("E2B_TEMPLATE", "nurse-scheduling-ai-sandbox"),
            turn_timeout_seconds=30,
            command_timeout_seconds=5,
        )
        async with managed_sandbox(factory, cleanup_timeout_seconds=10) as raw_sandbox:
            assert isinstance(raw_sandbox, E2BSandboxBackend)
            await raw_sandbox.write_file("/workspace/timeout-check.txt", b"preserved")
            await wait_until_paused(raw_sandbox)

            assert await raw_sandbox.read_file("/workspace/timeout-check.txt") == b"preserved"
            metrics = raw_sandbox.lifecycle_metrics
            assert metrics.pause_count == 1
            assert metrics.resume_count == 1
            assert metrics.resume_wait_seconds > 0

        assert raw_sandbox.lifecycle_state is E2BSandboxState.CLOSED

    asyncio.run(exercise())


def test_application_deadline_explicitly_kills_and_prevents_resume():
    async def exercise() -> None:
        factory = E2BSandboxFactory(
            api_key=E2B_API_KEY,
            template=os.getenv("E2B_TEMPLATE", "nurse-scheduling-ai-sandbox"),
            turn_timeout_seconds=30,
            command_timeout_seconds=5,
        )
        raw_sandbox: E2BSandboxBackend | None = None
        with pytest.raises(TimeoutError):
            async with managed_sandbox(factory, cleanup_timeout_seconds=10) as created:
                async with asyncio.timeout(0.5):
                    assert isinstance(created, E2BSandboxBackend)
                    raw_sandbox = created
                    await asyncio.Event().wait()

        assert raw_sandbox is not None
        assert raw_sandbox.lifecycle_state is E2BSandboxState.CLOSED
        with pytest.raises(SandboxNotFoundException):
            await AsyncSandbox.connect(raw_sandbox.sandbox_id, timeout=5, api_key=E2B_API_KEY)

    asyncio.run(exercise())


def test_manual_pause_survives_kill_timeout_but_explicit_kill_is_terminal():
    """Record observed timeout behavior and the authoritative cleanup boundary."""

    async def exercise() -> None:
        sandbox = await AsyncSandbox.create(
            os.getenv("E2B_TEMPLATE", "nurse-scheduling-ai-sandbox"),
            timeout=5,
            lifecycle={"on_timeout": "kill", "auto_resume": False},
            allow_internet_access=False,
            api_key=E2B_API_KEY,
        )
        sandbox_id = sandbox.sandbox_id
        killed = False
        try:
            await sandbox.files.write("/workspace/timeout-check.txt", "preserved", user="user")
            await sandbox.pause(keep_memory=True)
            await asyncio.sleep(5.5)

            await sandbox.connect(timeout=5)
            assert await sandbox.files.read("/workspace/timeout-check.txt", user="user") == "preserved"
            await sandbox.pause(keep_memory=True)
            assert await sandbox.kill()
            killed = True

            with pytest.raises(SandboxNotFoundException):
                await AsyncSandbox.connect(sandbox_id, timeout=5, api_key=E2B_API_KEY)
        finally:
            if not killed:
                await sandbox.kill()

    asyncio.run(exercise())
