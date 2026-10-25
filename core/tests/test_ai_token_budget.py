"""Checks for provider-enforced output and reasoning budgets."""

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

from nurse_scheduling.ai.agent_loop import agent_loop
from nurse_scheduling.ai.agent_types import AgentCompaction, AgentCompactionStart
from nurse_scheduling.ai.compaction import COMPACTION_MANIFEST, ContextCompactor
from nurse_scheduling.ai.context import summary_message
from nurse_scheduling.ai.context_tokens import estimate_context_tokens
from nurse_scheduling.ai.models import ModelCatalog, ModelSelection
from nurse_scheduling.ai.provider import ProviderContextOverflowError, ProviderError
from nurse_scheduling.ai.system_prompt import load_system_prompt_entries, load_system_prompt_sections

from .test_ai_basic import make_settings
from .test_ai_provider import _collect, _delta_chunk, _sse_body, _transport_provider


def wire_provider(monkeypatch, requests):
    def handle(request):
        requests.append(request)
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Summary complete"})))

    return _transport_provider(monkeypatch, handle)


def test_output_budget_uses_model_limits_and_keeps_session_binding(monkeypatch):
    requests = []
    original = wire_provider(monkeypatch, requests)
    original.output_tokens = 900
    bound = original.with_session_id("chat-id").with_output_limit(600)
    asyncio.run(_collect(bound.stream_events([{"role": "user", "content": "Hello"}])))
    assert json.loads(requests[0].content)["max_tokens"] == 600
    assert requests[0].headers["x-session-id"] == "chat-id"
    assert original._max_output_tokens is None


def test_budget_counts_tool_definitions_and_leaves_context_room(monkeypatch):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider.context_tokens = 16000
    messages = [{"role": "user", "content": "x" * 20000}]
    tools = [{"type": "function", "function": {"name": "read", "description": "x" * 8000}}]
    asyncio.run(_collect(provider.stream_events(messages, tools)))
    payload = json.loads(requests[0].content)
    assert payload["max_tokens"] + estimate_context_tokens(messages, tools) <= 16000 - 4096
    assert 1 < payload["max_tokens"] < 6000


@pytest.mark.parametrize("window", [6000, 8192, 32000])
def test_short_requests_leave_the_fixed_pi_context_margin(monkeypatch, window):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider.context_tokens = window
    messages = [{"role": "user", "content": "Hello"}]
    asyncio.run(_collect(provider.stream_events(messages)))
    payload = json.loads(requests[0].content)
    assert payload["max_tokens"] == window - estimate_context_tokens(messages, []) - 4096
    assert payload["max_tokens"] > 1


@pytest.mark.parametrize("window", [1024, 4096])
def test_small_windows_fail_when_the_fixed_margin_leaves_no_response_room(monkeypatch, window):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider.context_tokens = window
    with pytest.raises(ProviderContextOverflowError, match="no room for a response"):
        asyncio.run(_collect(provider.stream_events([{"role": "user", "content": "Hello"}])))
    assert requests == []


@pytest.mark.parametrize("window", [4096, 8192])
def test_compaction_preserves_context_when_the_pi_request_does_not_fit(monkeypatch, window):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider.context_tokens = window
    messages = [
        {"role": "system", "content": "Scheduling assistant"},
        {"role": "user", "content": "Earlier task " + "x" * 100000},
        {"role": "assistant", "content": "Recent work " + "y" * 100000},
        {"role": "user", "content": "Inspect P1"},
    ]
    before = json.dumps(messages)
    events = asyncio.run(_collect(ContextCompactor(provider).compact(messages, [], force=True)))
    assert not any(isinstance(event, AgentCompaction) for event in events)
    assert requests == []
    assert json.dumps(messages) == before


def test_actual_context_usage_limits_output_when_wire_estimate_is_smaller(monkeypatch):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider.context_tokens = 16000
    bound = provider.with_output_limit(None, context_used_tokens=7000)
    asyncio.run(_collect(bound.stream_events([{"role": "user", "content": "Hello"}])))
    assert json.loads(requests[0].content)["max_tokens"] == 4904


def test_numeric_reasoning_budget_leaves_answer_room_and_preserves_parameters(monkeypatch):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider._parameters = {"thinking": {"type": "enabled", "budget_tokens": 8192}}
    asyncio.run(_collect(provider.with_output_limit(6000).stream_events([])))
    payload = json.loads(requests[0].content)
    assert payload["max_tokens"] == 6000
    assert payload["thinking"] == {"type": "enabled", "budget_tokens": 4976}
    assert provider._parameters["thinking"]["budget_tokens"] == 8192


@pytest.mark.parametrize("remaining", [0, -100])
def test_exhausted_context_fails_before_sending_a_completion(monkeypatch, remaining):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider.context_tokens = 16000
    bound = provider.with_output_limit(None, context_used_tokens=16000 - 4096 - remaining)
    with pytest.raises(ProviderContextOverflowError, match="no room for a response"):
        asyncio.run(_collect(bound.stream_events([])))
    assert requests == []


@pytest.mark.parametrize("limit_source", ["max_tokens", "max_completion_tokens", "model"])
def test_small_reasoning_output_cap_does_not_start_compaction(monkeypatch, limit_source):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider.context_tokens = 32000
    provider._context_tokens_loaded = True
    provider._parameters = {"thinking": {"type": "enabled", "budget_tokens": 8192}}
    if limit_source == "model":
        provider.output_tokens = 1024
    else:
        provider._parameters[limit_source] = 1024
    events = []

    async def run():
        async for event in agent_loop(
            provider,
            [{"role": "user", "content": "Keep nights"}, {"role": "assistant", "content": "Understood"}],
            [],
        ):
            events.append(event)

    with pytest.raises(ProviderError, match="output token limit") as error:
        asyncio.run(run())
    assert type(error.value) is ProviderError
    assert not any(isinstance(event, AgentCompactionStart) for event in events)
    assert requests == []


