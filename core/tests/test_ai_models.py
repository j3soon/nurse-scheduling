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

import httpx
import pytest
from fastapi import HTTPException

from nurse_scheduling.ai.models import ModelCatalog, ModelSelection
from nurse_scheduling.ai.provider import OpenAiCompatibleProvider

from . import test_ai_basic as basic


def gateway(monkeypatch):
    calls = []
    client_type = httpx.AsyncClient

    def respond(request):
        key = request.headers.get("Authorization")
        if request.url.path.endswith("/models"):
            ids = ["fast", "deep"] if key != "Bearer key-b" else ["fast"]
            return httpx.Response(200, json={"data": [{"id": name} for name in ids]})
        if request.url.path.endswith("/model/info"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "model_name": "deep",
                            "litellm_params": {"api_key": "must-not-leak"},
                            "model_info": {
                                "max_input_tokens": 32000,
                                "chat_reasoning_options": [
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
            {"id": "default", "label": "Default"},
            {"id": "off", "label": "Off"},
            {"id": "high", "label": "High"},
        ]
        assert "api_key" not in first.text and "must-not-leak" not in first.text


def test_turns_freeze_reasoning_switch_model_and_replay_without_calls(monkeypatch):
    calls = gateway(monkeypatch)
    app = basic.create_test_app(settings=settings(), provider=None)
    headers = {"Authorization": "Bearer institution-a-ai-token"}
    with basic.AuthenticatedTestClient(app, headers=headers) as client:
        session = basic.create_session(client)
        path = f"/sessions/{session}/messages"
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


def test_invalid_profile_does_not_include_secret_in_exception():
    value = basic.make_settings(provider_profiles_json='{"a":{"api_key":"private-secret","extra":true}}')
    with pytest.raises(ValueError) as error:
        ModelCatalog(value)
    assert "private-secret" not in str(error.value)
