"""Bounded model context assembled from session and workspace state."""

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
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .config import DEFAULT_MAX_HISTORY_CHARS
from .optimizer import WORKSPACE_OPTIMIZER_RESULT, OptimizerCompletion
from .provider import (
    ChatMessage,
    TokenUsage,
    assistant_tool_call_message,
    tool_result_image_message,
    tool_result_message,
)
from .schedule_context import describe_schedule
from .session_events import ContextUsageEvent
from .transcript import (
    AgentMessage,
    AppEventEntry,
    AssistantMessage,
    ProposalDecision,
    ProposalDecisionEntry,
    ToolCall,
    ToolResultMessage,
    UserMessage,
    starts_exchange,
)
from .workspace import SANDBOX_SYSTEM_PROMPT, SandboxAttachment, attachment_path

APP_EVENT_PREFIX = "[App event]"
STATUS_PREFIX = "[Current status]"
SCHEDULE_CHANGED_EVENT = (
    f"{APP_EVENT_PREFIX} The schedule changed in the app. /workspace/schedule.yaml contains the current version."
)
SCHEDULE_CHANGED_DISCARDED_EVENT = (
    f"{SCHEDULE_CHANGED_EVENT} The pending proposal was discarded because it was made for the previous schedule."
)
PROPOSAL_APPROVED_HISTORY = (
    f"{APP_EVENT_PREFIX} The user approved the previous schedule proposal. Its changes are now part of the current "
    "schedule."
)
PROPOSAL_REJECTED_HISTORY = (
    f"{APP_EVENT_PREFIX} The user rejected the previous schedule proposal. All schedule changes made during that agent "
    "run were discarded. This run starts with a fresh workspace containing the current schedule."
)
PROPOSAL_INVALID_HISTORY = (
    f"{APP_EVENT_PREFIX} The previous schedule proposal failed trusted validation when the user approved it, so it was "
    "discarded. All schedule changes made during that agent run were dropped. This run starts with a fresh "
    "workspace containing the current schedule."
)
PROPOSAL_DECISION_HISTORY: dict[ProposalDecision, str] = {
    "approved": PROPOSAL_APPROVED_HISTORY,
    "rejected": PROPOSAL_REJECTED_HISTORY,
    "invalid": PROPOSAL_INVALID_HISTORY,
}
UPLOAD_EVENT_PREFIX = f"{APP_EVENT_PREFIX} The user uploaded files."
REMOVAL_EVENT_PREFIX = f"{APP_EVENT_PREFIX} The user removed a file from the workspace:"
PENDING_PROPOSAL_STATUS = (
    "A validated proposal is pending. Its exact candidate and diff are available in the trusted workspace files that "
    "the instructions describe."
)
OPTIMIZER_RESULT_STATUS = "Optimization result:"
UNLISTED_UPLOADS_STATUS = "Uploaded files not listed in this conversation:"
# Short titles let the chat label each app-written message without parsing its text.
_APP_EVENT_TITLES = (
    (UPLOAD_EVENT_PREFIX, "Files Uploaded"),
    (REMOVAL_EVENT_PREFIX, "File Removed"),
    (SCHEDULE_CHANGED_DISCARDED_EVENT, "Schedule Changed, Proposal Discarded"),
    (SCHEDULE_CHANGED_EVENT, "Schedule Changed"),
    (PROPOSAL_APPROVED_HISTORY, "Proposal Approved"),
    (PROPOSAL_REJECTED_HISTORY, "Proposal Rejected"),
    (PROPOSAL_INVALID_HISTORY, "Proposal Invalid"),
)
_STATUS_TITLES = (
    (PENDING_PROPOSAL_STATUS, "Pending Proposal"),
    (OPTIMIZER_RESULT_STATUS, "Optimizer Result"),
    (UNLISTED_UPLOADS_STATUS, "Unlisted Uploads"),
)
ABORTED_RESPONSE_HISTORY = "[This response was interrupted before completion. Its workspace changes were discarded.]"


def optimizer_completion_message(result_data: dict[str, Any]) -> str:
    """Render the completion prompt shared by production and controlled evaluations."""
    if (result_data.get("result") or {}).get("score") is not None:
        result_data = {
            **result_data,
            "score_direction": "maximize",
            "score_comparison_scope": "Compare only scores from unchanged constraints and weights.",
        }
    result_path = WORKSPACE_OPTIMIZER_RESULT if result_data["download_available"] else "unavailable"
    return (
        f"Optimizer job finished. Result workbook: {result_path}.\n"
        f"Optimizer result JSON:\n{json.dumps(result_data, ensure_ascii=False)}"
    )


