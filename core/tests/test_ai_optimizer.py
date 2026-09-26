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
import threading
from collections.abc import AsyncIterator

import httpx
import pytest

from nurse_scheduling.ai.optimizer import (
    HttpOptimizerBackend,
    OptimizerArtifact,
    OptimizerError,
    OptimizerJobPayload,
    OptimizerResultUnavailable,
    SessionOptimizer,
    optimizer_tool_definition,
)
from nurse_scheduling.ai.session_events import SessionEventBroker

from .ai_test_helper import base_schedule_payload, optimizer_workbook_bytes, parse_schedule, schedule_yaml

TEST_SCHEDULE = schedule_yaml()
WORKBOOK_BYTES = optimizer_workbook_bytes()


def test_tool_description_explains_the_default_timeout() -> None:
    function = optimizer_tool_definition()["function"]

    assert "configured default" in function["description"]
    assert "Default: 300 seconds" in function["parameters"]["properties"]["timeout_seconds"]["description"]
    configured = optimizer_tool_definition(420)["function"]
    assert "Default: 420 seconds" in configured["parameters"]["properties"]["timeout_seconds"]["description"]


class FakeOptimizerBackend:
    """Expose deterministic state transitions without running a solver."""

    def __init__(self, result_bytes: bytes = WORKBOOK_BYTES) -> None:
        self.submissions: list[tuple[str, int | None]] = []
        self.result_bytes = result_bytes
        self.release = asyncio.Event()
        self.finish_requests: list[str] = []
        self.cancel_requests: list[str] = []
        self.closed = False
        self.deleted: list[str] = []
        self.submit_gate: asyncio.Event | None = None
        self.submit_entered = asyncio.Event()
        self.submit_error = False
        self.status_failures = 0
        self.status_check_attempted = asyncio.Event()
        self.status_outage_observed = asyncio.Event()
        self.final_state = "completed"
        self.finish_gate: asyncio.Event | None = None
        self.result_gate: asyncio.Event | None = None
        self.result_entered = asyncio.Event()
        self.deleted_event = asyncio.Event()

    async def submit(self, schedule_yaml: str, timeout_seconds: int | None) -> OptimizerJobPayload:
        self.submit_entered.set()
        if self.submit_gate is not None:
            await self.submit_gate.wait()
        if self.submit_error:
            raise OptimizerError("The optimizer request failed.")
        self.submissions.append((schedule_yaml, timeout_seconds))
        return OptimizerJobPayload(id=f"remote-{len(self.submissions)}", state="running")

    async def get(self, job_id: str) -> OptimizerJobPayload:
        self.status_check_attempted.set()
        if self.status_failures > 0:
            self.status_failures -= 1
            if self.status_failures == 0:
                self.status_outage_observed.set()
            raise OptimizerError("The optimizer request failed.")
        if not self.release.is_set():
            return OptimizerJobPayload(id=job_id, state="running")
        if self.final_state != "completed":
            return OptimizerJobPayload(
                id=job_id,
                state=self.final_state,
                terminal=True,
                error={"code": "solver_failed"},
            )
        return OptimizerJobPayload(
            id=job_id,
            state="completed",
            terminal=True,
            result={"outcome": "feasible", "score": 17},
            links={"schedule": f"/optimize/{job_id}/xlsx"},
        )

    async def progress_events(self, job_id: str) -> AsyncIterator[dict[str, object]]:
        if False:
            yield {"job_id": job_id}

    async def finish_now(self, job_id: str) -> OptimizerJobPayload:
        self.finish_requests.append(job_id)
        self.release.set()
        if self.finish_gate is not None:
            await self.finish_gate.wait()
        return OptimizerJobPayload(id=job_id, state="running")

    async def cancel(self, job_id: str) -> OptimizerJobPayload:
        self.cancel_requests.append(job_id)
        return OptimizerJobPayload(id=job_id, state="cancelled", terminal=True)

    async def result_artifact(self, _job: OptimizerJobPayload) -> OptimizerArtifact:
        self.result_entered.set()
        if self.result_gate is not None:
            await self.result_gate.wait()
        return OptimizerArtifact(
            self.result_bytes,
            "optimized-schedule.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    async def close(self) -> None:
        self.closed = True

    async def delete(self, job_id: str) -> None:
        self.deleted.append(job_id)
        self.deleted_event.set()


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
            "http://api:8000",
            "optimizer-token",
            5,
            1_000_000,
            transport=httpx.MockTransport(handle),
        )

        submitted = await backend.submit("description: accepted\n", 30)
        finished = await backend.finish_now(submitted.id)
        cancelled = await backend.cancel(submitted.id)
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
        assert cancelled.state == "running"
        assert artifact.content == b"workbook"
        assert [request.url.path for request in requests] == [
            "/optimize",
            "/optimize/remote-1/finish-now",
            "/optimize/remote-1/cancel",
            "/optimize/remote-1/xlsx",
            "/optimize/remote-1",
        ]
        assert all(request.headers["authorization"] == "Bearer optimizer-token" for request in requests)
        assert "multipart/form-data" in requests[0].headers["content-type"]
        assert b"description: accepted\n" in requests[0].content
        assert b'name="prettify"\r\n\r\ntrue' in requests[0].content
        assert b'name="timeout"' in requests[0].content

    asyncio.run(scenario())


