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

from .config import DEFAULT_MAX_HISTORY_CHARS
from .optimizer import WORKSPACE_OPTIMIZER_RESULT
from .provider import ChatMessage
from .schedule_context import describe_schedule
from .transcript import AssistantEntry, ProposalDecision, SessionEntry, UserEntry
from .workspace import SANDBOX_SYSTEM_PROMPT, SandboxAttachment

PROPOSAL_APPROVED_HISTORY = (
    "The user approved the previous schedule proposal. Its changes are now part of the current canonical schedule."
)
PROPOSAL_REJECTED_HISTORY = (
    "The user rejected the previous schedule proposal. All schedule changes made during that agent turn were "
    "discarded. This turn starts with a fresh workspace containing the current canonical schedule."
)
PROPOSAL_INVALID_HISTORY = (
    "The previous schedule proposal failed trusted validation when the user approved it, so it was discarded. All "
    "schedule changes made during that agent turn were dropped. This turn starts with a fresh workspace containing "
    "the current canonical schedule."
)
PROPOSAL_DECISION_HISTORY: dict[ProposalDecision, str] = {
    "approved": PROPOSAL_APPROVED_HISTORY,
    "rejected": PROPOSAL_REJECTED_HISTORY,
    "invalid": PROPOSAL_INVALID_HISTORY,
}
ABORTED_RESPONSE_HISTORY = "[This response was interrupted before completion. Its workspace changes were discarded.]"


def context_message(entry: SessionEntry) -> ChatMessage:
    """Project one transcript entry into the provider conversation."""
    if isinstance(entry, UserEntry):
        return ChatMessage(role="user", content=entry.text)
    if isinstance(entry, AssistantEntry):
        # Pi's provider adapters also skip aborted and errored assistant messages. We
        # keep a note in their place because the interrupted run's sandbox is gone, so
        # its partial text may claim schedule changes that no longer exist. A
        # length-truncated answer finished its run and is replayed as written.
        if entry.stop_reason in ("stop", "length"):
            return ChatMessage(role="assistant", content=entry.text)
        return ChatMessage(role="assistant", content=ABORTED_RESPONSE_HISTORY)
    return ChatMessage(role="user", content=PROPOSAL_DECISION_HISTORY[entry.decision])


def recent_history(transcript: Sequence[SessionEntry], max_chars: int) -> list[ChatMessage]:
    """Project the newest transcript entries that fit the prompt budget, oldest first.

    Retention bounds how much of a conversation the session holds, not how much a
    provider can accept. A long session would otherwise grow every later prompt past
    the model context window and fail the request outright.
    """
    kept: list[ChatMessage] = []
    remaining = max_chars
    for entry in reversed(transcript):
        message = context_message(entry)
        remaining -= len(json.dumps(message, ensure_ascii=False))
        if remaining < 0:
            break
        kept.append(message)
    kept.reverse()
    return kept


def prepare_provider_request(conversation: Sequence[ChatMessage]) -> list[ChatMessage]:
    """Derive each in-run provider request from the run's conversation.

    Prior history is already bounded by `build_provider_messages`, and the run's own
    growth is bounded by tool budgets, so this sends the conversation unchanged. A
    later in-run policy belongs here. It must keep each assistant tool call with all
    of its tool results, and must return a new list rather than edit the record.
    """
    return list(conversation)


def build_provider_messages(
    transcript: Sequence[SessionEntry],
    schedule_yaml: str,
    question: str,
    attachments: Sequence[SandboxAttachment] = (),
    *,
    system_prompt: str = SANDBOX_SYSTEM_PROMPT,
    pending_proposal: bool = False,
    optimizer_result_available: bool = False,
    max_history_chars: int = DEFAULT_MAX_HISTORY_CHARS,
) -> list[ChatMessage]:
    """Build a provider prompt that keeps schedule data separate from instructions."""
    system_content = f"{system_prompt}\n\nCurrent schedule summary:\n{describe_schedule(schedule_yaml)}"
    if pending_proposal:
        system_content += (
            "\nA validated proposal is pending. Its exact candidate and diff are available in the trusted workspace "
            "files described above."
        )
    if attachments:
        system_content += f"\nAttached files: {len(attachments)}. Manifest: /workspace/attachments/manifest.json."
    if optimizer_result_available:
        system_content += f"\nOptimization result: {WORKSPACE_OPTIMIZER_RESULT}."
    return [
        ChatMessage(role="system", content=system_content),
        *recent_history(transcript, max_history_chars),
        ChatMessage(role="user", content=question),
    ]
