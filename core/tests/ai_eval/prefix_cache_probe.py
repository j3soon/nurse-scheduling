"""Probe cache reporting for the app's stable prompt and tool prefix."""

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

import argparse
import asyncio
import hashlib
import json
import statistics
import time
from pathlib import Path
from uuid import uuid4

import httpx

from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.optimizer_tool import optimizer_tool_definition
from nurse_scheduling.ai.sandbox_tools import SandboxPiTools
from nurse_scheduling.ai.workspace import SANDBOX_SYSTEM_PROMPT


def _tools(settings: AiSettings) -> list[dict]:
    return [
        *SandboxPiTools(None, settings.sandbox_command_timeout_seconds).definitions,
        optimizer_tool_definition(settings.optimizer_default_timeout_seconds),
    ]


async def _request(client, settings, tools, prefix, question, *, max_tokens=1, cache_salt=None) -> dict:
    payload = {
        "model": settings.provider_model,
        "messages": [{"role": "system", "content": prefix}, {"role": "user", "content": question}],
        "tools": tools,
        "tool_choice": "auto",
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    if cache_salt is not None:
        payload["cache_salt"] = cache_salt
    started = time.perf_counter()
    first_token = None
    usage = None
    async with client.stream("POST", f"{settings.provider_base_url}/chat/completions", json=payload) as response:
        if not response.is_success:
            raise RuntimeError(f"Cache probe returned HTTP {response.status_code}.")
        async for line in response.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json.loads(line[6:])
            for choice in chunk.get("choices", []):
                delta = choice.get("delta", {})
                if first_token is None and any(
                    delta.get(key) for key in ("content", "reasoning_content", "reasoning", "tool_calls")
                ):
                    first_token = time.perf_counter() - started
            if chunk.get("usage") is not None:
                usage = chunk["usage"]
    return {"first_token_seconds": first_token, "seconds": time.perf_counter() - started, "usage": usage}


async def probe(settings: AiSettings, repeats: int, *, append_system_text="", transport=None) -> dict:
    """Repeat a stable prefix with changing questions and unique-prefix controls."""
    tools = _tools(settings)
    system_prompt = SANDBOX_SYSTEM_PROMPT + ("\n\n" + append_system_text if append_system_text else "")
    rows = []
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {settings.provider_api_key}"},
        timeout=settings.provider_timeout_seconds,
        transport=transport,
    ) as client:
        for index in range(repeats):
            for arm in ("shared-prefix", "unique-prefix"):
                prefix = system_prompt
                if arm == "unique-prefix":
                    prefix = f"Cache probe {uuid4()}.\n{prefix}"
                row = await _request(client, settings, tools, prefix, f"Reply with OK. Probe {index + 1}.")
                rows.append({"arm": arm, "repetition": index + 1, **row})
    warmed = [row for row in rows if row["arm"] == "shared-prefix" and row["repetition"] > 1]
    cached = [((row["usage"] or {}).get("prompt_tokens_details") or {}).get("cached_tokens") for row in warmed]
    hits = any(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in cached)
    reported = all(isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in cached)
    timing = {}
    for arm in ("shared-prefix", "unique-prefix"):
        values = [
            row["first_token_seconds"] for row in rows if row["arm"] == arm and row["first_token_seconds"] is not None
        ]
        timing[arm] = {
            "samples": len(values),
            "mean": statistics.mean(values) if values else None,
            "std": statistics.stdev(values) if len(values) > 1 else None,
        }
    return {
        "model": settings.provider_model,
        "cache_status": "confirmed" if hits else "no-reported-hits" if reported else "unknown",
        "note": "Positive cached_tokens confirms reuse for this prefix. Zero hits does not imply caching is disabled. Timing is descriptive, not proof. The first shared-prefix request is excluded from the hit check.",
        "prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "tools_sha256": hashlib.sha256(json.dumps(tools, sort_keys=True).encode()).hexdigest(),
        "timing": timing,
        "requests": rows,
    }


def _cached(row):
    value = ((row["usage"] or {}).get("prompt_tokens_details") or {}).get("cached_tokens")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