def test_http_backend_resumes_optimizer_progress_with_its_server_side_token() -> None:
    async def scenario() -> None:
        requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(
                    200,
                    text='id: 1\nevent: job.progressed\ndata: {"currentBestScore": 12, "elapsedSeconds": 1}\n\n',
                )
            return httpx.Response(
                200,
                text=(
                    'id: 2\nevent: job.progressed\ndata: {"currentBestScore": 18, "elapsedSeconds": 2, '
                    '"source": "solver", "solutionIndex": 2, "commentCount": 1}\n\n'
                    'id: 3\nevent: job.state_changed\ndata: {"state": "completed", "terminal": true}\n\n'
                ),
            )

        backend = HttpOptimizerBackend(
            "http://api:8000", "optimizer-token", 5, 1_000_000, transport=httpx.MockTransport(handle)
        )
        points = [point async for point in backend.progress_events("remote-1")]
        await backend.close()

        assert points == [
            {"currentBestScore": 12, "elapsedSeconds": 1, "solutionIndex": None, "commentCount": None},
            {
                "currentBestScore": 18,
                "elapsedSeconds": 2,
                "source": "solver",
                "solutionIndex": 2,
                "commentCount": 1,
            },
        ]
        assert requests[0].headers["authorization"] == "Bearer optimizer-token"
        assert "last-event-id" not in requests[0].headers
        assert requests[1].headers["last-event-id"] == "1"

    asyncio.run(scenario())


def test_http_backend_replays_an_optimizer_event_cut_off_before_its_delimiter() -> None:
    async def scenario() -> None:
        requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(
                    200,
                    text=(
                        'id: 1\nevent: job.progressed\ndata: {"currentBestScore": 12, "elapsedSeconds": 1}\n\n'
                        'id: 2\nevent: job.progressed\ndata: {"currentBestScore": 9, "elapsedSeconds": 2}\n'
                    ),
                )
            return httpx.Response(
                200,
                text=(
                    'id: 2\nevent: job.progressed\ndata: {"currentBestScore": 9, "elapsedSeconds": 2}\n\n'
                    'id: 3\nevent: job.state_changed\ndata: {"state": "completed", "terminal": true}\n\n'
                ),
            )

        backend = HttpOptimizerBackend(
            "http://api:8000", "optimizer-token", 5, 1_000_000, transport=httpx.MockTransport(handle)
        )
        points = [point async for point in backend.progress_events("remote-1")]
        await backend.close()

        assert points == [
            {"currentBestScore": 12, "elapsedSeconds": 1, "solutionIndex": None, "commentCount": None},
            {"currentBestScore": 9, "elapsedSeconds": 2, "solutionIndex": None, "commentCount": None},
        ]
        assert requests[1].headers["last-event-id"] == "1"

    asyncio.run(scenario())


def test_optimizer_progress_replay_does_not_displace_background_turn_events() -> None:
    broker = SessionEventBroker(max_events_per_session=2, max_progress_events_per_session=2)
    broker.publish("session-1", "run_start", {"message_id": "turn-1"})
    for score in (1, 2, 3):
        broker.publish("session-1", "optimization_progress", {"score": score})
    broker.publish("session-1", "done", {"message_id": "turn-1"})

    events = broker.events_after("session-1")
    assert [(event.id, event.type) for event in events] == [
        (1, "run_start"),
        (3, "optimization_progress"),
        (4, "optimization_progress"),
        (5, "done"),
    ]


