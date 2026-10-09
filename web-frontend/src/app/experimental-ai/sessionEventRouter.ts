/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2026 Johnson Sun
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

// This code is mostly AI generated.

import type { SessionReset } from './aiClient';
import type { SessionEvent, SessionEventHandler } from './sessionEvents';

interface DeferredEvent {
  event: SessionEvent;
  background: SessionEventHandler;
  ownsConversation: () => boolean;
}

interface ForegroundRun {
  runId?: string;
  handle: SessionEventHandler;
  deferred: DeferredEvent[];
  reject: (error: Error) => void;
  refresh: () => void;
  pendingReset?: SessionReset;
}

/** Route one session stream independently of React and HTTP response timing. */
export class SessionEventRouter {
  foreground: ForegroundRun | null = null;

  begin(handle: SessionEventHandler, reject: (error: Error) => void, refresh: () => void): ForegroundRun {
    const run = { handle, reject, refresh, deferred: [] as DeferredEvent[] };
    this.foreground = run;
    return run;
  }

  dispatch(event: SessionEvent, background: SessionEventHandler, ownsConversation: () => boolean): void {
    if (!ownsConversation()) return;
    if (event.type === 'session_reset' && !event.runId) {
      background(event);
      this.reset(event.reset);
      for (const runId of event.reset.runIds) this.dispatch({ ...event, runId }, background, ownsConversation);
      return;
    }
    const foreground = this.foreground;
    if (!foreground || !event.runId) { background(event); return; }
    if (foreground.runId) {
      (foreground.runId === event.runId ? foreground.handle : background)(event);
      return;
    }
    // A fast run can publish before POST identifies it. Preserve both foreground
    // and review events until that acknowledgement chooses their destination.
    foreground.deferred.push({ event, background, ownsConversation });
  }

  acknowledge(run: ForegroundRun, runId: string, identify: (id: string) => void): void {
    if (this.foreground !== run) return;
    run.runId = runId;
    identify(runId);
    const terminalBuffered = run.deferred.some(({ event }) => event.runId === runId
      && ['done', 'stopped', 'stale', 'error'].includes(event.type));
    for (const { event, background, ownsConversation } of run.deferred.splice(0)) {
      if (ownsConversation()) {
        (event.runId === runId ? run.handle : background)(event);
      }
    }
    // An earlier snapshot may predate acceptance. Refresh it after identifying the
    // run instead of treating missing output as proof that a new run expired.
    if (run.pendingReset && !terminalBuffered && !run.pendingReset.terminalRunIds.includes(runId)
      && run.pendingReset.activeRunId !== runId) run.refresh();
    run.pendingReset = undefined;
  }

  reset(reset: SessionReset): void {
    const run = this.foreground;
    if (run && !run.runId) run.pendingReset = reset;
    if (run?.runId && !reset.runIds.includes(run.runId)
      && !reset.terminalRunIds.includes(run.runId) && reset.activeRunId !== run.runId) {
      run.reject(new Error('This response expired from event replay. Start a new question.'));
    }
  }

  finish(run: ForegroundRun): void {
    if (this.foreground === run) this.foreground = null;
  }
}
