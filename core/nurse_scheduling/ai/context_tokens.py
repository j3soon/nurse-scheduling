"""Token estimates and response limits shared by provider requests and compaction."""

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

# This file is mostly AI generated.

import json
import math
from collections.abc import Sequence
from typing import Any


def estimate_tokens(message: dict[str, Any]) -> int:
    """Use Pi's characters/4 fallback, with a fixed allowance for tool images."""
    content = message.get("content")
    if isinstance(content, list):
        chars = sum(len(part.get("text", "")) if part.get("type") == "text" else 4800 for part in content)
    else:
        chars = len(content or "")
    chars += len(json.dumps(message.get("tool_calls", []), ensure_ascii=False))
    # Count opaque state conservatively when provider usage is unavailable.
    chars += sum(
        len(json.dumps(message[key], ensure_ascii=False))
        for key in (
            "reasoning_content",
            "reasoning",
            "reasoning_text",
            "reasoning_details",
            "thinking_blocks",
            "provider_specific_fields",
        )
        if key in message
    )
    return math.ceil(chars / 4) + 4


def estimate_context_tokens(messages: Sequence[dict[str, Any]], tools: Sequence[dict], identity=None) -> int:
    """Prefer the latest same-model usage plus estimates for messages after it."""
    estimate = sum(estimate_tokens(message) for message in messages) + math.ceil(len(json.dumps(tools)) / 4)
    trailing = 0
    for message in reversed(messages):
        usage = message.get("_usage")
        source = message.get("_provider")
        if usage and source == identity and usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0) > 0:
            return max(estimate, usage["prompt_tokens"] + usage["completion_tokens"] + trailing)
        # A summary invalidates usage from the history it replaced.
        if message.get("_compaction_summary"):
            break
        trailing += estimate_tokens(message)
    return estimate


def response_token_limit(
    used_tokens: int,
    *,
    context_tokens: int | None,
    output_tokens: int | None,
    requested_tokens: int | None,
) -> int | None:
    """Fit output inside model limits and leave Pi's context safety margin."""
    limits = [value for value in (output_tokens, requested_tokens) if type(value) is int and value > 0]
    if context_tokens is not None and context_tokens > 0:
        safety = 4096
        limits.append(max(1, context_tokens - used_tokens - safety))
    return min(limits) if limits else None