def test_background_and_progress_replay_have_separate_default_limits() -> None:
    broker = SessionEventBroker()
    for index in range(1001):
        broker.publish("session-1", "text_delta", {"index": index})
    for index in range(101):
        broker.publish("session-1", "optimization_progress", {"index": index})

    events = broker.events_after("session-1")
    assert len(events) == 1100
    assert events[0].data["index"] == 1
    assert events[999].data["index"] == 1000
    assert events[1000].data["index"] == 1
    assert events[-1].data["index"] == 100


def test_retiring_a_session_ends_its_open_event_stream() -> None:
    async def scenario() -> None:
        broker = SessionEventBroker()
        received: list[str | None] = []

        async def consume() -> None:
            async for event in broker.stream("session-1", 0):
                received.append(event.type if event is not None else None)

        reader = asyncio.create_task(consume())
        broker.publish("session-1", "run_start", {"message_id": "turn-1"})
        await asyncio.sleep(0)
        broker.forget_session("session-1")
        await asyncio.wait_for(reader, timeout=1)

        assert received == ["run_start"]
        assert "session-1" not in broker._signals

    asyncio.run(scenario())


def test_a_rejected_request_tells_the_model_what_the_optimizer_refused() -> None:
    async def scenario() -> None:
        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/finish-now"):
                return httpx.Response(500, json={"detail": "Job store unavailable"})
            return httpx.Response(400, json={"detail": "Optimization timeout must be between 1 and 3600 seconds"})

        backend = HttpOptimizerBackend(
            "http://api:8000",
            "optimizer-token",
            5,
            1_000_000,
            transport=httpx.MockTransport(handle),
        )

        with pytest.raises(OptimizerError, match="between 1 and 3600 seconds"):
            await backend.submit("description: rejected\n", 100_000)
        with pytest.raises(OptimizerError, match="^The optimizer request failed.$"):
            await backend.finish_now("remote-1")
        await backend.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("body", [[], "rejected", 42, None])
def test_a_non_object_rejection_keeps_the_optimizer_error_path(body: object) -> None:
    async def scenario() -> None:
        backend = HttpOptimizerBackend(
            "http://api:8000",
            "optimizer-token",
            5,
            1_000_000,
            transport=httpx.MockTransport(lambda _request: httpx.Response(400, json=body)),
        )
        with pytest.raises(OptimizerError, match="rejected the request with status 400"):
            await backend.submit("description: rejected\n", 30)
        await backend.close()

    asyncio.run(scenario())


def test_a_rejected_submission_reports_the_reason_to_the_model() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        backend.submit_error = True

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            return None

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        rejected = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')

        assert not rejected.ok
        assert "The optimizer request failed." in rejected.text
        await optimizer.close()

    asyncio.run(scenario())


def test_start_returns_immediately_and_completion_wakes_the_agent() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        completions: list[tuple[str, str, OptimizerArtifact | None]] = []
        updates: list[tuple[str, dict[str, object]]] = []
        completed = asyncio.Event()

        async def on_completion(session_id: str, prompt: str, artifact: OptimizerArtifact | None) -> None:
            completions.append((session_id, prompt, artifact))
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
            TEST_SCHEDULE,
            json.dumps({"action": "start", "timeout_seconds": 30}),
        )

        assert outcome.ok
        assert "background" in outcome.text
        assert len(backend.submissions) == 1
        assert backend.submissions[0][1] == 30
        assert "description" not in parse_schedule(backend.submissions[0][0])
        assert not completed.is_set()

        backend.release.set()
        await asyncio.wait_for(completed.wait(), timeout=1)
        limited = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')

        assert completions[0][0] == "session-1"
        assert '"score": 17' in completions[0][1]
        assert "/workspace/optimizer-results/optimized-schedule.xlsx" in completions[0][1]
        assert repr(WORKBOOK_BYTES) not in completions[0][1]
        assert completions[0][2] is not None
        assert completions[0][2].content == WORKBOOK_BYTES
        assert [update[1]["state"] for update in updates] == ["running", "completed"]
        local_job_id = str(updates[-1][1]["job_id"])
        artifact = await optimizer.result_artifact("session-1", local_job_id)
        assert artifact.content == WORKBOOK_BYTES
        assert await optimizer.latest_result_artifact("session-1") == artifact
        assert await optimizer.latest_result_artifact("session-2") is None
        inspection = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"inspect_result"}')
        assert not inspection.ok
        assert backend.deleted == ["remote-1"]
        assert not limited.ok
        assert "limit of 1" in limited.text
        await optimizer.close()
        assert backend.closed

    asyncio.run(scenario())


