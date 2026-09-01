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

from nurse_scheduling.ai.sandbox import managed_sandbox
from nurse_scheduling.ai.sandbox.e2b import E2BSandboxFactory

E2B_API_KEY = os.getenv("E2B_API_KEY", "").strip()
RUN_LIVE = os.getenv("RUN_E2B_INTEGRATION", "") == "1"

pytestmark = pytest.mark.skipif(
    not E2B_API_KEY or not RUN_LIVE,
    reason="set E2B_API_KEY and RUN_E2B_INTEGRATION=1 for the live E2B check",
)


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
            result = await sandbox.run(
                "rg -n 'P1' schedule.yaml && "
                "python3 -c \"from ruamel.yaml import YAML; "
                "print(YAML(typ='safe').load(open('schedule.yaml'))['people'][0]['id'])\""
            )
            assert result.exit_code == 0
            assert result.stdout == "2:  - id: P1\nP1\n"
            assert await sandbox.read_file("/workspace/schedule.yaml") == b"people:\n  - id: P1\n"

    asyncio.run(exercise())
