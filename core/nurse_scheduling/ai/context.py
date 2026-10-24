"""Existing model context and application event presentation."""

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

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import DEFAULT_MAX_HISTORY_CHARS, AiSettings
from .optimizer import WORKSPACE_OPTIMIZER_RESULT
from .provider import (
    ChatMessage,
    TokenUsage,
    ToolCapableChatProvider,
    assistant_tool_call_message,
    tool_result_image_message,
    tool_result_message,
)
from .schedule_context import describe_schedule
from .transcript import (
    STATUS_PREFIX,
    AgentMessage,
    AppEventEntry,
    AssistantMessage,
    CompactionEntry,
    ProviderIdentity,
    ToolCall,
    ToolResultMessage,
    UserMessage,
    starts_exchange,
)
from .workspace import SANDBOX_SYSTEM_PROMPT, SandboxAttachment, attachment_path

CANDIDATE_VALIDATION_ERROR = (
    "The candidate schedule failed trusted validation. All schedule changes made during this agent turn were "
    "discarded. The current schedule was not changed."
)
PROVIDER_ERROR = "The AI provider failed. Please try again."
SANDBOX_COMMAND_TIMEOUT_ERROR = (
    "An AI shell command timed out. The temporary workspace was discarded. Please try again."
)
SANDBOX_TURN_TIMEOUT_ERROR = "The AI response timed out. Please try again."
STALE_TURN_ERROR = "The schedule changed while this response was generated, so the response was discarded."


def recent_history(history: list[ChatMessage], max_chars: int) -> list[ChatMessage]:
    """Keep the newest retained messages that fit the prompt budget, oldest first.

    Retention bounds how much of a conversation the session holds, not how much a
    provider can accept. A long session would otherwise grow every later prompt past
    the model context window and fail the request outright.
    """
    return project_history(entries_from_legacy_history(history), max_chars).messages


APP_EVENT_PREFIX = "[App event]"
TIMEZONE_STATUS = "Workspace timezone: "
INTERRUPTED_TOOL_RESULT = "No result provided. The tool exchange was interrupted."
SCHEDULE_CHANGED_EVENT = (
    f"{APP_EVENT_PREFIX} The schedule changed in the app. /workspace/schedule.yaml contains the current version."
)
UPLOAD_EVENT_PREFIX = f"{APP_EVENT_PREFIX} The user uploaded files."
REMOVAL_EVENT_PREFIX = f"{APP_EVENT_PREFIX} The user removed a file from the workspace:"
OPTIMIZER_RESULT_STATUS = "Optimization result:"
UNLISTED_UPLOADS_STATUS = "Uploaded files not listed in this conversation:"
# Short titles let the chat label each app-written message without parsing its text.
_APP_EVENT_TITLES = (
    (UPLOAD_EVENT_PREFIX, "Files Uploaded"),
    (REMOVAL_EVENT_PREFIX, "File Removed"),
    (SCHEDULE_CHANGED_EVENT, "Schedule Changed"),
)
_STATUS_TITLES = (
    (TIMEZONE_STATUS, "Workspace Timezone"),
    (OPTIMIZER_RESULT_STATUS, "Optimizer Result"),
    (UNLISTED_UPLOADS_STATUS, "Unlisted Uploads"),
)


def history_chars(messages: Sequence[ChatMessage]) -> int:
    """Measure messages the same way the prompt history budget does."""
    return sum(len(json.dumps(message, ensure_ascii=False)) for message in messages)


def _file_entry(attachment: SandboxAttachment, index: int) -> dict[str, str | int]:
    return {
        "filename": attachment.filename,
        "path": attachment_path(attachment, index),
        "media_type": attachment.media_type,
        "bytes": attachment.byte_count,
    }


def upload_event(attachments: Sequence[SandboxAttachment], first_index: int = 1) -> str:
    """Describe uploaded files once in history, so later requests keep the same prefix."""
    files = [_file_entry(attachment, index) for index, attachment in enumerate(attachments, start=first_index)]
    return (
        f"{UPLOAD_EVENT_PREFIX} They stay in the workspace until the user removes them: "
        f"{json.dumps(files, ensure_ascii=False)}"
    )


