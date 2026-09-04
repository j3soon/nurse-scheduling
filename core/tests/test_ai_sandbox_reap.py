"""Tests for the one-shot E2B sandbox reaper."""

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
from typing import ClassVar

import pytest

from nurse_scheduling.ai.sandbox.reap import reap_once


class FakeCleanupManager:
    instances: ClassVar[list["FakeCleanupManager"]] = []
    reconciliation_succeeded = True
    remaining = 0

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.pending_count = self.remaining
        self.reconciled = False
        self.retried = False
        self.instances.append(self)

    async def reconcile_once(self) -> bool:
        self.reconciled = True
        return self.reconciliation_succeeded

    async def retry_deferred_once(self) -> None:
        self.retried = True


@pytest.fixture(autouse=True)
def reset_fake_manager():
    FakeCleanupManager.instances.clear()
    FakeCleanupManager.reconciliation_succeeded = True
    FakeCleanupManager.remaining = 0


def test_reaper_uses_only_e2b_cleanup_configuration(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "key")
    monkeypatch.setenv("AI_SANDBOX_CONTROL_REQUEST_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("AI_SANDBOX_RETRY_BACKOFF_SECONDS", "0.75")
    monkeypatch.setenv("AI_SANDBOX_REAPER_INTERVAL_SECONDS", "45")

    result = asyncio.run(reap_once(manager_factory=FakeCleanupManager))

    assert result == 0
    manager = FakeCleanupManager.instances[0]
    assert manager.kwargs == {
        "api_key": "key",
        "request_timeout_seconds": 3,
        "retry_backoff_seconds": 0.75,
        "reaper_interval_seconds": 45,
    }
    assert manager.reconciled
    assert manager.retried


@pytest.mark.parametrize(
    ("reconciliation_succeeded", "remaining"),
    [(False, 0), (True, 1)],
)
def test_reaper_fails_when_reconciliation_or_deletion_is_unconfirmed(
    monkeypatch,
    caplog,
    reconciliation_succeeded,
    remaining,
):
    monkeypatch.setenv("E2B_API_KEY", "key")
    FakeCleanupManager.reconciliation_succeeded = reconciliation_succeeded
    FakeCleanupManager.remaining = remaining

    with caplog.at_level(logging.ERROR, logger="nurse_scheduling.ai.sandbox.reap"):
        result = asyncio.run(reap_once(manager_factory=FakeCleanupManager))

    assert result == 1
    record = caplog.records[-1]
    assert record.reconciliation_succeeded is reconciliation_succeeded
    assert record.pending_count == remaining


def test_reaper_does_not_require_ai_provider_configuration(monkeypatch):
    monkeypatch.setenv("E2B_API_KEY", "key")
    monkeypatch.delenv("AI_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("AI_PROVIDER_BASE_URL", raising=False)

    assert asyncio.run(reap_once(manager_factory=FakeCleanupManager)) == 0


def test_reaper_requires_e2b_api_key(monkeypatch):
    monkeypatch.delenv("E2B_API_KEY", raising=False)

    with pytest.raises(ValueError, match="E2B_API_KEY is required"):
        asyncio.run(reap_once(manager_factory=FakeCleanupManager))
