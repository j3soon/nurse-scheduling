"""Restart recovery for AI chat sessions, runs, and replayable events."""

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

import asyncio
import logging
from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import suppress
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from .agent_session import STALE_RUN_ERROR, AgentSession
from .history import ChatHistory, EntryRow, EventRow, RunKind, RunStatus
from .provider import TokenUsage
from .session_event_stream import SessionEvent, SessionEventStream, fold_recovery
from .session_events import AgentSessionTerminalEvent
from .sessions import SessionStore

logger = logging.getLogger("nurse_scheduling.ai.recovery")
RESTART_ERROR = (
    "The AI service restarted during this response. Your question and saved output were recovered. "
    "You can retry this run."
)
BACKGROUND_RESTART_ERROR = "The AI service restarted during this background response. Its saved output was recovered."
# Bound how long a storage reset waits for pending event writes before it serves the projection.
FLUSH_TIMEOUT_SECONDS = 5
MAX_RETRY_DELAY_SECONDS = 30


def _event_rows(events: Sequence[SessionEvent]) -> list[EventRow]:
    """Combine adjacent text fragments of one run into a row covering their IDs."""
    rows: list[EventRow] = []
    for event in events:
        run_id = event.data.get("run_id")
        run_id = run_id if isinstance(run_id, str) else None
        if rows and event.type in {"delta", "reasoning"}:
            first, _last, previous_run, kind, data = rows[-1]
            if kind == event.type and previous_run == run_id:
                rows[-1] = (first, event.id, run_id, kind, {**data, "text": data["text"] + event.data["text"]})
                continue
        rows.append((event.id, event.id, run_id, event.type, event.data))
    return rows