def removal_event(attachment: SandboxAttachment, index: int) -> str:
    """Describe one removed file in history."""
    removed = {"filename": attachment.filename, "path": attachment_path(attachment, index)}
    return f"{REMOVAL_EVENT_PREFIX} {json.dumps(removed, ensure_ascii=False)}"


def status_message(
    history: Sequence[ChatMessage],
    attachments: Sequence[SandboxAttachment],
    *,
    optimizer_result_available: bool,
    frontend_timezone: str | None = None,
) -> str:
    """Describe request-specific state that would otherwise change the cached prompt prefix."""
    lines = []
    sent = "\n".join(str(message["content"]) for message in history)
    if frontend_timezone is not None:
        timezone = f"{TIMEZONE_STATUS}{frontend_timezone}."
        previous_timezone = next(
            (
                line
                for message in reversed(history)
                if isinstance(message.get("content"), str) and message["content"].startswith(STATUS_PREFIX)
                for line in reversed(message["content"].splitlines())
                if line.startswith(TIMEZONE_STATUS)
            ),
            None,
        )
        if timezone != previous_timezone:
            lines.append(timezone)
    if optimizer_result_available and WORKSPACE_OPTIMIZER_RESULT not in sent:
        lines.append(
            f"{OPTIMIZER_RESULT_STATUS} {WORKSPACE_OPTIMIZER_RESULT}. "
            "The user can already download this workbook with the chat's Download result button."
        )
    # Trimmed history or a failed turn can hide an upload event, so list only the files the request cannot show.
    unlisted = [
        entry
        for index, attachment in enumerate(attachments, start=1)
        if (entry := _file_entry(attachment, index))["path"] not in sent
    ]
    if unlisted:
        lines.append(f"{UNLISTED_UPLOADS_STATUS} {json.dumps(unlisted, ensure_ascii=False)}")
    return f"{STATUS_PREFIX}\n" + "\n".join(lines) if lines else ""


def validate_frontend_timezone(value: str) -> str:
    """Accept an IANA timezone that the server can use for the sandbox environment."""
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("frontend_timezone must be a known IANA timezone") from error
    return value


def context_usage(
    used_chars: int,
    settings: AiSettings,
    last_call: TokenUsage | None = None,
    provider: ToolCapableChatProvider | None = None,
    *,
    estimated_tokens: int | None = None,
) -> dict[str, int]:
    """Report retained history size and the latest request's tokens with the provider's context limit.

    The latest provider call holds the whole conversation that the model saw, so its prompt and
    completion tokens show how full the context window is. A sum over a turn's calls would count
    the same prompt several times.
    """
    usage = {"used_chars": used_chars, "max_chars": settings.max_history_chars}
    if last_call is not None or estimated_tokens is not None:
        usage["used_tokens"] = (
            estimated_tokens if estimated_tokens is not None else last_call.prompt_tokens + last_call.completion_tokens
        )
        limit = getattr(provider, "context_tokens", None)
        if type(limit) is int and limit > 0:
            usage["max_tokens"] = limit
    return usage


def history_context_chars(history: list[ChatMessage], max_chars: int) -> int:
    """Measure the serialized conversation selected for the next turn's history budget."""
    return history_chars(recent_history(history, max_chars))