def test_progress_reaches_browser_updates_without_entering_the_agent_prompt() -> None:
    class ProgressBackend(FakeOptimizerBackend):
        async def progress_events(self, job_id: str) -> AsyncIterator[dict[str, object]]:
            yield {"currentBestScore": 23, "elapsedSeconds": 2, "source": "solver"}
            await self.release.wait()

    async def scenario() -> None:
        backend = ProgressBackend()
        updates: list[dict[str, object]] = []
        prompts: list[str] = []
        progress_seen = asyncio.Event()
        completed = asyncio.Event()

        async def on_update(_session_id: str, update: dict[str, object]) -> None:
            updates.append(update)
            if "progress" in update:
                progress_seen.set()

        async def on_completion(_session_id: str, prompt: str, _artifact: OptimizerArtifact | None) -> None:
            prompts.append(prompt)
            completed.set()

        optimizer = SessionOptimizer(
            backend, poll_interval_seconds=0.001, on_completion=on_completion, on_update=on_update
        )
        await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')
        await asyncio.wait_for(progress_seen.wait(), timeout=1)
        assert updates[1]["progress"] == {"currentBestScore": 23, "elapsedSeconds": 2, "source": "solver"}
        assert not prompts

        backend.release.set()
        await asyncio.wait_for(completed.wait(), timeout=2)
        assert "currentBestScore" not in prompts[0]
        await optimizer.close()

    asyncio.run(scenario())


def test_session_optimizer_restores_named_people_in_download_and_attached_result() -> None:
    async def scenario() -> None:
        payload = base_schedule_payload()
        payload["people"]["items"][0]["id"] = "Alice"
        payload["people"]["items"][1]["id"] = "Bob"
        payload["people"]["groups"][0]["members"] = ["Alice", "Bob"]
        payload["preferences"][1]["person"] = ["Alice"]
        original_yaml = schedule_yaml(payload)
        backend = FakeOptimizerBackend(optimizer_workbook_bytes(("P1", "P2")))
        completed = asyncio.Event()
        attached_result: OptimizerArtifact | None = None

        async def on_completion(_session_id: str, _prompt: str, artifact: OptimizerArtifact | None) -> None:
            nonlocal attached_result
            attached_result = artifact
            completed.set()

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        started = await optimizer.execute("session-1", original_yaml, '{"action":"start"}')
        assert started.ok
        assert "Alice" not in backend.submissions[0][0]
        assert "description" not in backend.submissions[0][0]

        backend.release.set()
        await asyncio.wait_for(completed.wait(), timeout=1)
        job_id = started.text.split("job ", 1)[1].split(" ", 1)[0]
        artifact = await optimizer.result_artifact("session-1", job_id)
        assert artifact.content != backend.result_bytes
        assert attached_result == artifact
        await optimizer.close()

    asyncio.run(scenario())


def test_oversized_restored_result_is_not_attached_or_downloadable() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        completed = asyncio.Event()
        received: list[tuple[str, OptimizerArtifact | None]] = []

        async def on_completion(_session_id: str, prompt: str, artifact: OptimizerArtifact | None) -> None:
            received.append((prompt, artifact))
            completed.set()

        optimizer = SessionOptimizer(
            backend,
            poll_interval_seconds=0.001,
            on_completion=on_completion,
            max_result_bytes=1,
        )
        started = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')
        backend.release.set()
        await asyncio.wait_for(completed.wait(), timeout=1)

        assert received[0][1] is None
        assert '"download_available": false' in received[0][0]
        assert await optimizer.latest_result_artifact("session-1") is None
        job_id = started.text.split("job ", 1)[1].split(" ", 1)[0]
        with pytest.raises(OptimizerResultUnavailable):
            await optimizer.result_artifact("session-1", job_id)
        await optimizer.close()

    asyncio.run(scenario())


