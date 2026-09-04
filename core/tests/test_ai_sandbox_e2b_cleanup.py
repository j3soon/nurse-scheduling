"""Tests for E2B deferred and stale-sandbox cleanup."""

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

from e2b.api.client.models.sandbox_state import SandboxState
from e2b.exceptions import SandboxException

from nurse_scheduling.ai.sandbox.e2b_cleanup import (
    HARD_DEADLINE_METADATA_KEY,
    MANAGED_METADATA_KEY,
    MANAGED_METADATA_VALUE,
    E2BSandboxCleanupManager,
)


class FakePaginator:
    def __init__(self, items: list[object]) -> None:
        self._items = items
        self.has_next = True

    async def next_items(self) -> list[object]:
        self.has_next = False
        return self._items


def test_metadata_records_ownership_and_the_turn_hard_deadline():
    manager = E2BSandboxCleanupManager(
        api_key="key",
        request_timeout_seconds=2,
        retry_backoff_seconds=0.5,
        reaper_interval_seconds=30,
        wall_clock=lambda: 100.25,
    )

    assert manager.metadata_for_turn(900) == {
        MANAGED_METADATA_KEY: MANAGED_METADATA_VALUE,
        HARD_DEADLINE_METADATA_KEY: "1000.25",
    }


def test_reconciliation_lists_only_owned_running_and_paused_sandboxes_and_kills_stale_ones(caplog):
    async def exercise() -> tuple[list[dict], list[str], E2BSandboxCleanupManager]:
        list_calls: list[dict] = []
        kill_calls: list[str] = []

        def list_sandboxes(**kwargs):
            list_calls.append(kwargs)
            if kill_calls:
                return FakePaginator([])
            return FakePaginator(
                [
                    SimpleNamespace(
                        sandbox_id="stale",
                        metadata={HARD_DEADLINE_METADATA_KEY: "99"},
                        state=SandboxState.PAUSED,
                    ),
                    SimpleNamespace(
                        sandbox_id="active",
                        metadata={HARD_DEADLINE_METADATA_KEY: "101"},
                        state=SandboxState.RUNNING,
                    ),
                ]
            )

        async def kill_sandbox(sandbox_id: str, **_kwargs) -> bool:
            kill_calls.append(sandbox_id)
            return True

        manager = E2BSandboxCleanupManager(
            api_key="key",
            request_timeout_seconds=2,
            retry_backoff_seconds=0.5,
            reaper_interval_seconds=30,
            list_sandboxes=list_sandboxes,
            kill_sandbox=kill_sandbox,
            wall_clock=lambda: 100,
            monotonic=lambda: 0,
        )
        await manager.reconcile_once()
        await manager.reconcile_once()
        await manager.retry_deferred_once()
        return list_calls, kill_calls, manager

    with caplog.at_level(logging.INFO, logger="nurse_scheduling.ai.sandbox.e2b_cleanup"):
        list_calls, kill_calls, manager = asyncio.run(exercise())

    assert kill_calls == ["stale"]
    assert manager.pending_count == 0
    query = list_calls[0]["query"]
    assert query.metadata == {MANAGED_METADATA_KEY: MANAGED_METADATA_VALUE}
    assert query.state == [SandboxState.RUNNING, SandboxState.PAUSED]
    assert list_calls[0]["limit"] == 100
    assert list_calls[0]["request_timeout"] == 2
    overdue_record = next(record for record in caplog.records if record.message.startswith("overdue sandbox"))
    assert overdue_record.levelno == logging.ERROR
    assert overdue_record.sandbox_id == "stale"
    assert overdue_record.overdue_seconds == 1
    assert sum(record.message.startswith("overdue sandbox") for record in caplog.records) == 1


