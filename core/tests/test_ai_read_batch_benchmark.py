"""Tests for the isolated E2B read-batch benchmark."""

import asyncio
import json

import pytest

from nurse_scheduling.ai.sandbox.fake import FakeSandboxBackend

from .ai_eval.read_batch_benchmark import _read_batch, _summarize, _write_report


def test_read_batch_runs_only_the_concurrent_mode_in_parallel():
    class TrackingBackend(FakeSandboxBackend):
        def __init__(self) -> None:
            super().__init__("fake-1", initial_files={"/workspace/file": b"content"})
            self.active = 0
            self.max_active = 0

        async def read_file(self, path: str) -> bytes:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0)
            content = await super().read_file(path)
            self.active -= 1
            return content

    async def exercise():
        sequential = TrackingBackend()
        concurrent = TrackingBackend()
        await _read_batch(sequential, "/workspace/file", 3, "sequential")
        await _read_batch(concurrent, "/workspace/file", 3, "concurrent")
        return sequential.max_active, concurrent.max_active

    assert asyncio.run(exercise()) == (1, 3)


def test_summary_reports_median_and_inclusive_p95():
    summary = _summarize([1.0, 2.0, 3.0])

    assert summary.median_seconds == 2.0
    assert summary.p95_seconds == pytest.approx(2.9)


def test_report_writes_machine_and_human_readable_results(tmp_path):
    result = {
        "config": {"runs": 2, "calls_per_batch": 3, "file_bytes": 1024},
        "sequential": {"median_seconds": 0.3, "p95_seconds": 0.4, "samples_seconds": [0.2, 0.4]},
        "concurrent": {"median_seconds": 0.1, "p95_seconds": 0.2, "samples_seconds": [0.1, 0.1]},
        "median_speedup": 3.0,
    }

    summary = _write_report(result, tmp_path / "report")

    assert "Median speedup: **3.000x**" in summary.read_text(encoding="utf-8")
    assert json.loads((summary.parent / "results.json").read_text(encoding="utf-8")) == result