def test_finish_now_controls_the_active_job_and_a_second_run_waits_for_terminal_state() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        completed = asyncio.Event()

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completed.set()

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        first = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')
        duplicate = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')
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

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completions.put_nowait(None)

        optimizer = SessionOptimizer(
            backend,
            poll_interval_seconds=0.001,
            on_completion=on_completion,
            max_cached_result_bytes=len(WORKBOOK_BYTES),
        )
        first = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')
        backend.release.set()
        await asyncio.wait_for(completions.get(), timeout=1)
        first_id = first.text.split("job ", 1)[1].split(" ", 1)[0]

        await optimizer.execute("session-2", TEST_SCHEDULE, '{"action":"start"}')
        await asyncio.wait_for(completions.get(), timeout=1)

        with pytest.raises(OptimizerResultUnavailable):
            await optimizer.result_artifact("session-1", first_id)
        await optimizer.close()

    asyncio.run(scenario())


def test_absolute_result_links_are_not_followed_with_the_optimizer_token() -> None:
    async def scenario() -> None:
        requests: list[httpx.Request] = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(200, content=b"workbook")

        backend = HttpOptimizerBackend(
            "http://api:8000",
            "optimizer-token",
            5,
            1_000_000,
            transport=httpx.MockTransport(handle),
        )
        for link in ("https://elsewhere.example/steal", "//elsewhere.example/steal", ""):
            job = OptimizerJobPayload(id="remote-1", state="completed", terminal=True, links={"schedule": link})
            with pytest.raises(OptimizerError):
                await backend.result_artifact(job)
        await backend.close()

        assert requests == []

    asyncio.run(scenario())


@pytest.mark.parametrize("base_url", ["http://optimizer.example:8000", "http://192.0.2.10:8000", "ftp://api:8000"])
def test_credentialed_optimizer_requires_https_outside_local_endpoints(base_url: str) -> None:
    with pytest.raises(ValueError, match="must use HTTPS"):
        HttpOptimizerBackend(base_url, "optimizer-token", 5, 1_000_000)


def test_an_omitted_timeout_submits_the_advertised_default() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            return None

        optimizer = SessionOptimizer(
            backend,
            poll_interval_seconds=0.001,
            on_completion=on_completion,
            default_timeout_seconds=420,
        )
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok

        assert backend.submissions[0][1] == 420
        assert "Default: 420 seconds" in str(optimizer_tool_definition(420))
        await optimizer.close()

    asyncio.run(scenario())


def test_a_finished_run_without_a_workbook_hides_the_previous_result() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        completions = asyncio.Queue[None]()

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completions.put_nowait(None)

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        backend.release.set()
        await asyncio.wait_for(completions.get(), timeout=1)
        assert await optimizer.latest_result_artifact("session-1") is not None

        backend.release.clear()
        backend.final_state = "failed"
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        assert await optimizer.latest_result_artifact("session-1") is not None
        backend.release.set()
        await asyncio.wait_for(completions.get(), timeout=1)

        assert await optimizer.latest_result_artifact("session-1") is None
        await optimizer.close()

    asyncio.run(scenario())


def test_finish_now_does_not_revive_a_job_that_already_completed() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        backend.finish_gate = asyncio.Event()
        completions = asyncio.Queue[None]()

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completions.put_nowait(None)

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        finishing = asyncio.create_task(optimizer.execute("session-1", "ignored", '{"action":"finish_now"}'))
        await asyncio.wait_for(completions.get(), timeout=1)
        backend.finish_gate.set()
        assert (await asyncio.wait_for(finishing, timeout=1)).ok

        status = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"status"}')
        assert "completed" in status.text
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        await optimizer.close()

    asyncio.run(scenario())


