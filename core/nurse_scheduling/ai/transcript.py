"""Typed session transcript entries, projected separately into model context."""

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
from typing import Literal

StopReason = Literal["stop", "aborted", "error"]
ProposalDecision = Literal["approved", "rejected", "invalid"]


@dataclass(frozen=True)
class UserEntry:
    """A question, steering message, or background prompt that started model work."""

    text: str


@dataclass(frozen=True)
class AssistantEntry:
    """One answer segment. Only a `stop` segment is replayed as written in model context."""

    text: str
    stop_reason: StopReason = "stop"


@dataclass(frozen=True)
class ProposalDecisionEntry:
    """The user's decision on a pending schedule proposal."""

    decision: ProposalDecision


SessionEntry = UserEntry | AssistantEntry | ProposalDecisionEntry


def entry_text(entry: SessionEntry) -> str:
    """Return the text an entry retains, which bounds its share of session memory."""
    return "" if isinstance(entry, ProposalDecisionEntry) else entry.text


def entry_record(entry: SessionEntry) -> dict[str, str]:
    """Serialize one entry for the chat history log."""
    if isinstance(entry, UserEntry):
        return {"role": "user", "text": entry.text}
    if isinstance(entry, AssistantEntry):
        return {"role": "assistant", "text": entry.text, "stop_reason": entry.stop_reason}
    return {"role": "proposal_decision", "decision": entry.decision}
