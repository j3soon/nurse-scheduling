"""Tests for AI-owned background optimizer jobs."""

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
import json

import httpx
import pytest

from nurse_scheduling.ai.optimizer import (
    HttpOptimizerBackend,
    OptimizerArtifact,
    OptimizerJobPayload,
    OptimizerResultUnavailable,
    SessionOptimizer,
    optimizer_tool_definition,
)


def test_tool_description_explains_the_default_timeout() -> None:
    function = optimizer_tool_definition()["function"]

    assert "normally 300 seconds" in function["description"]
    assert "normally 300 seconds" in function["parameters"]["properties"]["timeout_seconds"]["description"]


class FakeOptimizerBackend:
    """Expose deterministic state transitions without running a solver."""

    def __init__(self) -> None:
        self.submissions: list[tuple[str, int | None]] = []
        self.release = asyncio.Event()
        self.finish_requests: list[str] = []
        self.closed = False
        self.deleted: list[str] = []

    async def submit(self, schedule_yaml: str, timeout_seconds: int | None) -> OptimizerJobPayload:
        self.submissions.append((schedule_yaml, timeout_seconds))
        return OptimizerJobPayload(id="remote-1", state="running")

    async def get(self, job_id: str) -> OptimizerJobPayload:
        if not self.release.is_set():
            return OptimizerJobPayload(id=job_id, state="running")
        return OptimizerJobPayload(
            id=job_id,
            state="completed",
            terminal=True,
            result={"outcome": "feasible", "score": 17},
            links={"schedule": f"/optimize/{job_id}/xlsx"},
        )

    async def finish_now(self, job_id: str) -> OptimizerJobPayload:
        self.finish_requests.append(job_id)
        self.release.set()
        return OptimizerJobPayload(id=job_id, state="running")

    async def result_artifact(self, _job: OptimizerJobPayload) -> OptimizerArtifact:
        return OptimizerArtifact(
            b"workbook bytes",
            "optimized-schedule.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    async def close(self) -> None:
        self.closed = True

    async def delete(self, job_id: str) -> None:
        self.deleted.append(job_id)


def test_http_backend_uses_the_existing_optimizer_routes_and_server_side_token() -> None:
    async def scenario() -> None:
        requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "DELETE":
                return httpx.Response(204)
            if request.url.path.endswith("/xlsx"):
                return httpx.Response(200, content=b"workbook")
            return httpx.Response(202, json={"id": "remote-1", "state": "running"})

        backend = HttpOptimizerBackend(
            "http://optimizer:8000",
            "optimizer-token",
            5,
            1_000_000,
            transport=httpx.MockTransport(handle),
        )

        submitted = await backend.submit("description: accepted\n", 30)
        finished = await backend.finish_now(submitted.id)
        artifact = await backend.result_artifact(
            OptimizerJobPayload(
                id=submitted.id,
                state="completed",
                terminal=True,
                links={"schedule": f"/optimize/{submitted.id}/xlsx"},
            )
        )
        await backend.delete(submitted.id)
        await backend.close()

        assert finished.state == "running"
        assert artifact.content == b"workbook"
        assert [request.url.path for request in requests] == [
            "/optimize",
            "/optimize/remote-1/finish-now",
            "/optimize/remote-1/xlsx",
            "/optimize/remote-1",
        ]
        assert all(request.headers["authorization"] == "Bearer optimizer-token" for request in requests)
        assert "multipart/form-data" in requests[0].headers["content-type"]
        assert b"description: accepted\n" in requests[0].content
        assert b'name="timeout"' in requests[0].content

    asyncio.run(scenario())


def test_start_returns_immediately_and_completion_wakes_the_agent() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        completions: list[tuple[str, str]] = []
        updates: list[tuple[str, dict[str, object]]] = []
        completed = asyncio.Event()

        async def on_completion(session_id: str, prompt: str) -> None:
            completions.append((session_id, prompt))
            completed.set()

        async def on_update(session_id: str, update: dict[str, object]) -> None:
            updates.append((session_id, update))

        optimizer = SessionOptimizer(
            backend,
            poll_interval_seconds=0.001,
            on_completion=on_completion,
            on_update=on_update,
            max_runs_per_session=1,
        )
        outcome = await optimizer.execute(
            "session-1",
            "description: accepted\n",
            json.dumps({"action": "start", "timeout_seconds": 30}),
        )

        assert outcome.ok
        assert "background" in outcome.text
        assert backend.submissions == [("description: accepted\n", 30)]
        assert not completed.is_set()

        backend.release.set()
        await asyncio.wait_for(completed.wait(), timeout=1)
        limited = await optimizer.execute("session-1", "description: second\n", '{"action":"start"}')

        assert completions[0][0] == "session-1"
        assert '"score": 17' in completions[0][1]
        assert "cannot inspect that artifact" in completions[0][1]
        assert "workbook bytes" not in completions[0][1]
        assert [update[1]["state"] for update in updates] == ["running", "completed"]
        local_job_id = str(updates[-1][1]["job_id"])
        artifact = await optimizer.result_artifact("session-1", local_job_id)
        assert artifact.content == b"workbook bytes"
        assert backend.deleted == ["remote-1"]
        assert not limited.ok
        assert "limit of 1" in limited.text
        await optimizer.close()
        assert backend.closed

    asyncio.run(scenario())


def test_finish_now_controls_the_active_job_and_a_second_run_waits_for_terminal_state() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        completed = asyncio.Event()

        async def on_completion(_session_id: str, _prompt: str) -> None:
            completed.set()

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        first = await optimizer.execute("session-1", "description: first\n", '{"action":"start"}')
        duplicate = await optimizer.execute("session-1", "description: second\n", '{"action":"start"}')
        finish = await optimizer.execute("session-1", "ignored", '{"action":"finish_now"}')

        assert first.ok
        assert not duplicate.ok
        assert finish.ok
        assert backend.finish_requests == ["remote-1"]
        await asyncio.wait_for(completed.wait(), timeout=1)
        await optimizer.close()

    asyncio.run(scenario())


def test_completed_artifacts_are_evicted_to_bound_process_memory() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        completions = asyncio.Queue[None]()

        async def on_completion(_session_id: str, _prompt: str) -> None:
            completions.put_nowait(None)

        optimizer = SessionOptimizer(
            backend,
            poll_interval_seconds=0.001,
            on_completion=on_completion,
            max_cached_result_bytes=len(b"workbook bytes"),
        )
        first = await optimizer.execute("session-1", "description: first\n", '{"action":"start"}')
        backend.release.set()
        await asyncio.wait_for(completions.get(), timeout=1)
        first_id = first.text.split("job ", 1)[1].split(" ", 1)[0]

        await optimizer.execute("session-2", "description: second\n", '{"action":"start"}')
        await asyncio.wait_for(completions.get(), timeout=1)

        with pytest.raises(OptimizerResultUnavailable):
            await optimizer.result_artifact("session-1", first_id)
        await optimizer.close()

    asyncio.run(scenario())
