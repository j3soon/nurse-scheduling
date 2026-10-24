"""Opt-in real-provider and E2B regression for compaction across chat runs."""

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
import logging
import os
from contextlib import aclosing
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from nurse_scheduling.ai.app import create_app
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.models import ModelCatalog
from nurse_scheduling.ai.provider import OpenAiCompatibleProvider, TextDelta
from nurse_scheduling.ai.sandbox.base import SandboxFileNotFoundError
from nurse_scheduling.ai.sandbox.e2b import E2BSandboxFactory
from nurse_scheduling.ai.transcript import CompactionEntry

from . import test_ai_basic as basic
from .test_ai_history import read_events
from .test_ai_optimizer import FakeOptimizerBackend

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_AI_COMPACTION_INTEGRATION") != "1",
    reason="set RUN_AI_COMPACTION_INTEGRATION=1 with provider and E2B credentials",
)

NOTE = "/workspace/temporary-compaction-note.txt"
EXPECTED = {
    "p1_nights_allowed": False,
    "p2_weekends_allowed": False,
    "dates": ["2031-04-01", "2031-04-02"],
    "note_available": False,
}
FILLER = ("Nonessential audit text. This paragraph adds no constraints or requested changes.\n" * 130)[:9600]
FIRST = (
    "Do not change the current schedule or start optimization. Remember these planning constraints: "
    "P1 must never work nights. P2 must never work weekends. Preserve the planning dates "
    "2031-04-01 and 2031-04-02 as notes, without applying them to the schedule. "
    f"Use a tool to write the text TEMPORARY_NOTE_731 to {NOTE}. "
    "After the write succeeds, reply only READY. The audit text below adds no instructions.\n" + FILLER
)
FOLLOW_UP = (
    "Do not change the schedule, start optimization, or recreate any file. "
    f"Use a tool to check whether {NOTE} exists in the current workspace. "
    "Recall the earlier planning constraints. Reply only with a JSON object containing "
    "p1_nights_allowed and p2_weekends_allowed booleans, dates as the two remembered ISO date strings, "
    "and note_available as the observed file-existence boolean.\n"
)


class TrackingFactory:
    """Use a prebuilt real sandbox and check its filesystem before hydration."""

    def __init__(self, settings):
        self.factory = E2BSandboxFactory.from_settings(settings)
        self.created = []

    async def prepare(self):
        # Source and prompts are uploaded by the workspace. This check uses the prebuilt image.
        pass

    def __getattr__(self, name):
        return getattr(self.factory, name)

    async def create(self, **kwargs):
        sandbox = await self.factory.create(**kwargs)
        try:
            try:
                await sandbox.read_file(NOTE)
                note_exists = True
            except SandboxFileNotFoundError:
                note_exists = False
            self.created.append({"id": sandbox.sandbox_id, "note_exists_before_hydration": note_exists})
            return sandbox
        except BaseException:
            await sandbox.close()
            raise


def assert_complete_tool_pairs(messages):
    pending = set()
    for message in messages:
        if message["role"] == "assistant":
            assert not pending, f"Missing results for {pending}"
            pending = {call["id"] for call in message.get("tool_calls", [])}
        elif message["role"] == "tool":
            assert message["tool_call_id"] in pending, "Orphan tool result"
            pending.remove(message["tool_call_id"])
    assert not pending, f"Incomplete tool exchange: {pending}"