def test_small_request_output_cap_is_not_context_overflow(monkeypatch):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider._parameters = {"thinking": {"type": "enabled", "budget_tokens": 8192}}
    with pytest.raises(ProviderError, match="output token limit") as error:
        asyncio.run(_collect(provider.with_output_limit(1024).stream_events([])))
    assert type(error.value) is ProviderError
    assert requests == []


@pytest.mark.parametrize("remaining", [1024, 2048])
def test_context_limited_reasoning_can_compact_or_keep_the_minimum_budget(monkeypatch, remaining):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider.context_tokens = 16000
    provider._parameters = {"thinking": {"type": "enabled", "budget_tokens": 8192}}
    bound = provider.with_output_limit(6000, context_used_tokens=16000 - 4096 - remaining)
    if remaining == 1024:
        with pytest.raises(ProviderContextOverflowError, match="reasoning and an answer"):
            asyncio.run(_collect(bound.stream_events([])))
        assert requests == []
    else:
        asyncio.run(_collect(bound.stream_events([])))
        payload = json.loads(requests[0].content)
        assert payload["max_tokens"] == 2048
        assert payload["thinking"]["budget_tokens"] == 1024


@pytest.mark.parametrize("initial_prompt,expected", [("context-compaction", 10000), ("compaction-turn-prefix", 8192)])
def test_summary_has_pi_history_and_turn_prefix_output_budgets(monkeypatch, initial_prompt, expected):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider.context_tokens = 16000
    provider.output_tokens = 10000
    compactor = ContextCompactor(provider)
    entries = load_system_prompt_entries(COMPACTION_MANIFEST)
    prompts = dict(zip((e["id"] for e in entries), load_system_prompt_sections(entries), strict=True))
    asyncio.run(
        _collect(
            compactor._summarize(
                [{"role": "user", "content": "Keep P1 nights"}], prompts, initial_prompt=initial_prompt
            )
        )
    )
    assert json.loads(requests[0].content)["max_tokens"] == expected
    assert provider._max_output_tokens is None


@pytest.mark.parametrize("previous_chars", [0, 14000])
def test_large_summary_input_is_not_silently_chunked(monkeypatch, previous_chars):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider.context_tokens = 16000
    messages = [
        {"role": "system", "content": "Scheduling assistant"},
        *([summary_message("s" * previous_chars)] if previous_chars else []),
        {"role": "user", "content": "Earlier task " + "x" * 100000},
        {"role": "assistant", "content": "Recent work " + "y" * 100000},
        {"role": "user", "content": "Inspect P1"},
    ]
    events = asyncio.run(_collect(ContextCompactor(provider).compact(messages, [], force=True)))
    assert not any(isinstance(event, AgentCompaction) for event in events)
    assert requests == []


@pytest.mark.parametrize(
    "supported,parameter",
    [(["max_completion_tokens"], "max_completion_tokens"), (["max_tokens", "max_completion_tokens"], "max_tokens")],
)
def test_gateway_metadata_drives_output_limit_and_parameter(monkeypatch, supported, parameter):
    requests = []
    client_type = httpx.AsyncClient

    def handle(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "test-model"}]})
        if request.url.path.endswith("/model/info"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "model_name": "test-model",
                            "model_info": {
                                "max_input_tokens": 32000,
                                "max_output_tokens": 2048,
                                "supported_openai_params": supported,
                            },
                        }
                    ]
                },
            )
        requests.append(request)
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Done"})))

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client_type(**{**kwargs, "transport": httpx.MockTransport(handle)})
    )

    async def run():
        _, _, provider = await ModelCatalog(make_settings()).resolve(None, ModelSelection(model="test-model"))
        assert provider.output_tokens == 2048
        await _collect(provider.stream_events([]))

    asyncio.run(run())
    payload = json.loads(requests[0].content)
    assert payload[parameter] == 2048
    assert ({"max_tokens", "max_completion_tokens"} - {parameter}).isdisjoint(payload)


def test_unknown_limits_refuse_generation(monkeypatch):
    requests = []
    provider = wire_provider(monkeypatch, requests)
    provider.context_tokens = None
    with pytest.raises(ProviderError, match="no valid context window"):
        asyncio.run(_collect(provider.stream_events([])))
    assert requests == []


@pytest.mark.parametrize("field", ["max_input_tokens", "max_model_len", "context_length", "max_tokens"])
def test_direct_discovery_keeps_input_room_when_output_can_fill_the_window(monkeypatch, field):
    requests = []

    def handle(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "test-model", field: 32000, "max_output_tokens": 32000}]})
        requests.append(request)
        return httpx.Response(200, text=_sse_body(_delta_chunk({"content": "Done"})))

    provider = _transport_provider(monkeypatch, handle)
    provider._include_usage = True
    provider.context_tokens = None
    provider._context_tokens_loaded = False
    messages = [{"role": "user", "content": "Inspect the current schedule."}]
    asyncio.run(_collect(provider.stream_events(messages)))
    assert provider.context_tokens == 32000
    assert json.loads(requests[0].content)["max_tokens"] == 32000 - 4096 - estimate_context_tokens(messages, [])