def build_provider_messages(
    history: HistoryContext | list[ChatMessage],
    schedule_yaml: str,
    question: str,
    attachments: Sequence[SandboxAttachment] = (),
    *,
    system_prompt: str = SANDBOX_SYSTEM_PROMPT,
    optimizer_result_available: bool = False,
    max_history_chars: int = DEFAULT_MAX_HISTORY_CHARS,
    max_download_bytes: int = 50_000_000,
    frontend_timezone: str | None = None,
) -> list[ChatMessage]:
    """Build a provider prompt whose system message and history stay unchanged between requests.

    Providers reuse cached work only for an identical prefix. New workspace facts
    go into a status message that the agent retains in history.
    """
    system_content = f"{system_prompt}\n\n{describe_schedule(schedule_yaml)}"
    system_content += f"\nDownload size limit: {max_download_bytes} bytes.\n"
    selected = (
        history
        if isinstance(history, HistoryContext)
        else project_history(entries_from_legacy_history(history), max_history_chars)
    )
    retained = selected.messages
    status = status_message(
        retained,
        attachments,
        optimizer_result_available=optimizer_result_available,
        frontend_timezone=frontend_timezone,
    )
    return [
        ChatMessage(role="system", content=system_content),
        *retained,
        ChatMessage(role="user", content=question),
        *([ChatMessage(role="user", content=status, _current_status=True)] if status else []),
    ]


def message_title(kind: str, content: str) -> str | None:
    """Name the topic of an app event or status message for its chat label."""
    if kind == "app" and content.startswith(STATUS_PREFIX):
        return message_title("status", content)
    if kind == "app":
        return next((title for prefix, title in _APP_EVENT_TITLES if content.startswith(prefix)), None)
    if kind == "status":
        lines = content.split("\n")[1:]
        titles = [title for prefix, title in _STATUS_TITLES if any(line.startswith(prefix) for line in lines)]
        return ", ".join(titles) or None
    return None


QuestionKind = Literal["question", "optimizer"]


def model_input(
    messages: Sequence[ChatMessage],
    history_indices: Sequence[int],
    question_kind: QuestionKind,
    *,
    app_indices: set[int] | None = None,
    status_index: int | None = None,
) -> dict[str, object]:
    """Describe a provider request for the chat: its system message and the messages added since the last reply.

    History messages after the last assistant reply are app events. Each one carries its absolute
    transcript entry index, so compaction and retries cannot reuse its identity.
    """
    history_count = len(history_indices)
    history = messages[1 : 1 + history_count]
    last_reply = max((index for index, message in enumerate(history) if message["role"] == "assistant"), default=-1)
    added: list[dict[str, object]] = [
        {"kind": "app", "index": history_indices[index], "content": message["content"]}
        for index, message in enumerate(history)
        if index > last_reply
        and message["role"] == "user"
        and (app_indices is None or history_indices[index] in app_indices)
    ]
    added.append({"kind": question_kind, "content": messages[1 + history_count]["content"]})
    added.extend(
        {
            "kind": "status",
            "content": message["content"],
            **({"index": status_index} if status_index is not None else {}),
        }
        for message in messages[2 + history_count :]
    )
    for entry in added:
        if title := message_title(str(entry["kind"]), str(entry["content"])):
            entry["title"] = title
    return {"system": messages[0]["content"], "messages": added}


def prepare_provider_request(
    prefix: Sequence[ChatMessage],
    entries: Sequence[AgentMessage],
    *,
    provider: ProviderIdentity | None = None,
    _preserve_native: bool = False,
) -> list[ChatMessage]:
    """Project the agent's in-run messages at the provider boundary."""
    request = list(prefix)
    pending_images: list[ChatMessage] = []

    def flush_images() -> None:
        request.extend(pending_images)
        pending_images.clear()

    for entry in entries:
        if isinstance(entry, CompactionEntry):
            flush_images()
            if entry.valid:
                request = apply_compaction(request, entry)
            continue
        if isinstance(entry, ToolResultMessage):
            request.append(tool_result_message(entry.tool_call_id, entry.text))
            if entry.image is not None:
                pending_images.append(tool_result_image_message(entry.tool_call_id, entry.image))
            continue
        flush_images()
        if isinstance(entry, AssistantMessage):
            if entry.tool_calls:
                # A truncated response is an audit record of raw model output. The
                # provider sees placeholder arguments so it can safely reissue calls.
                calls = (
                    tuple(ToolCall(call.id, call.name, "{}") for call in entry.tool_calls)
                    if entry.stop_reason == "length"
                    else entry.tool_calls
                )
                message = assistant_tool_call_message(calls, entry.text)
            else:
                message = ChatMessage(role="assistant", content=entry.text)
            if entry.stop_reason in {"aborted", "error"}:
                continue
            if entry.provider is not None:
                message["_provider"] = asdict(entry.provider)
                if entry.stop_reason != "length":
                    message.update(entry.native_reasoning)
            if entry.usage is not None:
                message["_usage"] = entry.usage
            request.append(message)
        elif isinstance(entry, UserMessage | AppEventEntry):
            request.append(ChatMessage(role="user", content=entry.text))
    flush_images()
    return (
        _repair_tool_pairs(request)
        if _preserve_native
        else compatible_provider_messages(_repair_tool_pairs(request), provider)
    )