def optimizer_review_prompt(completion: OptimizerCompletion) -> str:
    """Describe a finished job for a new review run without embedding its workbook."""
    result_data: dict[str, Any] = {
        "job_id": completion.job_id,
        "state": completion.state,
        "source_sha256": completion.source_sha256,
        "result": completion.result,
        "error": completion.error,
        "download_available": completion.artifact is not None,
        "artifact_error": completion.artifact_error,
    }
    if completion.artifact is not None and completion.request_audit is not None:
        result_data["request_audit"] = completion.request_audit
    return optimizer_completion_message(result_data)


def history_chars(messages: Sequence[ChatMessage]) -> int:
    """Measure messages the same way the prompt history budget does."""
    return sum(len(json.dumps(message, ensure_ascii=False)) for message in messages)


def _file_entry(attachment: SandboxAttachment, index: int) -> dict[str, str | int]:
    return {
        "filename": attachment.filename,
        "path": attachment_path(attachment, index),
        "media_type": attachment.media_type,
        "bytes": len(attachment.data),
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
    pending_proposal: bool,
    optimizer_result_available: bool,
) -> str:
    """Describe request-specific state that would otherwise change the cached prompt prefix."""
    lines = []
    if pending_proposal:
        lines.append(PENDING_PROPOSAL_STATUS)
    if optimizer_result_available:
        lines.append(f"{OPTIMIZER_RESULT_STATUS} {WORKSPACE_OPTIMIZER_RESULT}.")
    # Trimmed history or a failed run can hide an upload event, so list only the files the request cannot show.
    sent = "\n".join(str(message["content"]) for message in history)
    unlisted = [
        entry
        for index, attachment in enumerate(attachments, start=1)
        if (entry := _file_entry(attachment, index))["path"] not in sent
    ]
    if unlisted:
        lines.append(f"{UNLISTED_UPLOADS_STATUS} {json.dumps(unlisted, ensure_ascii=False)}")
    return f"{STATUS_PREFIX}\n" + "\n".join(lines) if lines else ""


def context_usage(
    used_chars: int,
    max_chars: int,
    last_call: TokenUsage | None = None,
    max_tokens: int | None = None,
) -> ContextUsageEvent:
    """Report retained history size and the latest request's tokens with the provider's context limit.

    The latest provider call holds the whole conversation that the model saw, so its prompt and
    completion tokens show how full the context window is. A sum over a run's calls would count
    the same prompt several times.
    """
    usage: ContextUsageEvent = {"type": "context_usage", "used_chars": used_chars, "max_chars": max_chars}
    if last_call is not None:
        usage["used_tokens"] = last_call.prompt_tokens + last_call.completion_tokens
        if type(max_tokens) is int and max_tokens > 0:
            usage["max_tokens"] = max_tokens
    return usage


def retained_entries(entries: Sequence[AgentMessage]) -> list[AgentMessage]:
    """Keep what later model context may use from a run's ordered entries.

    Tool calls, tool results, and reasoning describe a sandbox that no longer
    exists, so later runs never see them. The chat history log keeps the full run.
    """
    return [
        AssistantMessage(entry.text, entry.stop_reason) if isinstance(entry, AssistantMessage) else entry
        for entry in entries
        if not isinstance(entry, ToolResultMessage)
    ]


def _projected_messages(transcript: Sequence[AgentMessage]) -> list[tuple[bool, ChatMessage]]:
    """Project entries into prior-run context, marking which messages are prompts."""
    projected: list[tuple[bool, ChatMessage]] = []
    answer: list[str] = []
    interrupted = False
    answering = False

    def close_answer() -> None:
        nonlocal answer, interrupted, answering
        if answering:
            # Pi's provider adapters also skip aborted and errored assistant messages.
            # We keep a note in their place because the interrupted run's sandbox is
            # gone, so its partial text may claim schedule changes that no longer
            # exist. A length-truncated answer finished its run and is replayed.
            content = ABORTED_RESPONSE_HISTORY if interrupted else "".join(answer)
            projected.append((False, ChatMessage(role="assistant", content=content)))
        answer, interrupted, answering = [], False, False

    for entry in transcript:
        if isinstance(entry, AssistantMessage):
            # The responses between two prompts form one answer, as the user saw it.
            answering = True
            answer.append(entry.text)
            interrupted = interrupted or entry.stop_reason in ("aborted", "error")
        elif isinstance(entry, UserMessage):
            close_answer()
            projected.append((starts_exchange(entry), ChatMessage(role="user", content=entry.text)))
        elif isinstance(entry, ProposalDecisionEntry):
            close_answer()
            projected.append((False, ChatMessage(role="user", content=PROPOSAL_DECISION_HISTORY[entry.decision])))
        elif isinstance(entry, AppEventEntry):
            close_answer()
            projected.append((starts_exchange(entry), ChatMessage(role="user", content=entry.text)))
    close_answer()
    return projected


