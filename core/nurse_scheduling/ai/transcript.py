"""Typed conversation entries independent of provider messages."""

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
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

# Pi's stop reasons. `tool_use` ends a response that requested tools.
StopReason = Literal["stop", "length", "tool_use", "aborted", "error"]
STATUS_PREFIX = "[Current status]"


@dataclass(frozen=True)
class ProviderIdentity:
    """The endpoint, API, and model that own native replay metadata."""

    endpoint: str
    model: str
    api: str = "openai-completions"


@dataclass(frozen=True)
class ToolCall:
    """One complete tool call a model requested, independent of the provider protocol."""

    id: str
    name: str
    arguments: str
    native: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UserMessage:
    """A question, steering message, or background prompt, as Pi's user message."""

    text: str


@dataclass(frozen=True)
class AssistantMessage:
    """One model response, as Pi's assistant message.

    An interrupted run ends with an `aborted` or `error` entry holding any partial output.
    """

    text: str
    stop_reason: StopReason = "stop"
    reasoning: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    native_reasoning: dict[str, Any] = field(default_factory=dict)
    provider: ProviderIdentity | None = None
    usage: dict[str, int | None] | None = None
    context_omitted: bool = False


@dataclass(frozen=True)
class ToolResultImage:
    """One bounded image returned by a model-facing tool."""

    media_type: str
    data: bytes


@dataclass(frozen=True)
class ToolResultMessage:
    """The result returned to the model for one tool call, as Pi's tool result message."""

    tool_call_id: str
    tool_name: str
    text: str
    ok: bool
    image: ToolResultImage | None = None


@dataclass(frozen=True)
class AppEventEntry:
    """A trusted app event between runs, such as an upload or schedule change, specific to this service."""

    text: str


@dataclass(frozen=True)
class CompactionEntry:
    """A summary that replaces older model context while retaining a recent tail."""

    summary: str
    keep_messages: int
    tokens_before: int
    valid: bool = True
    read_files: tuple[str, ...] = ()
    modified_files: tuple[str, ...] = ()


AgentMessage = UserMessage | AssistantMessage | ToolResultMessage | AppEventEntry | CompactionEntry

# Earlier versions stored the user's approval of each schedule change. A stored decision
# restores as the app event the model received.
_LEGACY_DECISION_EVENTS = {
    "approved": "[App event] The user approved the previous schedule proposal. Its changes are now part of the current "
    "schedule.",
    "rejected": "[App event] The user rejected the previous schedule proposal. All schedule changes made during that "
    "agent turn were discarded. This turn starts with a fresh workspace containing the current schedule.",
    "invalid": "[App event] The previous schedule proposal failed trusted validation when the user approved it, so it "
    "was discarded. All schedule changes made during that agent turn were dropped. This turn starts with a fresh "
    "workspace containing the current schedule.",
}

ENTRY_TYPES = {
    UserMessage: "user",
    AssistantMessage: "assistant",
    ToolResultMessage: "tool_result",
    AppEventEntry: "app_event",
    CompactionEntry: "compaction",
}


def entry_record(entry: AgentMessage) -> tuple[str, dict[str, Any]]:
    """Store an entry's origin and fields without storing tool images."""
    payload = asdict(replace(entry, image=None) if isinstance(entry, ToolResultMessage) else entry)
    if isinstance(entry, ToolResultMessage):
        payload.pop("image")
    if isinstance(entry, AssistantMessage) and not entry.context_omitted:
        payload.pop("context_omitted")
    if isinstance(entry, CompactionEntry):
        for field in ("read_files", "modified_files"):
            if not payload[field]:
                payload.pop(field)
    return ENTRY_TYPES[type(entry)], payload


def entry_from_record(entry_type: str, payload: dict[str, Any]) -> AgentMessage:
    """Restore an entry without inferring its origin from user-controlled text."""
    if entry_type == "assistant":
        return AssistantMessage(
            payload["text"],
            payload["stop_reason"],
            payload.get("reasoning", ""),
            tuple(ToolCall(**call) for call in payload.get("tool_calls", ())),
            payload.get("native_reasoning", {}),
            ProviderIdentity(**payload["provider"]) if payload.get("provider") else None,
            payload.get("usage"),
            payload.get("context_omitted", False),
        )
    if entry_type == "proposal_decision":
        return AppEventEntry(_LEGACY_DECISION_EVENTS[payload["decision"]])
    if entry_type == "compaction":
        payload = {
            **payload,
            "read_files": tuple(payload.get("read_files", ())),
            "modified_files": tuple(payload.get("modified_files", ())),
        }
    types = {
        "user": UserMessage,
        "tool_result": ToolResultMessage,
        "app_event": AppEventEntry,
        "compaction": CompactionEntry,
    }
    return types[entry_type](**payload)


def starts_exchange(entry: AgentMessage) -> bool:
    """Whether model context may start at this entry without an earlier answer it refers to."""
    if isinstance(entry, AppEventEntry) and entry.text.startswith(STATUS_PREFIX):
        return False
    return isinstance(entry, UserMessage | AppEventEntry | CompactionEntry)


def entry_text(entry: AgentMessage) -> str:
    """Return the text an entry holds, which bounds its share of session memory."""
    if isinstance(entry, UserMessage | ToolResultMessage | AppEventEntry):
        return entry.text
    if isinstance(entry, CompactionEntry):
        return entry.summary
    if isinstance(entry, AssistantMessage):
        return (
            entry.text
            + entry.reasoning
            + "".join(call.arguments + json.dumps(call.native, ensure_ascii=False) for call in entry.tool_calls)
            + (json.dumps(entry.native_reasoning, ensure_ascii=False) if entry.native_reasoning else "")
        )
    return ""
