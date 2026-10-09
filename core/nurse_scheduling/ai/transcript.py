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

from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

# Pi's stop reasons. `tool_use` ends a response that requested tools.
StopReason = Literal["stop", "length", "tool_use", "aborted", "error"]
ProposalDecision = Literal["approved", "rejected", "invalid"]


@dataclass(frozen=True)
class ToolCall:
    """One complete tool call a model requested, independent of the provider protocol."""

    id: str
    name: str
    arguments: str


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
class ProposalDecisionEntry:
    """The user's decision on a pending schedule proposal, specific to this service."""

    decision: ProposalDecision


@dataclass(frozen=True)
class AppEventEntry:
    """A trusted app event between runs, such as an upload or schedule change, specific to this service."""

    text: str


AgentMessage = UserMessage | AssistantMessage | ToolResultMessage | ProposalDecisionEntry | AppEventEntry

ENTRY_TYPES = {
    UserMessage: "user",
    AssistantMessage: "assistant",
    ToolResultMessage: "tool_result",
    ProposalDecisionEntry: "proposal_decision",
    AppEventEntry: "app_event",
}


def entry_record(entry: AgentMessage) -> tuple[str, dict[str, Any]]:
    """Store an entry's origin and fields without storing tool images."""
    payload = asdict(replace(entry, image=None) if isinstance(entry, ToolResultMessage) else entry)
    if isinstance(entry, ToolResultMessage):
        payload.pop("image")
    return ENTRY_TYPES[type(entry)], payload


def entry_from_record(entry_type: str, payload: dict[str, Any]) -> AgentMessage:
    """Restore an entry without inferring its origin from user-controlled text."""
    if entry_type == "assistant":
        return AssistantMessage(
            payload["text"],
            payload["stop_reason"],
            payload.get("reasoning", ""),
            tuple(ToolCall(**call) for call in payload.get("tool_calls", ())),
        )
    types = {
        "user": UserMessage,
        "tool_result": ToolResultMessage,
        "proposal_decision": ProposalDecisionEntry,
        "app_event": AppEventEntry,
    }
    return types[entry_type](**payload)


def starts_exchange(entry: AgentMessage) -> bool:
    """Whether model context may start at this entry without an earlier answer it refers to."""
    return isinstance(entry, UserMessage | AppEventEntry)


def entry_text(entry: AgentMessage) -> str:
    """Return the text an entry holds, which bounds its share of session memory."""
    if isinstance(entry, UserMessage | ToolResultMessage | AppEventEntry):
        return entry.text
    if isinstance(entry, AssistantMessage):
        return entry.text + entry.reasoning + "".join(call.arguments for call in entry.tool_calls)
    return ""