SUMMARY_PREFIX = "[Conversation summary]"


def summary_message(summary: str) -> ChatMessage:
    """Represent a compaction summary as conversation data."""
    return ChatMessage(role="user", content=f"{SUMMARY_PREFIX}\n{summary}", _compaction_summary=True)


def _recent_messages(projected: list[tuple[bool, ChatMessage]], count: int) -> list[tuple[bool, ChatMessage]]:
    if count <= 0:
        return []
    start = len(projected)
    while start > 0 and count > 0:
        start -= 1
        if not projected[start][1].get("_tool_image"):
            count -= 1
    tail = []
    for prompt, original in projected[start:]:
        message = dict(original)
        message.pop("_usage", None)
        tail.append((prompt, message))
    return tail


def apply_compaction(messages: Sequence[ChatMessage], entry: CompactionEntry) -> list[ChatMessage]:
    """Replace old context while preserving fixed instructions and the recent tail."""
    system, conversation = [], []
    for message in messages:
        if message["role"] == "system":
            system.append(message)
        else:
            conversation.append((False, message))
    tail = [message for _, message in _recent_messages(conversation, entry.keep_messages)]
    return [*system, summary_message(entry.summary), *tail]


def retained_entries(entries: Sequence[AgentMessage]) -> list[AgentMessage]:
    """Retain native reasoning and tool exchanges. Release transient image bytes."""
    return [replace(entry, image=None) if isinstance(entry, ToolResultMessage) else entry for entry in entries]


def compatible_provider_messages(
    messages: Sequence[ChatMessage], provider: ProviderIdentity | None
) -> list[ChatMessage]:
    """Replay opaque metadata only to its original API, endpoint, and model."""
    import hashlib
    import re

    result = []
    ids = {}
    for original in messages:
        message = dict(original)
        source = message.pop("_provider", None)
        message.pop("_usage", None)
        message.pop("_tool_image", None)
        message.pop("_current_status", None)
        message.pop("_compaction_summary", None)
        compatible = provider is not None and source == asdict(provider)
        if message["role"] == "assistant" and not compatible:
            for name in (
                "reasoning",
                "reasoning_content",
                "reasoning_text",
                "reasoning_details",
                "thinking_blocks",
                "provider_specific_fields",
            ):
                message.pop(name, None)
            if "tool_calls" in message:
                calls = []
                for call in message["tool_calls"]:
                    call_id = call["id"]
                    if provider is not None and source is not None:
                        normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", call_id)
                        if normalized != call_id or len(normalized) > 40:
                            normalized = normalized[:31] + "_" + hashlib.sha256(call_id.encode()).hexdigest()[:8]
                        ids[call_id] = normalized
                        call_id = normalized
                    calls.append({"id": call_id, "type": "function", "function": dict(call["function"])})
                message["tool_calls"] = calls
        if message["role"] == "tool":
            message["tool_call_id"] = ids.get(message["tool_call_id"], message["tool_call_id"])
        result.append(message)
    return result


