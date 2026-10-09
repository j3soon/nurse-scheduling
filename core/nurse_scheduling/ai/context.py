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

import json
from collections.abc import Sequence

from .config import DEFAULT_MAX_HISTORY_CHARS, AiSettings
from .optimizer import WORKSPACE_OPTIMIZER_RESULT
from .provider import ChatMessage, TokenUsage, ToolCapableChatProvider
from .schedule_context import describe_schedule
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
    kept: list[ChatMessage] = []
    remaining = max_chars
    for message in reversed(history):
        remaining -= len(json.dumps(message, ensure_ascii=False))
        if remaining < 0:
            break
        kept.append(message)
    kept.reverse()
    return kept


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
    "turn were discarded. This turn starts with a fresh workspace containing the current schedule."
)
PROPOSAL_INVALID_HISTORY = (
    f"{APP_EVENT_PREFIX} The previous schedule proposal failed trusted validation when the user approved it, so it was "
    "discarded. All schedule changes made during that agent turn were dropped. This turn starts with a fresh "
    "workspace containing the current schedule."
)
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
    # Trimmed history or a failed turn can hide an upload event, so list only the files the request cannot show.
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
    settings: AiSettings,
    last_call: TokenUsage | None = None,
    provider: ToolCapableChatProvider | None = None,
) -> dict[str, int]:
    """Report retained history size and the latest request's tokens with the provider's context limit.

    The latest provider call holds the whole conversation that the model saw, so its prompt and
    completion tokens show how full the context window is. A sum over a turn's calls would count
    the same prompt several times.
    """
    usage = {"used_chars": used_chars, "max_chars": settings.max_history_chars}
    if last_call is not None:
        usage["used_tokens"] = last_call.prompt_tokens + last_call.completion_tokens
        limit = getattr(provider, "context_tokens", None)
        if type(limit) is int and limit > 0:
            usage["max_tokens"] = limit
    return usage


def history_context_chars(history: list[ChatMessage], max_chars: int) -> int:
    """Measure the serialized conversation selected for the next turn's history budget."""
    return history_chars(recent_history(history, max_chars))


def build_provider_messages(
    history: list[ChatMessage],
    schedule_yaml: str,
    question: str,
    attachments: Sequence[SandboxAttachment] = (),
    *,
    system_prompt: str = SANDBOX_SYSTEM_PROMPT,
    pending_proposal: bool = False,
    optimizer_result_available: bool = False,
    max_history_chars: int = DEFAULT_MAX_HISTORY_CHARS,
    max_download_bytes: int = 50_000_000,
) -> list[ChatMessage]:
    """Build a provider prompt whose system message and history stay unchanged between requests.

    Providers reuse cached work only for an identical prefix. Request-specific state therefore goes
    into a final status message that history never keeps.
    """
    system_content = f"{system_prompt}\n\n{describe_schedule(schedule_yaml)}"
    system_content += f"\nDownload size limit: {max_download_bytes} bytes.\n"
    retained = recent_history(history, max_history_chars)
    status = status_message(
        retained,
        attachments,
        pending_proposal=pending_proposal,
        optimizer_result_available=optimizer_result_available,
    )
    return [
        ChatMessage(role="system", content=system_content),
        *retained,
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
    messages: Sequence[ChatMessage], history_count: int, history_offset: int, question_kind: str
) -> dict[str, object]:
    """Describe a provider request for the chat: its system message and the messages added since the last reply.

    History messages after the last assistant reply are app events. Each one carries its absolute history
    index, so the chat shows it once even when a failed turn is retried.
    """
    history = messages[1 : 1 + history_count]
    last_reply = max((index for index, message in enumerate(history) if message["role"] == "assistant"), default=-1)
    added: list[dict[str, object]] = [
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