def test_finish_now_waits_for_workbook_before_terminal_update() -> None:
    class TerminalFinishBackend(FakeOptimizerBackend):
        async def finish_now(self, job_id: str) -> OptimizerJobPayload:
            self.release.set()
            return OptimizerJobPayload(id=job_id, state="completed", terminal=True)

    async def scenario() -> None:
        backend = TerminalFinishBackend()
        backend.result_gate = asyncio.Event()
        updates: list[dict[str, object]] = []
        completed = asyncio.Event()

        async def on_update(_session_id: str, update: dict[str, object]) -> None:
            updates.append(update)

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completed.set()

        optimizer = SessionOptimizer(
            backend, poll_interval_seconds=0.001, on_completion=on_completion, on_update=on_update
        )
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        assert (await optimizer.execute("session-1", "ignored", '{"action":"finish_now"}')).ok
        await asyncio.wait_for(backend.result_entered.wait(), timeout=1)
        assert not [update for update in updates if update["terminal"]]

        backend.result_gate.set()
        await asyncio.wait_for(completed.wait(), timeout=1)
        assert [update["downloadable"] for update in updates if update["terminal"]] == [True]
        await optimizer.close()

    asyncio.run(scenario())


def test_immediately_completed_submission_waits_for_workbook_before_terminal_update() -> None:
    class ImmediateBackend(FakeOptimizerBackend):
        async def submit(self, schedule_yaml: str, timeout_seconds: int | None) -> OptimizerJobPayload:
            self.submissions.append((schedule_yaml, timeout_seconds))
            return OptimizerJobPayload(id="remote-1", state="completed", terminal=True)

    async def scenario() -> None:
        backend = ImmediateBackend()
        backend.result_gate = asyncio.Event()
        updates: list[dict[str, object]] = []
        completed = asyncio.Event()

        async def on_update(_session_id: str, update: dict[str, object]) -> None:
            updates.append(update)

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completed.set()

        optimizer = SessionOptimizer(
            backend, poll_interval_seconds=0.001, on_completion=on_completion, on_update=on_update
        )
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        await asyncio.wait_for(backend.result_entered.wait(), timeout=1)
        assert not updates

        backend.result_gate.set()
        await asyncio.wait_for(completed.wait(), timeout=1)
        assert [update["downloadable"] for update in updates if update["terminal"]] == [True]
        await optimizer.close()

    asyncio.run(scenario())