def _repair_tool_pairs(messages: Sequence[ChatMessage]) -> list[ChatMessage]:
    """Complete interrupted tool batches before the next assistant or user message."""
    result = []
    pending = {}
    for message in messages:
        if message["role"] == "tool":
            if message["tool_call_id"] in pending:
                pending.pop(message["tool_call_id"])
                result.append(message)
            continue
        for call_id in pending:
            result.append(tool_result_message(call_id, INTERRUPTED_TOOL_RESULT))
        pending = {call["id"]: call for call in message.get("tool_calls", [])}
        result.append(message)
    result.extend(tool_result_message(call_id, INTERRUPTED_TOOL_RESULT) for call_id in pending)
    return result


def _projected_messages(
    transcript: Sequence[AgentMessage], *, with_sources: bool = False
) -> list[tuple[bool, ChatMessage]]:
    """Project complete exchanges, retaining each native response and tool result."""
    projected = []
    response = []
    response_start = 0

    def close_answer() -> None:
        if not response:
            return
        if all(
            isinstance(entry, AssistantMessage)
            and entry.stop_reason not in {"aborted", "error"}
            and not entry.tool_calls
            and not entry.native_reasoning
            and entry.usage is None
            for entry in response
        ):
            # Keep the historical text-only projection for legacy sessions.
            messages = [ChatMessage(role="assistant", content="".join(entry.text for entry in response))]
        else:
            messages = prepare_provider_request([], response, _preserve_native=True)
        if with_sources:
            for message in messages:
                message["_source_index"] = response_start
        projected.extend((False, message) for message in messages)
        response.clear()

    for index, entry in enumerate(transcript):
        if isinstance(entry, CompactionEntry):
            if entry.valid:
                close_answer()
                tail = _recent_messages(projected, entry.keep_messages)
                message = summary_message(entry.summary)
                if with_sources:
                    message["_source_index"] = index
                projected[:] = [(True, message), *tail]
        elif isinstance(entry, UserMessage | AppEventEntry):
            close_answer()
            message = ChatMessage(role="user", content=entry.text)
            if with_sources:
                message["_source_index"] = index
            projected.append((starts_exchange(entry), message))
        else:
            if not response:
                response_start = index
            response.append(entry)
    close_answer()
    return projected


def projected_history(transcript: Sequence[AgentMessage]) -> list[ChatMessage]:
    """Project the whole transcript into prior-run messages."""
    return [message for _prompt, message in _projected_messages(transcript)]


@dataclass(frozen=True)
class HistoryContext:
    """Selected prior-run messages, source entry indices, and serialized JSON character budget."""

    messages: list[ChatMessage]
    used_chars: int
    dropped_messages: int
    source_indices: list[int]


def project_history(transcript: Sequence[AgentMessage], max_chars: int = DEFAULT_MAX_HISTORY_CHARS) -> HistoryContext:
    """Project the newest transcript messages that fit the prompt budget, oldest first.

    Retention bounds how much of a conversation the session holds, not how much a
    provider can accept. A long session would otherwise grow every later prompt past
    the model context window and fail the request outright.
    """
    projected = _projected_messages(transcript, with_sources=True)
    kept: list[tuple[bool, ChatMessage, int, int]] = []
    remaining = max_chars
    for prompt, message in reversed(projected):
        source_index = message.pop("_source_index")
        size = len(json.dumps(message, ensure_ascii=False))
        remaining -= size
        if remaining < 0:
            break
        kept.append((prompt, message, size, source_index))
    # Start at a prompt or app event. An answer whose prompt did not fit refers to
    # an exchange the model can no longer see.
    while kept and not kept[-1][0]:
        kept.pop()
    return HistoryContext(
        messages=[message for _prompt, message, _size, _source in reversed(kept)],
        used_chars=sum(size for _prompt, _message, size, _source in kept),
        dropped_messages=len(projected) - len(kept),
        source_indices=[source for _prompt, _message, _size, source in reversed(kept)],
    )


ABORTED_RESPONSE_HISTORY = (
    "[App event] The response was interrupted. Its incomplete output is omitted from context. "
    "The run's temporary workspace was discarded. Earlier tool results describe that discarded workspace."
)