async def run_live_case(name, settings, controls, output):
    factory = TrackingFactory(settings)
    app = create_app(settings=settings, sandbox_factory=factory, optimizer_backend=FakeOptimizerBackend())
    report = {"case": name, "passed": False, "requests": [], "events": [], "sandboxes": factory.created}
    control = {"report": report, "block_summary": False, "summary_started": asyncio.Event()}
    original_observer = app.state.session_event_stream.observer

    def observe(session_id, event):
        if original_observer is not None:
            original_observer(session_id, event)
        report["events"].append({"id": event.id, "type": event.type, "data": deepcopy(event.data)})

    app.state.session_event_stream.observer = observe
    try:
        async with (
            asyncio.timeout(240),
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver", headers=basic.AI_AUTH_HEADERS
            ) as client,
        ):
            session = (await client.post("/sessions", json={"schedule_yaml": basic.schedule_yaml()})).json()["id"]
            owner = client.cookies[basic.OWNER_COOKIE]
            controls[session] = control
            report["session_id"] = session
            models = {model["id"]: model for model in (await client.get("/models")).json()["models"]}
            primary = settings.provider_model
            secondary = os.getenv("AI_COMPACTION_SWITCH_MODEL", "azure/gpt-6-luna")
            assert primary in models, "The configured model is unavailable"

            async def select(model, reasoning="none"):
                options = {option["id"] for option in models[model]["reasoning_options"]}
                response = await client.put(
                    f"/sessions/{session}/model-selection",
                    json={
                        "model": model,
                        "reasoning": reasoning if reasoning in options else "default",
                    },
                )
                assert response.status_code == 200, response.text

            async def submit(question, message_id, *, wait=True):
                response = await client.post(
                    f"/sessions/{session}/messages", json={"message": question, "message_id": message_id}
                )
                assert response.status_code == 200, response.text[:500]
                events = basic.parse_sse(response.text)
                if wait:
                    assert events[-1][0] == "done", events[-1]
                    while app.state.runs.busy(session):
                        await asyncio.sleep(0.02)
                return events

            async def check_facts(question, message_id):
                events = await submit(question, message_id)
                text = "".join(data["text"] for kind, data in events if kind == "delta")
                answer, _ = json.JSONDecoder().raw_decode(text[text.index("{") :])
                assert answer == EXPECTED, answer
                assert any(kind == "tool" and NOTE in data["arguments"] for kind, data in events), "No live file check"
                assert not any(
                    kind == "tool" and data["name"] in {"write", "edit", "optimizer"} for kind, data in events
                )

            await select(primary, "low" if name == "model-switch" else "none")
            initial = await submit(FIRST, "initial")
            assert any(kind == "tool" and data["ok"] and NOTE in data["arguments"] for kind, data in initial)
            assert not any(event["type"] == "compaction_start" for event in report["events"]), (
                "First turn compacted too early"
            )
            if name == "model-switch":
                assert secondary in models and secondary != primary, (
                    "Set AI_COMPACTION_SWITCH_MODEL to another available model"
                )
                await select(secondary)
            if name == "cancellation":
                control["block_summary"] = True
                pending = asyncio.create_task(submit(FOLLOW_UP + FILLER, "cancel", wait=False))
                try:
                    await asyncio.wait_for(control["summary_started"].wait(), timeout=90)
                    response = await client.post(f"/sessions/{session}/stop")
                    assert response.status_code == 202
                    stopped = await pending
                    assert stopped[-1][0] == "stopped", stopped[-1]
                finally:
                    if not pending.done():
                        pending.cancel()
                        await asyncio.gather(pending, return_exceptions=True)
                while app.state.runs.busy(session):
                    await asyncio.sleep(0.02)
                assert not any(
                    isinstance(entry, CompactionEntry) and entry.valid
                    for entry in app.state.session_store.get(session).transcript
                )
                assert any(event["type"] == "compaction_end" and event["data"]["aborted"] for event in report["events"])
                assert any(request.get("cancelled") for request in report["requests"]), (
                    "The real summary stream was not cancelled"
                )
                control["block_summary"] = False
                await check_facts(FOLLOW_UP, "resume")
            else:
                await check_facts(FOLLOW_UP + FILLER, "follow-up")
                if name == "repeated":
                    await check_facts(FOLLOW_UP + FILLER, "repeat")
                elif name == "model-switch":
                    await select(primary)
                    await check_facts(FOLLOW_UP, "switch-back")
            successful = [
                event for event in report["events"] if event["type"] == "compaction_end" and event["data"]["success"]
            ]
            assert successful, "No automatic compaction occurred"
            assert all(event["data"]["estimated_tokens_after"] < event["data"]["tokens_before"] for event in successful)
            for request in report["requests"]:
                assert request["session_id"] == session
                assert_complete_tool_pairs(request["messages"])
            if name == "repeated":
                assert len(successful) >= 2
                assert any(
                    request["summary"] and "<previous-summary>" in str(request["messages"])
                    for request in report["requests"]
                )
            if name == "model-switch":
                assert {request["model"] for request in report["requests"]} == {primary, secondary}
            assert len(factory.created) >= 2 and len({sandbox["id"] for sandbox in factory.created}) == len(
                factory.created
            )
            assert all(not sandbox["note_exists_before_hydration"] for sandbox in factory.created)
            assert app.state.session_store.get(session).schedule_yaml == basic.schedule_yaml()
            frames = await read_events(app, session, owner, until="session_reset", reset=True)
            reset = next(data for _, kind, data in frames if kind == "session_reset")
            assert any(event["type"] == "compaction_end" and event["data"]["success"] for event in reset["events"])
            costs = app.state.session_store.get(session).cost_totals.public()
            assert costs["calls"] >= len(successful) + 2 and costs["pending"] == 0
            report.update(passed=True, successful_compactions=len(successful), costs=costs)
    except Exception as error:
        logging.getLogger(__name__).exception("Live compaction scenario failed: %s", name)
        report.update(error_type=type(error).__name__, error=str(error))
    finally:
        output.mkdir(parents=True, exist_ok=True)
        (output / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def test_real_chat_runs_preserve_context_through_compaction(monkeypatch):
    required = ("AI_PROVIDER_BASE_URL", "AI_PROVIDER_API_KEY", "AI_PROVIDER_MODEL", "E2B_API_KEY")
    missing = [key for key in required if not os.getenv(key)]
    assert not missing, f"Missing live settings: {', '.join(missing)}"
    settings = replace(
        AiSettings.from_env(),
        auth_token=basic.AI_AUTH_TOKEN,
        auth_tokens=(),
        auth_required=True,
        history_postgres_url="",
        provider_profiles_json="",
        max_history_chars=24000,
        max_history_messages=1000,
        max_message_chars=20000,
        request_log_enabled=False,
        cookie_secure=False,
        provider_timeout_seconds=60,
    )
    controls = {}
    original = OpenAiCompatibleProvider._stream_attempt

    async def observe(self, timeout, headers, payload):
        control = controls[headers["x-session-id"]]
        summary = str(payload["messages"][0].get("content", "")).startswith(
            "You are a context summarization assistant."
        )
        request = {
            "session_id": headers["x-session-id"],
            "model": payload["model"],
            "summary": summary,
            "messages": deepcopy(payload["messages"]),
        }
        control["report"]["requests"].append(request)
        try:
            async with aclosing(original(self, timeout, headers, payload)) as events:
                async for event in events:
                    if summary and control["block_summary"] and isinstance(event, TextDelta):
                        control["summary_started"].set()
                        await asyncio.Event().wait()
                    yield event
        except asyncio.CancelledError:
            request["cancelled"] = True
            raise

    monkeypatch.setattr(OpenAiCompatibleProvider, "_stream_attempt", observe)
    output = Path(
        os.getenv(
            "AI_COMPACTION_LIVE_OUTPUT_DIR", Path(__file__).resolve().parents[2] / "artifacts" / "compaction-live"
        )
    )

    async def exercise():
        models = {model.id: model for model in await ModelCatalog(settings).models(None)}
        primary = settings.provider_model
        secondary = os.getenv("AI_COMPACTION_SWITCH_MODEL", "azure/gpt-6-luna")
        assert secondary != primary, "AI_COMPACTION_SWITCH_MODEL must select a different model"
        for model in (primary, secondary):
            assert model in models, f"Live compaction model is unavailable: {model}"
            assert models[model].context_tokens is not None, (
                f"Live compaction requires a reported context limit for {model}. "
                "Select models with context metadata through AI_PROVIDER_MODEL and AI_COMPACTION_SWITCH_MODEL."
            )
        return await asyncio.gather(
            *(
                run_live_case(name, settings, controls, output)
                for name in ("threshold", "repeated", "model-switch", "cancellation")
            )
        )

    reports = asyncio.run(exercise())
    summaries = [
        {key: value for key, value in report.items() if key not in {"requests", "events", "sandboxes"}}
        for report in reports
    ]
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    assert all(report["passed"] for report in reports), f"Live compaction failed. See {output}"