class SessionRecovery:
    """Save session state in capture order and restore sessions from PostgreSQL.

    Without a history database, every operation succeeds without storage, and
    sessions exist only in process memory.
    """

    def __init__(self, history: ChatHistory | None, store: SessionStore, event_stream: SessionEventStream) -> None:
        self.history = history
        self._store = store
        self._event_stream = event_stream
        self._locks: dict[str, asyncio.Lock] = {}
        self._pins: Counter[str] = Counter()
        self._unsaved: set[str] = set()
        # Final run writes that failed, retried before the next state save of their session.
        self._unsaved_outcomes: dict[str, list[tuple[Any, ...]]] = {}
        # Conversation entries in session order, saved by the next write of their session.
        self._pending_entries: dict[str, list[EntryRow]] = {}
        self._entry_writers: dict[str, asyncio.Task[None]] = {}
        self._pending_events: dict[str, list[SessionEvent]] = {}
        self._writers: dict[str, asyncio.Task[None]] = {}
        self._restore_lock = asyncio.Lock()
        if history is not None:
            store.on_entry(self._observe_entry)
            event_stream.observer = self._observe
            event_stream.load_recovery = self._load_recovery

    @property
    def enabled(self) -> bool:
        return self.history is not None

    def pin(self, session_id: str) -> Callable[..., None]:
        """Keep a session loaded until the returned release runs.

        The store releases a run before its outcome is saved, and an endpoint changes a
        session before its write starts. Eviction must wait for both.
        """
        self._pins[session_id] += 1
        released = False

        def release(*_args: object) -> None:
            nonlocal released
            if released:
                return
            released = True
            self._pins[session_id] -= 1
            if self._pins[session_id] <= 0:
                del self._pins[session_id]

        return release

    def evictable(self, session_id: str) -> bool:
        """Whether storage holds everything an unloaded session would need."""
        return (
            session_id not in self._pins
            and session_id not in self._unsaved
            and session_id not in self._unsaved_outcomes
            and session_id not in self._pending_entries
            and session_id not in self._pending_events
        )

    def forget(self, session_id: str) -> None:
        """Drop the coordination state of a retired session. Storage keeps its saved copy."""
        self._locks.pop(session_id, None)
        self._unsaved.discard(session_id)
        self._unsaved_outcomes.pop(session_id, None)
        self._pending_entries.pop(session_id, None)
        self._pending_events.pop(session_id, None)
        for writers in (self._entry_writers, self._writers):
            writer = writers.pop(session_id, None)
            if writer is not None:
                writer.cancel()

    def _record(self, session_id: str, saved: bool) -> bool:
        """Keep a session whose newest state failed to save, so eviction never drops its only copy."""
        if saved:
            self._unsaved.discard(session_id)
        elif self._store.get(session_id) is not None:
            self._unsaved.add(session_id)
        return saved

    async def _write_state(self, session_id: str, operation: str, /, *args: Any, **kwargs: Any) -> bool:
        """Capture the current state and write it, one session write at a time.

        Each write captures the whole state and then waits for a database thread. The
        lock commits writes in capture order, so an older state never replaces a newer one.
        """
        assert self.history is not None
        release = self.pin(session_id)
        try:
            async with self._locks.setdefault(session_id, asyncio.Lock()):
                if self._store.get(session_id) is None:
                    return True
                for outcome in tuple(self._unsaved_outcomes.get(session_id, ())):
                    if not await self._write_with_entries(session_id, "finish_run", *outcome, session_id=session_id):
                        return self._record(session_id, False)
                    self._unsaved_outcomes[session_id].remove(outcome)
                self._unsaved_outcomes.pop(session_id, None)
                return self._record(session_id, await self._write_with_entries(session_id, operation, *args, **kwargs))
        finally:
            release()

    async def _write_with_entries(self, session_id: str, operation: str, /, *args: Any, **kwargs: Any) -> bool:
        """Write the current state in one transaction with every entry it counts."""
        assert self.history is not None
        entries = list(self._pending_entries.get(session_id, ()))
        state = self._store.recovery_state(session_id)
        saved = await self.history.write(operation, *args, state=state, entries=entries, **kwargs)
        if saved:
            self._entries_saved(session_id, len(entries))
        return saved

    def _entries_saved(self, session_id: str, count: int) -> None:
        pending = self._pending_entries.get(session_id)
        if pending is not None:
            del pending[:count]
            if not pending:
                del self._pending_entries[session_id]

    def _observe_entry(self, session_id: str, entry: EntryRow) -> None:
        """Queue a conversation entry, which a background writer saves as Pi saves each message."""
        self._pending_entries.setdefault(session_id, []).append(entry)
        writer = self._entry_writers.get(session_id)
        if writer is None or writer.done():
            self._entry_writers[session_id] = asyncio.create_task(
                self._write_entries(session_id), name=f"ai-entries-{session_id}"
            )

    async def _write_entries(self, session_id: str) -> None:
        """Save queued entries in order, retrying a failed batch until storage accepts it."""
        assert self.history is not None
        delay = 1.0
        while self._pending_entries.get(session_id):
            async with self._locks.setdefault(session_id, asyncio.Lock()):
                entries = list(self._pending_entries.get(session_id, ()))
                saved = not entries or await self.history.write("append_entries", session_id, entries)
                if saved:
                    self._entries_saved(session_id, len(entries))
            if saved:
                delay = 1.0
                continue
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RETRY_DELAY_SECONDS)

    async def save(self, session_id: str, credential_id: str | None = None) -> bool:
        if self.history is None:
            return True
        return await self._write_state(session_id, "save_session", session_id, credential_id=credential_id)

    async def start_run(
        self,
        session_id: str,
        run_id: str,
        prompt: str,
        prompt_seq: int,
        *,
        model: str,
        attachment_count: int,
        kind: RunKind,
        message_id: str | None,
        credential_id: str | None,
    ) -> bool:
        if self.history is None:
            return True
        return await self._write_state(
            session_id,
            "start_run",
            run_id,
            session_id,
            prompt=prompt,
            prompt_seq=prompt_seq,
            model=model,
            attachment_count=attachment_count,
            kind=kind,
            message_id=message_id,
            credential_id=credential_id,
        )

    async def finish_run(
        self,
        session_id: str,
        run_id: str,
        status: RunStatus,
        error_code: str | None,
        usage: TokenUsage | None,
        committed: bool,
    ) -> bool:
        """Save the outcome with the resulting state. A failed write is retried by the next save."""
        if self.history is None:
            return True
        outcome = (run_id, status, error_code, usage, committed)
        if await self._write_state(session_id, "finish_run", *outcome, session_id=session_id):
            return True
        if self._store.get(session_id) is not None:
            self._unsaved_outcomes.setdefault(session_id, []).append(outcome)
        return False

    async def stop_message(self, session_id: str, message_id: str) -> None:
        """Save a named Stop, so its message cannot start later, even after a restart.

        Raises:
            HTTPException: With status 503 when storage cannot save the request.
        """
        if self.history is None:
            return
        release = self.pin(session_id)
        try:
            saved = await self.history.write("stop_message", session_id, message_id)
        finally:
            release()
        if not saved:
            raise HTTPException(status_code=503, detail="The stop request could not be saved. Please try again.")

    async def message_stopped(self, session_id: str, message_id: str) -> bool:
        if self.history is None:
            return False
        return bool(await self._read(session_id, "message_stopped", message_id))

    async def find_message(self, session_id: str, message_id: str) -> tuple[str, str] | None:
        """Return the run ID and prompt of an accepted client message that memory no longer holds."""
        if self.history is None:
            return None
        return await self._read(session_id, "find_message", message_id)

    async def _read(self, session_id: str, operation: str, *args: Any) -> Any:
        """Read storage for a loaded session, which stays loaded until the read returns.

        Raises:
            HTTPException: With status 503 when storage is unavailable.
        """
        assert self.history is not None
        release = self.pin(session_id)
        try:
            return await self.history.read(operation, session_id, *args)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        finally:
            release()

    async def restore(self, session_id: str, owner: str) -> None:
        """Load a saved session after a restart or eviction, and end runs the old process left open.

        Raises:
            HTTPException: With status 404 when no unexpired owned session exists, 503 when
                storage is unavailable, or 429 when no session slot is free.
        """
        assert self.history is not None
        async with self._restore_lock:
            if self._store.get(session_id) is not None:
                return
            try:
                UUID(session_id)
                UUID(owner)
            except ValueError:
                raise HTTPException(status_code=404, detail="Chat session not found.") from None
            try:
                record = await self.history.read("load_session", session_id, owner)
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from None
            if record is None:
                raise HTTPException(status_code=404, detail="Chat session not found.")
            session = self._store.restore(
                session_id,
                owner,
                record["state"],
                record["expires_at"],
                entries=record["entries"],
                next_entry_seq=record["next_entry_seq"],
            )
            self._event_stream.restore(session_id, record["last_event_id"])
            release = self.pin(session_id)
            try:
                for run in record["unfinished_runs"]:
                    await self._end_unfinished_run(session, run["id"], run["kind"], run["status"])
            finally:
                release()

    async def _end_unfinished_run(self, session: AgentSession, run_id: str, kind: str, status: str) -> None:
        """Publish the terminal event a stored run lacks. A running run was interrupted by the restart."""
        terminal: AgentSessionTerminalEvent
        if status == "running":
            assert self.history is not None
            message = BACKGROUND_RESTART_ERROR if kind == "background" else RESTART_ERROR
            terminal = {"type": "error", "message": message}
            await self.finish_run(session.id, run_id, "failed", "service_restart", None, False)
        elif status == "completed":
            terminal = {"type": "done"}
        elif status == "cancelled":
            terminal = {"type": "stopped"}
        elif status == "stale":
            terminal = {"type": "stale", "message": STALE_RUN_ERROR}
        else:
            terminal = {"type": "error", "message": "The AI response failed."}
        session.publish({**terminal, "run_id": run_id})

    def _observe(self, session_id: str, event: SessionEvent) -> None:
        """Queue a published event for storage. Optimizer progress stays transient."""
        if event.type == "optimization_progress":
            return
        self._pending_events.setdefault(session_id, []).append(event)
        writer = self._writers.get(session_id)
        if writer is None or writer.done():
            self._writers[session_id] = asyncio.create_task(
                self._write_events(session_id), name=f"ai-events-{session_id}"
            )

    async def _write_events(self, session_id: str) -> None:
        """Write queued events in order, retrying a failed batch until storage accepts it.

        Readers receive events before they are saved. A restored stream therefore continues
        its IDs past storage and replaces output that a browser saw but storage lacks.
        """
        assert self.history is not None
        delay = 1.0
        while self._pending_events.get(session_id):
            batch = list(self._pending_events[session_id])
            if await self.history.write("append_events", session_id, _event_rows(batch)):
                delay = 1.0
                pending = self._pending_events.get(session_id)
                if pending is not None:
                    del pending[: len(batch)]
                    if not pending:
                        del self._pending_events[session_id]
                continue
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RETRY_DELAY_SECONDS)

    async def flush(self, session_id: str) -> None:
        """Wait until every entry and event so far is saved."""
        for writers in (self._entry_writers, self._writers):
            writer = writers.get(session_id)
            if writer is not None and not writer.done():
                await asyncio.shield(writer)

    async def _load_recovery(self, session_id: str, after_id: int) -> tuple[int, list[SessionEvent]] | None:
        """Build a complete reset from storage. None means storage lags, so the projection serves it."""
        assert self.history is not None
        covered = self._event_stream.cursor(session_id)
        try:
            await asyncio.wait_for(self.flush(session_id), FLUSH_TIMEOUT_SECONDS)
            rows = await self.history.read("load_events", session_id, after_id)
        except (TimeoutError, RuntimeError):
            logger.error("AI recovery reset fell back to the replay projection session_id=%s", session_id)
            return None
        # Rows saved after the cursor capture are part of the reset, so the reader skips them later.
        covered = max([covered, *(last for _first, last, *_rest in rows)])
        return covered, fold_recovery(SessionEvent(last, kind, data) for _first, last, _run, kind, data in rows)

    async def close(self) -> None:
        """Give pending entry and event writes a bounded chance to finish during shutdown."""
        writers = [
            writer
            for writers in (self._entry_writers, self._writers)
            for writer in writers.values()
            if not writer.done()
        ]
        if writers:
            await asyncio.wait(writers, timeout=FLUSH_TIMEOUT_SECONDS)
        for writer in writers:
            writer.cancel()
        for writer in writers:
            with suppress(asyncio.CancelledError):
                await writer
