"""Provider-neutral agent messages, shaped like Pi's, that record each run."""

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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .provider import ToolResultImage

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
class ToolResultMessage:
    """The result returned to the model for one tool call, as Pi's tool result message."""

    tool_call_id: str
    tool_name: str
    text: str
    ok: bool
    image: "ToolResultImage | None" = None


@dataclass(frozen=True)
class ProposalDecisionEntry:
    """The user's decision on a pending schedule proposal, specific to this service."""

    decision: ProposalDecision


AgentMessage = UserMessage | AssistantMessage | ToolResultMessage | ProposalDecisionEntry


def entry_text(entry: AgentMessage) -> str:
    """Return the text an entry holds, which bounds its share of session memory."""
    if isinstance(entry, UserMessage | ToolResultMessage):
        return entry.text
    if isinstance(entry, AssistantMessage):
        return entry.text + entry.reasoning + "".join(call.arguments for call in entry.tool_calls)
    return ""