def projected_history(transcript: Sequence[AgentMessage]) -> list[ChatMessage]:
    """Project the whole transcript into prior-run messages."""
    return [message for _prompt, message in _projected_messages(transcript)]


@dataclass(frozen=True)
class HistoryContext:
    """Selected prior-run messages and their serialized JSON character budget."""

    messages: list[ChatMessage]
    used_chars: int
    dropped_messages: int


def project_history(transcript: Sequence[AgentMessage], max_chars: int = DEFAULT_MAX_HISTORY_CHARS) -> HistoryContext:
    """Project the newest transcript messages that fit the prompt budget, oldest first.

    Retention bounds how much of a conversation the session holds, not how much a
    provider can accept. A long session would otherwise grow every later prompt past
    the model context window and fail the request outright.
    """
    projected = _projected_messages(transcript)
    kept: list[tuple[bool, ChatMessage, int]] = []
    remaining = max_chars
    for prompt, message in reversed(projected):
        size = len(json.dumps(message, ensure_ascii=False))
        remaining -= size
        if remaining < 0:
            break
        kept.append((prompt, message, size))
    # Start at a prompt or app event. An answer or proposal decision whose prompt did
    # not fit refers to an exchange the model can no longer see.
    while kept and not kept[-1][0]:
        kept.pop()
    return HistoryContext(
        messages=[message for _prompt, message, _size in reversed(kept)],
        used_chars=sum(size for _prompt, _message, size in kept),
        dropped_messages=len(projected) - len(kept),
    )


def prepare_provider_request(prefix: Sequence[ChatMessage], entries: Sequence[AgentMessage]) -> list[ChatMessage]:
    """Project the agent's in-run messages at the provider boundary."""
    request = list(prefix)
    pending_images: list[ChatMessage] = []

    def flush_images() -> None:
        request.extend(pending_images)
        pending_images.clear()

    for entry in entries:
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
                request.append(assistant_tool_call_message(calls, entry.text))
            else:
                request.append(ChatMessage(role="assistant", content=entry.text))
        elif isinstance(entry, UserMessage):
            request.append(ChatMessage(role="user", content=entry.text))
    flush_images()
    return request


def build_provider_messages(
    history: HistoryContext,
    schedule_yaml: str,
    question: str,
    attachments: Sequence[SandboxAttachment] = (),
    *,
    system_prompt: str = SANDBOX_SYSTEM_PROMPT,
    pending_proposal: bool = False,
    optimizer_result_available: bool = False,
    max_download_bytes: int = 50_000_000,
) -> list[ChatMessage]:
    """Build a provider prompt whose system message and history stay unchanged between requests.

    Providers reuse cached work only for an identical prefix. Request-specific state therefore goes
    into a final status message that history never keeps. Schedule data stays separate from instructions.
    """
    system_content = f"{system_prompt}\n\n{describe_schedule(schedule_yaml)}"
    system_content += f"\nDownload size limit: {max_download_bytes} bytes.\n"
    status = status_message(
        history.messages,
        attachments,
        pending_proposal=pending_proposal,
        optimizer_result_available=optimizer_result_available,
    )
    return [
        ChatMessage(role="system", content=system_content),
        *history.messages,
        ChatMessage(role="user", content=question),
        *([ChatMessage(role="user", content=status)] if status else []),
    ]


def message_title(kind: str, content: str) -> str | None:
    """Name the topic of an app event or status message for its chat label."""
    if kind == "app":
        return next((title for prefix, title in _APP_EVENT_TITLES if content.startswith(prefix)), None)
    if kind == "status":
        lines = content.split("\n")[1:]
        titles = [title for prefix, title in _STATUS_TITLES if any(line.startswith(prefix) for line in lines)]
        return ", ".join(titles) or None
    return None


def model_input(
    messages: Sequence[ChatMessage],
    history_count: int,
    history_offset: int,
    question_kind: Literal["question", "optimizer"],
) -> dict[str, Any]:
    """Describe a provider request for the chat: its system message and the messages added since the last reply.

    History messages after the last assistant reply are app events. Each one carries its absolute history
    index, so the chat shows it once even when a failed run is retried.
    """
    history = messages[1 : 1 + history_count]
    last_reply = max((index for index, message in enumerate(history) if message["role"] == "assistant"), default=-1)
    added: list[dict[str, Any]] = [
        {"kind": "app", "index": history_offset + index, "content": message["content"]}
        for index, message in enumerate(history)
        if index > last_reply
    ]
    added.append({"kind": question_kind, "content": messages[1 + history_count]["content"]})
    added.extend({"kind": "status", "content": message["content"]} for message in messages[2 + history_count :])
    for entry in added:
        if title := message_title(str(entry["kind"]), str(entry["content"])):
            entry["title"] = title
    return {"system": messages[0]["content"], "messages": added}
