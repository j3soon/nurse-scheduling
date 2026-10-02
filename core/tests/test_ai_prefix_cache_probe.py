"""Verify that cache probes distinguish hits, misses, and absent telemetry."""

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

from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.sandbox_agent import SANDBOX_SYSTEM_PROMPT
from tests.ai_eval.prefix_cache_probe import benchmark, probe


@pytest.mark.parametrize(
    "details,status",
    [
        (None, "unknown"),
        ({"cached_tokens": 0}, "no-reported-hits"),
        ({"cached_tokens": 2048}, "confirmed"),
    ],
)
@pytest.mark.parametrize("extra", ["", "Additional scheduling reference."])
def test_probes_real_prefix_without_inventing_cache_hits(details, status, extra):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        usage = {"prompt_tokens": 2157, "completion_tokens": 1, "total_tokens": 2158}
        if details is not None:
            usage["prompt_tokens_details"] = details
        chunks = [
            {"choices": [{"delta": {"role": "assistant"}}]},
            {"choices": [{"delta": {"reasoning_content": "OK"}}]},
            {"choices": [], "usage": usage},
        ]
        return httpx.Response(
            200, text="".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n"
        )

    result = asyncio.run(
        probe(
            AiSettings("https://provider.invalid/v1", "secret", "model"),
            3,
            append_system_text=extra,
            transport=httpx.MockTransport(handler),
        )
    )

    assert result["cache_status"] == status
    assert len(result["requests"]) == 6
    prefix = SANDBOX_SYSTEM_PROMPT + ("\n\n" + extra if extra else "")
    assert all(requests[index]["messages"][0]["content"] == prefix for index in (0, 2, 4))
    assert len({requests[index]["messages"][0]["content"] for index in (1, 3, 5)}) == 3
    assert all(request["stream_options"] == {"include_usage": True} for request in requests)
    assert all(request["tools"] == requests[0]["tools"] for request in requests)
    assert result["timing"]["shared-prefix"]["samples"] == 3
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize("mismatched_output", [False, True])
def test_benchmark_pairs_identical_messages_with_verified_cold_controls(mismatched_output):
    requests = []
    seen = set()

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        warm = body["cache_salt"] in seen
        seen.add(body["cache_salt"])
        output = 64 if mismatched_output and warm else 128
        usage = {
            "prompt_tokens": 14000,
            "completion_tokens": output,
            "total_tokens": 14000 + output,
            "prompt_tokens_details": {"cached_tokens": 11200 if warm else 0},
        }
        chunks = [{"choices": [{"delta": {"content": "OK"}}]}, {"choices": [], "usage": usage}]
        return httpx.Response(200, text="".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks))

    result = asyncio.run(
        benchmark(
            AiSettings("https://provider.invalid/v1", "secret", "model"),
            10,
            append_system_text="A scheduling reference.",
            transport=httpx.MockTransport(handler),
        )
    )

    assert len(requests) == 21  # One untimed warmup and ten matched pairs.
    assert result["cold_controls_verified"]
    assert result["warm_hit_runs"] == 10
    assert result["pairs"] == (0 if mismatched_output else 10)
    assert result["unmatched_pairs"] == (10 if mismatched_output else 0)
    for index in range(1, 21, 2):
        assert requests[index]["messages"] == requests[index + 1]["messages"]
        assert requests[index]["cache_salt"] != requests[index + 1]["cache_salt"]
        assert requests[index]["max_tokens"] == requests[index + 1]["max_tokens"] == 128
    assert [row["arm"] for row in result["requests"][:4]] == ["cold", "warm", "warm", "cold"]
    assert "secret" not in json.dumps(result)
