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

import { dispatchSessionEvent, type SessionReset, type StreamCallbacks } from './aiClient';
import { sessionEventCallbacks, type SessionEvent } from './sessionEvents';

interface DeferredEvent {
  event: SessionEvent;
  background: StreamCallbacks;
  ownsConversation: () => boolean;
}

interface ForegroundRun {
  runId?: string;
  callbacks: StreamCallbacks;
  deferred: DeferredEvent[];
  reject: (error: Error) => void;
}

/** Route one session stream independently of React and HTTP response timing. */
export class SessionEventRouter {
  foreground: ForegroundRun | null = null;

  begin(callbacks: StreamCallbacks, reject: (error: Error) => void): ForegroundRun {
    const run = { callbacks, reject, deferred: [] as DeferredEvent[] };
    this.foreground = run;
    return run;
  }

  forRun(runId: string, background: StreamCallbacks, ownsConversation: () => boolean): StreamCallbacks | undefined {
    const foreground = this.foreground;
    if (!foreground) return undefined;
    if (foreground.runId) return foreground.runId === runId ? foreground.callbacks : undefined;
    // A fast run can publish before POST identifies it. Preserve both foreground
    // and review events until that acknowledgement chooses their destination.
    return sessionEventCallbacks(event => {
      if (!ownsConversation()) return;
      if (foreground.runId) {
        dispatchSessionEvent(foreground.runId === runId ? foreground.callbacks : background, event);
      } else {
        foreground.deferred.push({ event, background, ownsConversation });
      }
    }, runId);
  }

  acknowledge(run: ForegroundRun, runId: string, identify: (id: string) => void): void {
    run.runId = runId;
    identify(runId);
    for (const { event, background, ownsConversation } of run.deferred.splice(0)) {
      if (ownsConversation()) {
        dispatchSessionEvent(event.runId === runId ? run.callbacks : background, event);
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