def test_a_brief_status_outage_does_not_end_a_running_job() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        backend.status_failures = 5
        completions: list[str] = []
        completed = asyncio.Event()

        async def on_completion(_session_id: str, prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completions.append(prompt)
            completed.set()

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        backend.release.set()
        await asyncio.wait_for(completed.wait(), timeout=1)

        assert '"state": "completed"' in completions[0]
        await optimizer.close()

    asyncio.run(scenario())


def test_a_sustained_status_outage_does_not_abandon_the_remote_job() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        backend.status_failures = 2
        completions: list[str] = []
        completed = asyncio.Event()

        async def on_completion(_session_id: str, prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completions.append(prompt)
            completed.set()

        optimizer = SessionOptimizer(
            backend,
            poll_interval_seconds=0.001,
            on_completion=on_completion,
            status_failure_grace_seconds=0,
        )
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        await asyncio.wait_for(backend.status_outage_observed.wait(), timeout=1)
        assert not completed.is_set()
        assert (await optimizer.execute("session-1", "", '{"action":"status"}')).text.endswith("is running.")
        assert not (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        assert len(backend.submissions) == 1

        backend.release.set()
        await asyncio.wait_for(completed.wait(), timeout=1)

        assert '"state": "completed"' in completions[0]
        await optimizer.close()

    asyncio.run(scenario())


def test_a_slow_submission_does_not_block_other_sessions() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        backend.submit_gate = asyncio.Event()

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            return None

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        starting = asyncio.create_task(optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}'))
        await asyncio.wait_for(backend.submit_entered.wait(), timeout=1)

        assert await asyncio.wait_for(optimizer.latest_result_artifact("session-2"), timeout=1) is None
        duplicate = await asyncio.wait_for(
            optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}'),
            timeout=1,
        )
        assert not duplicate.ok
        assert "already being submitted" in duplicate.text

        backend.submit_gate.set()
        assert (await asyncio.wait_for(starting, timeout=1)).ok
        await optimizer.close()

    asyncio.run(scenario())


def test_a_cancelled_start_returns_the_reserved_run() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        backend.submit_gate = asyncio.Event()

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            return None

        optimizer = SessionOptimizer(
            backend,
            poll_interval_seconds=0.001,
            on_completion=on_completion,
            max_runs_per_session=1,
        )
        stopped = asyncio.create_task(optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}'))
        await asyncio.wait_for(backend.submit_entered.wait(), timeout=1)
        stopped.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stopped

        backend.submit_gate.set()
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        await optimizer.close()

    asyncio.run(scenario())


def test_a_rejected_submission_returns_the_reserved_run() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        backend.submit_error = True

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            return None

        optimizer = SessionOptimizer(
            backend,
            poll_interval_seconds=0.001,
            on_completion=on_completion,
            max_runs_per_session=1,
        )
        rejected = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')
        backend.submit_error = False
        retried = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')

        assert not rejected.ok
        assert retried.ok
        await optimizer.close()

    asyncio.run(scenario())


def test_a_retired_session_releases_its_runs_and_retained_workbooks() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        completions = asyncio.Queue[None]()

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completions.put_nowait(None)

        optimizer = SessionOptimizer(
            backend,
            poll_interval_seconds=0.001,
            on_completion=on_completion,
            max_runs_per_session=1,
        )
        started = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')
        backend.release.set()
        await asyncio.wait_for(completions.get(), timeout=1)
        job_id = started.text.split("job ", 1)[1].split(" ", 1)[0]
        assert (await optimizer.result_artifact("session-1", job_id)).content == WORKBOOK_BYTES

        optimizer.forget_session("session-1")

        assert await optimizer.latest_result_artifact("session-1") is None
        with pytest.raises(OptimizerResultUnavailable):
            await optimizer.result_artifact("session-1", job_id)
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        await optimizer.close()

    asyncio.run(scenario())


def test_retirement_during_submission_does_not_restore_session_state() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        backend.submit_gate = asyncio.Event()
        completions: list[str] = []
        updates: list[dict[str, object]] = []

        async def on_completion(session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completions.append(session_id)

        async def on_update(_session_id: str, update: dict[str, object]) -> None:
            updates.append(update)

        optimizer = SessionOptimizer(
            backend, poll_interval_seconds=0.001, on_completion=on_completion, on_update=on_update
        )
        starting = asyncio.create_task(optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}'))
        await asyncio.wait_for(backend.submit_entered.wait(), timeout=1)
        optimizer.forget_session("session-1")
        backend.submit_gate.set()
        assert not (await asyncio.wait_for(starting, timeout=1)).ok
        await asyncio.wait_for(backend.deleted_event.wait(), timeout=1)

        assert await optimizer.latest_result_artifact("session-1") is None
        assert optimizer._cached_artifact_bytes == 0
        assert backend.cancel_requests == ["remote-1"]
        assert not completions and not updates
        await optimizer.close()

    asyncio.run(scenario())


def test_retirement_cancels_a_running_remote_job() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        completions: list[str] = []

        async def on_completion(session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completions.append(session_id)

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        await asyncio.wait_for(backend.status_check_attempted.wait(), timeout=1)
        optimizer.forget_session("session-1")
        await asyncio.wait_for(backend.deleted_event.wait(), timeout=1)
        await asyncio.wait_for(asyncio.gather(*tuple(optimizer._tasks)), timeout=1)

        assert backend.cancel_requests == ["remote-1"]
        assert not completions
        await optimizer.close()

    asyncio.run(scenario())


def test_retired_session_waits_for_remote_cancellation_before_cleanup() -> None:
    class CancellingBackend(FakeOptimizerBackend):
        def __init__(self) -> None:
            super().__init__()
            self.cancel_requested = asyncio.Event()
            self.final_state = "cancelled"

        async def cancel(self, job_id: str) -> OptimizerJobPayload:
            self.cancel_requests.append(job_id)
            self.cancel_requested.set()
            return OptimizerJobPayload(id=job_id, state="cancelling")

    async def scenario() -> None:
        backend = CancellingBackend()
        completions: list[str] = []

        async def on_completion(session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completions.append(session_id)

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        optimizer.forget_session("session-1")
        await asyncio.wait_for(backend.cancel_requested.wait(), timeout=1)
        assert not backend.deleted_event.is_set()

        backend.release.set()
        await asyncio.wait_for(backend.deleted_event.wait(), timeout=1)
        await asyncio.wait_for(asyncio.gather(*tuple(optimizer._tasks)), timeout=1)
        assert backend.deleted == ["remote-1"]
        assert not completions
        await optimizer.close()

    asyncio.run(scenario())


def test_retirement_during_result_download_does_not_retain_or_announce_it() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        backend.result_gate = asyncio.Event()
        completions: list[str] = []

        async def on_completion(session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completions.append(session_id)

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        assert (await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')).ok
        backend.release.set()
        await asyncio.wait_for(backend.result_entered.wait(), timeout=1)
        optimizer.forget_session("session-1")
        backend.result_gate.set()
        await asyncio.wait_for(backend.deleted_event.wait(), timeout=1)

        assert await optimizer.latest_result_artifact("session-1") is None
        assert optimizer._cached_artifact_bytes == 0
        assert not completions
        await optimizer.close()

    asyncio.run(scenario())


def test_session_limit_preserves_a_live_sessions_completed_result() -> None:
    async def scenario() -> None:
        backend = FakeOptimizerBackend()
        completed = asyncio.Event()

        async def on_completion(_session_id: str, _prompt: str, _artifact: OptimizerArtifact | None) -> None:
            completed.set()

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion, max_sessions=1)
        started = await optimizer.execute("session-1", TEST_SCHEDULE, '{"action":"start"}')
        backend.release.set()
        await asyncio.wait_for(completed.wait(), timeout=1)
        blocked = await optimizer.execute("session-2", TEST_SCHEDULE, '{"action":"start"}')
        job_id = started.text.split("job ", 1)[1].split(" ", 1)[0]

        assert not blocked.ok
        assert (await optimizer.result_artifact("session-1", job_id)).content == WORKBOOK_BYTES
        await optimizer.close()

    asyncio.run(scenario())


def test_retirement_during_preparation_revokes_submission(monkeypatch) -> None:
    from nurse_scheduling.ai import optimizer as module

    entered = threading.Event()
    release = threading.Event()
    prepare = module.prepare_optimizer_schedule

    def blocked_prepare(*args):
        entered.set()
        assert release.wait(timeout=2)
        return prepare(*args)

    monkeypatch.setattr(module, "prepare_optimizer_schedule", blocked_prepare)

    async def scenario():
        backend = FakeOptimizerBackend()

        async def on_completion(*_args):
            pytest.fail("A retired job cannot wake the assistant")

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        starting = asyncio.create_task(optimizer.execute("session", TEST_SCHEDULE, "{}"))
        assert await asyncio.to_thread(entered.wait, 1)
        optimizer.forget_session("session")
        release.set()
        assert not (await starting).ok
        assert backend.submissions == []
        assert optimizer._sessions == {}
        await optimizer.close()

    asyncio.run(scenario())


def test_cancelled_submission_cleans_its_late_remote_response_without_revoking_the_retry() -> None:
    async def scenario():
        backend = FakeOptimizerBackend()
        backend.submit_gate = asyncio.Event()

        async def on_completion(*_args):
            return None

        optimizer = SessionOptimizer(
            backend, poll_interval_seconds=0.001, on_completion=on_completion, max_runs_per_session=1
        )
        starting = asyncio.create_task(optimizer.execute("session", TEST_SCHEDULE, "{}"))
        await backend.submit_entered.wait()
        starting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await starting
        # The abandoned submission and its retry now have distinct owners.
        retry = asyncio.create_task(optimizer.execute("session", TEST_SCHEDULE, "{}"))
        backend.submit_gate.set()
        assert (await retry).ok
        await asyncio.wait_for(backend.deleted_event.wait(), timeout=1)
        assert backend.cancel_requests == ["remote-1"]
        assert backend.deleted == ["remote-1"]
        assert optimizer._latest("session").remote_id == "remote-2"
        assert optimizer._sessions["session"].runs == 1
        await optimizer.close()
        assert backend.closed
        assert optimizer._tasks == set()
        assert optimizer._submissions == set()

    asyncio.run(scenario())


def test_shutdown_during_followup_does_not_delete_the_remote_job_twice() -> None:
    async def scenario():
        backend = FakeOptimizerBackend()
        reviewing = asyncio.Event()

        async def on_completion(*_args):
            reviewing.set()
            await asyncio.Event().wait()

        optimizer = SessionOptimizer(backend, poll_interval_seconds=0.001, on_completion=on_completion)
        assert (await optimizer.execute("session", TEST_SCHEDULE, "{}")).ok
        backend.release.set()
        await reviewing.wait()
        await optimizer.close()
        assert backend.deleted == ["remote-1"]

    asyncio.run(scenario())
