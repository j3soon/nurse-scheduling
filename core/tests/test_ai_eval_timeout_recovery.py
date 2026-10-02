"""Independent checks for live agent timeout recovery."""

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
import copy
import hashlib
import json
import time
from types import SimpleNamespace

import pytest

from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.sandbox import CommandResult
from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend, FakeSandboxFactory
from nurse_scheduling.loader import _load_yaml

from .ai_eval import timeout_recovery_benchmark as comparison
from .ai_eval.grading import RunOutcome, grade, load_cases
from .ai_eval.runner import CASES, CaseRun, fixture_text
from .ai_eval.timeout_recovery_benchmark import CASE_ID, ObservedSandbox, recovery_failures


@pytest.mark.parametrize("fault", [None, "checkpoint", "replay", "late-write", "terminal", "rehydrate", "recreate"])
def test_runtime_oracle_rejects_false_recovery(fault):
    async def exercise():
        backend = FakeSandboxBackend(
            "same-sandbox",
            command_handler=lambda *_: CommandResult(
                "checkpoint saved", "", 124, timed_out=True, sandbox_terminated=fault == "terminal"
            ),
        )
        backend.lifecycle_state = SimpleNamespace(value="running")
        observed = ObservedSandbox(backend)
        checkpoint = {
            "description": "Recovered clinic checkpoint",
            "source_sha256": hashlib.sha256(fixture_text("small-clinic").encode()).hexdigest(),
        }
        if fault == "checkpoint":
            checkpoint["source_sha256"] = "wrong source"
        await observed.write_files(
            {
                "/workspace/timeout-checkpoint.json": json.dumps(checkpoint),
                "/workspace/timeout-attempts.txt": "once\nonce\n" if fault == "replay" else "once\n",
            }
        )
        if fault == "late-write":
            await observed.write_files({"/workspace/late-write.txt": "unsafe"})
        if fault == "rehydrate":
            await observed.write_files({"/workspace/schedule.yaml": "hydrated again"})
        await observed.run("python3 diagnostic", timeout_seconds=2)
        observed.timeout_ended = time.perf_counter() - 10
        await observed.close()
        failures = recovery_failures([observed, observed] if fault == "recreate" else [observed])
        assert bool(failures) == (fault is not None)
        assert backend.closed

    asyncio.run(exercise())


@pytest.mark.parametrize("fault", [None, "no-timeout", "wrong-description", "unrelated-edit"])
def test_timeout_case_grades_recovered_edit_and_failed_bash(fault):
    case = next(case for case in load_cases(CASES) if case.id == CASE_ID)
    initial = _load_yaml(fixture_text(case.fixture).encode())
    proposed = copy.deepcopy(initial)
    proposed["description"] = "Wrong checkpoint" if fault == "wrong-description" else "Recovered clinic checkpoint"
    if fault == "unrelated-edit":
        proposed["people"]["items"][0]["description"] = "Unrequested change"
    outcome = RunOutcome(
        answer="Proposed the recovered checkpoint description.",
        initial=initial,
        proposed=proposed,
        activity=[{"kind": "tool", "name": "bash", "ok": fault == "no-timeout"}],
    )
    assert grade(case, outcome).passed == (fault is None)


def test_comparison_checkpoints_and_reports_without_live_credentials(tmp_path, monkeypatch):
    def factory(terminal):
        def create(sandbox_id):
            backend = FakeSandboxBackend(
                sandbox_id,
                command_handler=lambda *_: CommandResult(
                    "checkpoint saved", "", 124, timed_out=True, sandbox_terminated=terminal
                ),
            )
            backend.lifecycle_state = SimpleNamespace(value="running")
            return backend

        return FakeSandboxFactory(create)

    before, after = factory(True), factory(False)
    monkeypatch.setattr(comparison, "historical_factory", lambda *_: (before, "historical-source-hash"))
    monkeypatch.setattr(comparison, "E2BSandboxFactory", SimpleNamespace(from_settings=lambda _: after))

    async def run(_provider, _settings, case, observed_factory, **_kwargs):
        observed = await observed_factory.create()
        await observed.write_files(
            {
                "/workspace/timeout-checkpoint.json": json.dumps(
                    {
                        "description": "Recovered clinic checkpoint",
                        "source_sha256": hashlib.sha256(fixture_text(case.fixture).encode()).hexdigest(),
                    }
                ),
                "/workspace/timeout-attempts.txt": "once\n",
            }
        )
        result = await observed.run("python3 diagnostic", timeout_seconds=2)
        observed.timeout_ended = time.perf_counter() - 10
        await observed.close()
        return CaseRun(case.id, case.category, not result.sandbox_terminated, 1.0, 2, tools=["bash(failed)"])

    monkeypatch.setattr(comparison, "run_case", run)
    settings = AiSettings(provider_base_url="http://unused.invalid", provider_api_key="unused", provider_model="test")
    assert asyncio.run(comparison.benchmark(settings, "HEAD", tmp_path, repeat=2, jobs=4))
    for arm in ("before", "after"):
        progress = json.loads((tmp_path / arm / "progress.json").read_text())
        assert progress == {"status": "complete", "completed": 2, "expected": 2}
        assert len((tmp_path / arm / "results.jsonl").read_text().splitlines()) == 2
        assert len(list((tmp_path / arm / "cases").glob("*.json"))) == 2
    metrics = json.loads((tmp_path / "attempt-metrics.json").read_text())
    assert metrics["after"]["total_tokens"]["mean"] is None
    assert metrics["after"]["tool_calls"]["mean"] == 1
    matched = json.loads((tmp_path / "after/baseline-comparison.json").read_text())
    assert matched["cases"][CASE_ID]["passing_pairs"] == 0
