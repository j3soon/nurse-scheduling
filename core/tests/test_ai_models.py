"""Credential isolation and model reasoning selection checks."""

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
from dataclasses import replace

import httpx
import pytest
from fastapi import HTTPException

from nurse_scheduling.ai.models import ModelCatalog, ModelSelection
from nurse_scheduling.ai.provider import OpenAiCompatibleProvider

from . import test_ai_basic as basic
from .test_ai_history import recorded_history

__all__ = ["recorded_history"]


def gateway(monkeypatch, *, parameters=None, options=None, metadata_status=200):
    calls = []
    client_type = httpx.AsyncClient

    def respond(request):
        key = request.headers.get("Authorization")
        if request.url.path.endswith("/models"):
            ids = ["fast", "deep"] if key != "Bearer key-b" else ["fast"]
            return httpx.Response(200, json={"data": [{"id": name} for name in ids]})
        if request.url.path.endswith("/model/info"):
            if metadata_status != 200:
                return httpx.Response(metadata_status)
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "model_name": "deep",
                            "litellm_params": {
                                "api_key": "must-not-leak",
                                **({"reasoning_effort": "high"} if parameters is None else parameters),
                            },
                            "model_info": {
                                "max_input_tokens": 32000,
                                "chat_reasoning_options": options
                                if options is not None
                                else [
                                    {"id": "off", "label": "Off", "parameters": {"thinking": {"type": "disabled"}}},
                                    {"id": "high", "label": "High", "parameters": {"reasoning_effort": "high"}},
                                ],
                            },
                        }
                    ]
                },
            )
        payload = json.loads(request.content)
        calls.append((key, payload))
        events = [
            {"choices": [{"delta": {"content": "Answer"}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        ]
        return httpx.Response(
            200, text="".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        )

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client_type(**{**kwargs, "transport": httpx.MockTransport(respond)})
    )
    return calls


def settings():
    return basic.make_settings(
        auth_tokens=basic.AI_AUTH_TOKENS,
        provider_profiles_json=json.dumps(
            {
                "institution-a": {"api_key": "key-a", "default_model": "fast"},
                "person_b": {"api_key": "key-b", "default_model": "fast"},
            }
        ),
    )


def test_models_are_authenticated_filtered_and_do_not_expose_credentials(monkeypatch):
    gateway(monkeypatch)
    app = basic.create_test_app(settings=settings(), provider=None)
    with basic.AuthenticatedTestClient(app) as client:
        assert client.get("/models", headers={"Authorization": "Bearer wrong"}).status_code == 401
        first = client.get("/models", headers={"Authorization": "Bearer institution-a-ai-token"})
        second = client.get("/models", headers={"Authorization": "Bearer person-b-ai-token"})
        assert [item["id"] for item in first.json()["models"]] == ["fast", "deep"]
        assert [item["id"] for item in second.json()["models"]] == ["fast"]
        assert first.json()["models"][1]["reasoning_options"] == [
            {"id": "off", "label": "Off"},
            {"id": "high", "label": "High"},
        ]
        assert first.json()["models"][1]["default_reasoning"] == "high"
        assert first.json()["models"][0]["default_reasoning"] == "default"
        assert "api_key" not in first.text and "must-not-leak" not in first.text


def test_turns_freeze_reasoning_switch_model_and_replay_without_calls(monkeypatch):
    calls = gateway(monkeypatch)
    app = basic.create_test_app(settings=settings(), provider=None)
    headers = {"Authorization": "Bearer institution-a-ai-token"}
    with basic.AuthenticatedTestClient(app, headers=headers) as client:
        session = basic.create_session(client)
        path = f"/sessions/{session}/messages"
        assert (
            client.get(f"/sessions/{session}", headers={"Authorization": "Bearer person-b-ai-token"}).status_code == 404
        )
        request = {"message": "Help", "message_id": "one", "selection": {"model": "deep", "reasoning": "high"}}
        first = client.post(path, json=request)
        assert first.status_code == 200
        assert "event: model_selection" in first.text
        assert client.post(path, json={**request, "selection": {"model": "unknown"}}).status_code == 202
        assert client.post(path, json={"message": "Next", "selection": {"model": "fast"}}).status_code == 200
        assert (
            client.post(path, json={"message": "Bad", "selection": {"model": "fast", "reasoning": "high"}}).status_code
            == 422
        )
        client.portal.call(
            app.state.session_optimizer._on_completion, session, "Review", None, {"model": "deep", "reasoning": "off"}
        )
    assert len(calls) == 3
    assert calls[2][1]["model"] == "deep" and calls[2][1]["thinking"] == {"type": "disabled"}
    assert calls[0][0] == "Bearer key-a" and calls[0][1]["reasoning_effort"] == "high"
    assert "reasoning_effort" not in calls[1][1]
    assert calls[1][1]["model"] == "fast"
    session = app.state.session_store._sessions[session]
    assert session.recovery_state()["model_selection"] == {"model": "fast", "reasoning": "default"}
    assert "key-a" not in json.dumps(session.recovery_state())


def test_profiles_isolate_concurrent_requests_and_reject_other_keys_models(monkeypatch):
    calls = gateway(monkeypatch)
    catalog = ModelCatalog(settings())

    async def exercise():
        first, second = await asyncio.gather(
            catalog.resolve("institution-a", ModelSelection(model="deep", reasoning="off")),
            catalog.resolve("person_b", ModelSelection(model="fast")),
        )
        await asyncio.gather(*[consume(item[2]) for item in (first, second)])
        with pytest.raises(HTTPException, match="not available"):
            await catalog.resolve("person_b", ModelSelection(model="deep"))
        with pytest.raises(HTTPException, match="no provider profile"):
            await catalog.resolve("missing", None)

    async def consume(provider: OpenAiCompatibleProvider):
        return [event async for event in provider.stream_events([])]

    asyncio.run(exercise())
    assert calls[0][1]["thinking"] == {"type": "disabled"}
    assert calls[1][0] == "Bearer key-b" and "thinking" not in calls[1][1]


@pytest.mark.parametrize("duplicate_question, expected_status", [("Help", 202), ("Different", 409)])
def test_duplicate_message_during_model_discovery(monkeypatch, duplicate_question, expected_status):
    client_type = httpx.AsyncClient
    calls = gateway(monkeypatch)
    app = basic.create_test_app(settings=basic.make_settings(provider_model="fast"), provider=None)
    original_models = ModelCatalog.models

    async def exercise():
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed(catalog, credential_id):
            started.set()
            await release.wait()
            return await original_models(catalog, credential_id)

        monkeypatch.setattr(ModelCatalog, "models", delayed)
        async with (
            app.router.lifespan_context(app),
            client_type(
                transport=httpx.ASGITransport(app), base_url="http://testserver", headers=basic.AI_AUTH_HEADERS
            ) as client,
        ):
            created = await client.post("/sessions", json={"schedule_yaml": "description: test"})
            session_id = created.json()["id"]
            path = f"/sessions/{session_id}/messages"
            first = asyncio.create_task(client.post(path, json={"message": "Help", "message_id": "one"}))
            await asyncio.wait_for(started.wait(), timeout=1)
            duplicate = asyncio.create_task(
                client.post(path, json={"message": duplicate_question, "message_id": "one"})
            )
            await asyncio.sleep(0.02)
            release.set()
            responses = await asyncio.wait_for(asyncio.gather(first, duplicate), timeout=2)
            assert responses[0].status_code == 200
            assert responses[1].status_code == expected_status
            if expected_status == 202:
                run_id = basic.parse_sse(responses[0].text)[0][1]["run_id"]
                assert responses[1].json() == {"run_id": run_id}
            else:
                assert "different question" in responses[1].json()["detail"]

    asyncio.run(exercise())
    assert len(calls) == 1


def test_invalid_profile_does_not_include_secret_in_exception():
    value = basic.make_settings(provider_profiles_json='{"a":{"api_key":"private-secret","extra":true}}')
    with pytest.raises(ValueError) as error:
        ModelCatalog(value)
    assert "private-secret" not in str(error.value)


@pytest.mark.parametrize("status", [422, 503])
def test_optimizer_review_reports_model_discovery_failure(monkeypatch, status, recorded_history):
    calls = gateway(monkeypatch)
    app = basic.create_test_app(settings=replace(settings(), history_postgres_url="postgresql://unused"), provider=None)
    headers = {"Authorization": "Bearer institution-a-ai-token"}
    with basic.AuthenticatedTestClient(app, headers=headers) as client:
        session_id = basic.create_session(client)
        selection = {"model": "deep", "reasoning": "high"}
        assert (
            client.post(
                f"/sessions/{session_id}/messages", json={"message": "Help", "selection": selection}
            ).status_code
            == 200
        )
        cursor = app.state.session_event_stream.cursor(session_id)

        async def unavailable(*_args):
            raise HTTPException(status, "The selected model is temporarily unavailable.")

        with monkeypatch.context() as failed_discovery:
            failed_discovery.setattr(ModelCatalog, "resolve", unavailable)
            client.portal.call(app.state.session_optimizer._on_completion, session_id, "Review", None, selection)

        events = app.state.session_event_stream.events_after(session_id, cursor)
        assert events[0].type == "run_start"
        assert events[-1].type == "error"
        assert events[-1].data["message"] == "The selected model is temporarily unavailable."
        assert not app.state.runs.busy(session_id)
        assert not app.state.session_store.get(session_id).active
        assert recorded_history["starts"][-1]["model"] == "deep"
        assert recorded_history["finishes"][-1][1:3] == ("failed", "provider_error")
        # A later request can still review the retained optimizer result.
        assert client.post(f"/sessions/{session_id}/messages", json={"message": "Try again"}).status_code == 200
    assert len(calls) == 2


def test_stop_cancels_optimizer_review_during_model_discovery(monkeypatch):
    app = basic.create_test_app(settings=settings(), provider=None)
    headers = {"Authorization": "Bearer institution-a-ai-token"}
    with basic.AuthenticatedTestClient(app, headers=headers) as client:
        session_id = basic.create_session(client)

        async def exercise():
            started = asyncio.Event()

            async def delayed(*_args):
                started.set()
                await asyncio.Event().wait()

            monkeypatch.setattr(ModelCatalog, "resolve", delayed)
            review = asyncio.create_task(app.state.session_optimizer._on_completion(session_id, "Review", None))
            await asyncio.wait_for(started.wait(), timeout=1)
            assert app.state.runs.busy(session_id)
            app.state.runs.stop(session_id)
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(review, timeout=1)
            assert not app.state.runs.busy(session_id)
            assert not app.state.session_store.get(session_id).active
            assert app.state.session_event_stream.events_after(session_id)[-1].type == "stopped"

        client.portal.call(exercise)


@pytest.mark.parametrize("metadata_status", [200, 403, 404])
def test_missing_reasoning_choices_preserve_gateway_default(monkeypatch, metadata_status):
    calls = gateway(monkeypatch, options=[], metadata_status=metadata_status)
    catalog = ModelCatalog(settings())

    async def exercise():
        models = await catalog.models("institution-a")
        assert [item.id for item in models] == ["fast", "deep"]
        assert all(item.reasoning == () for item in models)
        with pytest.raises(HTTPException, match="not supported"):
            await catalog.resolve("institution-a", ModelSelection(model="deep", reasoning="high"))
        selection, _, provider = await catalog.resolve("institution-a", ModelSelection(model="deep"))
        assert selection.reasoning == "default"
        return [item async for item in provider.stream_events([])]

    asyncio.run(exercise())
    assert "reasoning_effort" not in calls[0][1]
    assert "chat_template_kwargs" not in calls[0][1]


@pytest.mark.parametrize(
    "parameters",
    [
        {"messages": []},
        {"api_key": "secret"},
        {"reasoning_effort": None},
        {"chat_template_kwargs": {"enable_thinking": "false"}},
        {"chat_template_kwargs": {"enable_thinking": True, "reasoning_effort": "unsupported"}},
        {"chat_template_kwargs": {"enable_thinking": True, "api_key": "secret"}},
        {"thinking": None},
        {"thinking": {"type": "disabled", "budget_tokens": 1024}},
    ],
)
def test_reasoning_metadata_cannot_override_other_request_fields(monkeypatch, parameters):
    gateway(monkeypatch, options=[{"id": "custom", "label": "Custom", "parameters": parameters}])
    with pytest.raises(HTTPException, match="metadata is invalid"):
        asyncio.run(ModelCatalog(settings()).models("institution-a"))


def test_omitted_reasoning_resolves_to_configured_default(monkeypatch):
    calls = gateway(monkeypatch)
    catalog = ModelCatalog(settings())

    async def exercise():
        selection, _, provider = await catalog.resolve("institution-a", ModelSelection(model="deep"))
        assert selection.reasoning == "high"
        return [event async for event in provider.stream_events([])]

    asyncio.run(exercise())
    assert calls[0][1]["reasoning_effort"] == "high"


@pytest.mark.parametrize("configured", [{}, {"reasoning_effort": "low"}])
def test_unknown_default_keeps_provider_default_without_guessing(monkeypatch, configured):
    gateway(monkeypatch, parameters=configured)
    model = asyncio.run(ModelCatalog(settings()).models("institution-a"))[1].public()
    assert model["default_reasoning"] == "default"
    assert model["reasoning_options"][0] == {"id": "default", "label": "Provider default"}


def test_nested_qwen_default_and_explicit_choice_reach_provider(monkeypatch):
    options = [
        {"id": "none", "label": "None", "parameters": {"chat_template_kwargs": {"enable_thinking": False}}},
        *[
            {
                "id": effort,
                "label": effort,
                "parameters": {"chat_template_kwargs": {"enable_thinking": True, "reasoning_effort": effort}},
            }
            for effort in ("low", "xhigh")
        ],
    ]
    calls = gateway(
        monkeypatch,
        parameters={
            "chat_template_kwargs": {"enable_thinking": True, "reasoning_effort": "xhigh", "other_template_setting": 1}
        },
        options=options,
    )
    catalog = ModelCatalog(settings())

    async def exercise():
        model = (await catalog.models("institution-a"))[1].public()
        assert model["default_reasoning"] == "xhigh"
        assert [option["id"] for option in model["reasoning_options"]] == ["none", "low", "xhigh"]
        for reasoning in ("default", "low", "none"):
            selection, _, provider = await catalog.resolve(
                "institution-a", ModelSelection(model="deep", reasoning=reasoning)
            )
            assert selection.reasoning == ("xhigh" if reasoning == "default" else reasoning)
            _ = [event async for event in provider.stream_events([])]

    asyncio.run(exercise())
    assert [call[1]["chat_template_kwargs"] for call in calls] == [
        {"enable_thinking": True, "reasoning_effort": "xhigh"},
        {"enable_thinking": True, "reasoning_effort": "low"},
        {"enable_thinking": False},
    ]