async def benchmark(settings: AiSettings, repeats: int, *, append_system_text="", transport=None) -> dict:
    """Measure reuse versus forced misses with identical prompt tokens and output limits."""
    from .comparison import _distribution, comparison_statistics

    tools = _tools(settings)
    prefix = SANDBOX_SYSTEM_PROMPT + ("\n\n" + append_system_text if append_system_text else "")
    salt = str(uuid4())
    rows = []
    started = time.perf_counter()
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {settings.provider_api_key}"},
        timeout=settings.provider_timeout_seconds,
        transport=transport,
    ) as client:
        warmup = await _request(
            client,
            settings,
            tools,
            prefix,
            "Explain how to inspect a roster workbook.",
            max_tokens=128,
            cache_salt=salt,
        )
        for repetition in range(1, repeats + 1):
            question = f"Explain how to inspect a roster workbook. Trial {repetition}."
            for arm in ("cold", "warm") if repetition % 2 else ("warm", "cold"):
                row = await _request(
                    client,
                    settings,
                    tools,
                    prefix,
                    question,
                    max_tokens=128,
                    cache_salt=salt if arm == "warm" else str(uuid4()),
                )
                rows.append({"arm": arm, "repetition": repetition, **row})
    paired = []
    for repetition in range(1, repeats + 1):
        pair = [
            next(row for row in rows if row["arm"] == arm and row["repetition"] == repetition)
            for arm in ("cold", "warm")
        ]
        if all(row["usage"] for row in pair) and all(
            pair[0]["usage"].get(key) == pair[1]["usage"].get(key) and pair[0]["usage"].get(key) is not None
            for key in ("prompt_tokens", "completion_tokens")
        ):
            paired.append(pair)
    records = {arm: [] for arm in ("cold", "warm")}
    for cold, warm in paired:
        for row in (cold, warm):
            usage = row["usage"]
            records[row["arm"]].append(
                {
                    "case_id": "prefix-cache",
                    "repetition": row["repetition"],
                    "passed": True,
                    "seconds": row["seconds"],
                    "tools": [],
                    "turns": 1,
                    "token_usage": {
                        "available": True,
                        "complete": True,
                        "prompt_tokens": usage["prompt_tokens"],
                        "completion_tokens": usage["completion_tokens"],
                        "total_tokens": usage["total_tokens"],
                        "cached_prompt_tokens": _cached(row),
                        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                    },
                }
            )
    comparison = comparison_statistics(records["cold"], records["warm"])["cases"].get("prefix-cache")
    first_token_pairs = [
        (cold["first_token_seconds"], warm["first_token_seconds"])
        for cold, warm in paired
        if cold["first_token_seconds"] is not None and warm["first_token_seconds"] is not None
    ]
    timing = {
        "pairs": len(first_token_pairs),
        "cold": _distribution([a for a, b in first_token_pairs]),
        "warm": _distribution([b for a, b in first_token_pairs]),
        "delta": _distribution([b - a for a, b in first_token_pairs]),
    }
    cold = [row for row in rows if row["arm"] == "cold"]
    warm = [row for row in rows if row["arm"] == "warm"]
    return {
        "model": settings.provider_model,
        "scope": "Forced cache misses versus reuse on one server, not a server flag off/on comparison. Identical paired messages, alternating order, 128-token output limit, untimed warmup, sequential requests to avoid local contention.",
        "prompt_sha256": hashlib.sha256(prefix.encode()).hexdigest(),
        "tools_sha256": hashlib.sha256(json.dumps(tools, sort_keys=True).encode()).hexdigest(),
        "cold_controls_verified": all(_cached(row) == 0 for row in cold),
        "warm_hit_runs": sum(isinstance(_cached(row), int) and _cached(row) > 0 for row in warm),
        "pairs": len(paired),
        "unmatched_pairs": repeats - len(paired),
        "first_token_seconds": timing,
        "comparison": comparison,
        "wall_seconds": time.perf_counter() - started,
        "warmup": warmup,
        "requests": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, choices=range(2, 11), default=3)
    parser.add_argument("--output", type=Path, help="Optional raw evidence path under artifacts/.")
    parser.add_argument(
        "--append-system-file",
        type=Path,
        help="Append a reference to the probe prefix, without changing the app prompt.",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Compare vLLM cache salts with identical tokens and 128-token output limits.",
    )
    args = parser.parse_args()
    try:
        extra = args.append_system_file.read_text(encoding="utf-8") if args.append_system_file else ""
        result = asyncio.run(
            (benchmark if args.benchmark else probe)(AiSettings.from_env(), args.repeat, append_system_text=extra)
        )
    except (httpx.HTTPError, ValueError, RuntimeError, OSError):
        print("Cache probe failed. Check provider configuration and connectivity.")
        return 1
    body = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body, encoding="utf-8")
    print(body, end="")
    if args.benchmark:
        return 0 if result["cold_controls_verified"] and result["unmatched_pairs"] == 0 else 2
    return {"confirmed": 0, "no-reported-hits": 1, "unknown": 2}[result["cache_status"]]


if __name__ == "__main__":
    raise SystemExit(main())
