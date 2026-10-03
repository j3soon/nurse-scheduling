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

import type { SessionReset, StreamCallbacks } from './aiClient';

interface ForegroundRun {
  runId?: string;
  callbacks: StreamCallbacks;
  deferred: (() => void)[];
  reject: (error: Error) => void;
}

/** Route one session stream independently of React and HTTP response timing. */
export class SessionEventRouter {
  foreground: ForegroundRun | null = null;

  begin(callbacks: StreamCallbacks, reject: (error: Error) => void): ForegroundRun {
    const run = { callbacks, reject, deferred: [] as (() => void)[] };
    this.foreground = run;
    return run;
  }

  forRun(runId: string, background: StreamCallbacks, ownsConversation: () => boolean): StreamCallbacks | undefined {
    const foreground = this.foreground;
    if (!foreground) return undefined;
    if (foreground.runId) return foreground.runId === runId ? foreground.callbacks : undefined;
    // A fast run can publish before POST identifies it. Preserve both foreground
    // and review events until that acknowledgement chooses their destination.
    return Object.fromEntries(Object.entries(background).map(([name, value]) => [
      name, typeof value === 'function' ? (...args: unknown[]) => {
        const deliver = () => {
          if (!ownsConversation()) return;
          const target = foreground.runId === runId ? foreground.callbacks : background;
          const handler = target[name as keyof StreamCallbacks];
          if (typeof handler === 'function') (handler as (...args: unknown[]) => unknown)(...args);
        };
        if (foreground.runId) deliver();
        else foreground.deferred.push(deliver);
      } : value,
    ])) as StreamCallbacks;
  }

  acknowledge(run: ForegroundRun, runId: string, identify: (id: string) => void): void {
    run.runId = runId;
    identify(runId);
    run.deferred.splice(0).forEach(deliver => deliver());
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