def entries_from_legacy_history(messages: Sequence[ChatMessage]) -> list[AgentMessage]:
    """Restore the existing persisted text view until typed persistence is introduced."""
    entries = []
    for message in messages:
        text = message.get("content") or ""
        if not isinstance(text, str):
            raise TypeError("Persisted chat history must contain text messages.")
        if message["role"] == "assistant":
            entries.append(AssistantMessage(text))
        elif text.startswith(APP_EVENT_PREFIX):
            entries.append(AppEventEntry(text))
        else:
            entries.append(UserMessage(text))
    return entries


def interrupted_entries(entries: Sequence[AgentMessage], reason) -> list[AgentMessage]:
    """Preserve completed exchanges and explain the discarded workspace separately."""
    result = []
    pending: dict[str, ToolCall] = {}
    for entry in entries:
        if isinstance(entry, ToolResultMessage):
            pending.pop(entry.tool_call_id, None)
        elif isinstance(entry, AssistantMessage | UserMessage | AppEventEntry):
            result.extend(
                ToolResultMessage(call.id, call.name, INTERRUPTED_TOOL_RESULT, False) for call in pending.values()
            )
            pending.clear()
            if isinstance(entry, AssistantMessage) and entry.stop_reason not in {"aborted", "error"}:
                pending.update((call.id, call) for call in entry.tool_calls)
        result.append(replace(entry, valid=False) if isinstance(entry, CompactionEntry) else entry)
    result.extend(ToolResultMessage(call.id, call.name, INTERRUPTED_TOOL_RESULT, False) for call in pending.values())
    last = next(
        (index for index in range(len(result) - 1, -1, -1) if not isinstance(result[index], CompactionEntry)), None
    )
    if last is not None and isinstance(result[last], AssistantMessage) and not result[last].tool_calls:
        result[last] = replace(result[last], stop_reason=reason)
    else:
        result.append(AssistantMessage("", reason))
    result.append(AppEventEntry(ABORTED_RESPONSE_HISTORY))
    return result


def compaction_safe_drop_end(transcript: Sequence[AgentMessage], end: int | None) -> int | None:
    """Retain a summary and the older messages it references as one retention unit."""
    if end is None:
        return None
    for index, entry in enumerate(transcript):
        if not isinstance(entry, CompactionEntry) or not entry.valid or entry.keep_messages <= 0:
            continue
        before = _projected_messages(transcript[:index], with_sources=True)
        tail = _recent_messages(before, entry.keep_messages)
        first = min((message["_source_index"] for _, message in tail), default=index)
        if first < end <= index:
            end = next(
                (
                    candidate
                    for candidate in range(index + 1, len(transcript))
                    if starts_exchange(transcript[candidate])
                ),
                None,
            )
            if end is None:
                return None
    return end


def drop_oldest_exchange(transcript: list[AgentMessage], keep_entries: int = 0) -> list[AgentMessage]:
    """Remove one prompt with its answers and decisions, while preserving the newest exchange."""
    end = next((index for index in range(1, len(transcript)) if starts_exchange(transcript[index])), None)
    end = compaction_safe_drop_end(transcript, end)
    if end is None or len(transcript) - end < keep_entries:
        return []
    removed = transcript[:end]
    del transcript[:end]
    return removed


def cap_transcript(transcript: list[AgentMessage], max_messages: int, max_chars: int, keep_entries: int = 0) -> int:
    """Trim whole exchanges while preserving the newest exchange and protected run.

    Past the prompt history budget, cut to half the budget. Cutting in batches
    keeps the prompt prefix unchanged for many turns so providers can reuse it.
    Per-request selection bounds an oversized newest exchange.
    """
    dropped = 0
    while len(projected_history(transcript)) > max(2, max_messages):
        removed = drop_oldest_exchange(transcript, keep_entries)
        if not removed:
            break
        dropped += len(projected_history(removed))
    if history_chars(projected_history(transcript)) > max_chars:
        while history_chars(projected_history(transcript)) > max_chars // 2:
            removed = drop_oldest_exchange(transcript, keep_entries)
            if not removed:
                break
            dropped += len(projected_history(removed))
    return dropped
