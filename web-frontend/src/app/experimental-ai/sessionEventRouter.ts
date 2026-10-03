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
}

/** Route one session stream independently of React and HTTP response timing. */
export class SessionEventRouter {
  foreground: ForegroundRun | null = null;

  begin(handle: SessionEventHandler, reject: (error: Error) => void): ForegroundRun {
    const run = { handle, reject, deferred: [] as DeferredEvent[] };
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
    run.runId = runId;
    identify(runId);
    for (const { event, background, ownsConversation } of run.deferred.splice(0)) {
      if (ownsConversation()) {
        (event.runId === runId ? run.handle : background)(event);
      }
    }
  }

  reset(reset: SessionReset): void {
    const run = this.foreground;
    if (run?.runId && !reset.terminalRunIds.includes(run.runId) && reset.activeRunId !== run.runId) {
      run.reject(new Error('This response expired from event replay. Start a new question.'));
    }
  }

  finish(run: ForegroundRun): void {
    if (this.foreground === run) this.foreground = null;
  }
}