def test_confirmation_rekills_a_sandbox_resurrected_by_a_late_resume():
    async def exercise() -> tuple[list[float], E2BSandboxCleanupManager]:
        now = [0.0]
        kill_calls: list[float] = []
        list_results = [
            [SimpleNamespace(sandbox_id="sandbox-1")],
            [],
        ]

        async def kill_sandbox(_sandbox_id: str, **_kwargs) -> bool:
            kill_calls.append(now[0])
            return True

        manager = E2BSandboxCleanupManager(
            api_key="key",
            request_timeout_seconds=2,
            retry_backoff_seconds=0.5,
            reaper_interval_seconds=30,
            list_sandboxes=lambda **_kwargs: FakePaginator(list_results.pop(0)),
            kill_sandbox=kill_sandbox,
            monotonic=lambda: now[0],
        )
        manager.confirm("sandbox-1")
        for instant in (1.99, 2.0, 2.49, 2.5):
            now[0] = instant
            await manager.retry_deferred_once()
        return kill_calls, manager

    kill_calls, manager = asyncio.run(exercise())

    assert kill_calls == [2.0, 2.5]
    assert manager.pending_count == 0


def test_deferred_cleanup_retries_with_exponential_backoff_until_absent():
    async def exercise() -> tuple[list[float], E2BSandboxCleanupManager]:
        now = [0.0]
        attempted_at: list[float] = []
        outcomes: list[BaseException | bool] = [TimeoutError(), SandboxException("offline"), False]

        async def kill_sandbox(_sandbox_id: str, **_kwargs) -> bool:
            attempted_at.append(now[0])
            outcome = outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        manager = E2BSandboxCleanupManager(
            api_key="key",
            request_timeout_seconds=2,
            retry_backoff_seconds=0.5,
            reaper_interval_seconds=30,
            list_sandboxes=lambda **_kwargs: FakePaginator([]),
            kill_sandbox=kill_sandbox,
            wall_clock=lambda: 100,
            monotonic=lambda: now[0],
        )
        manager.defer("sandbox-1")
        for instant in (0.0, 0.49, 0.5, 1.49, 1.5):
            now[0] = instant
            await manager.retry_deferred_once()
        return attempted_at, manager

    attempted_at, manager = asyncio.run(exercise())

    assert attempted_at == [0.0, 0.5, 1.5]
    assert manager.pending_count == 0


def test_deferred_cleanup_escalates_only_the_third_consecutive_failure(caplog):
    async def exercise() -> None:
        now = [0.0]

        async def kill_sandbox(_sandbox_id: str, **_kwargs) -> bool:
            raise TimeoutError

        manager = E2BSandboxCleanupManager(
            api_key="key",
            request_timeout_seconds=2,
            retry_backoff_seconds=0.5,
            reaper_interval_seconds=30,
            list_sandboxes=lambda **_kwargs: FakePaginator([]),
            kill_sandbox=kill_sandbox,
            monotonic=lambda: now[0],
        )
        manager.defer("sandbox-1")
        for instant in (0.0, 0.5, 1.5, 3.5):
            now[0] = instant
            await manager.retry_deferred_once()

    with caplog.at_level(logging.WARNING, logger="nurse_scheduling.ai.sandbox.e2b_cleanup"):
        asyncio.run(exercise())

    failures = [record for record in caplog.records if record.message.startswith("deferred sandbox cleanup failed")]
    assert [record.levelno for record in failures] == [
        logging.WARNING,
        logging.WARNING,
        logging.ERROR,
        logging.WARNING,
    ]
    assert failures[2].sandbox_id == "sandbox-1"
    assert failures[2].cleanup_attempt == 3


def test_cleanup_worker_runs_reconciliation_on_start_and_stops_cleanly():
    async def exercise() -> int:
        list_calls = 0

        def list_sandboxes(**_kwargs):
            nonlocal list_calls
            list_calls += 1
            return FakePaginator([])

        manager = E2BSandboxCleanupManager(
            api_key="key",
            request_timeout_seconds=2,
            retry_backoff_seconds=0.5,
            reaper_interval_seconds=30,
            list_sandboxes=list_sandboxes,
        )
        await manager.start()
        await manager.stop()
        return list_calls

    assert asyncio.run(exercise()) == 1
