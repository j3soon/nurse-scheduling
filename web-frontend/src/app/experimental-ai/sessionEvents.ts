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

import type {
  ContextUsage,
  OptimizationActivity,
  OptimizationProgressActivity,
  SessionReset,
  StreamCallbacks,
  ToolActivity,
  ToolStartActivity,
} from './aiClient';

// Parsed events carry run identity. run_context is the client's replay adoption signal.
export type SessionEvent = (
  | { type: 'session_reset'; reset: SessionReset }
  | { type: 'run_context'; runId: string }
  | { type: 'run_start'; runId: string; trigger: string }
  | { type: 'delta' | 'reasoning'; text: string }
  | { type: 'truncated' }
  | { type: 'tool_start'; activity: ToolStartActivity }
  | { type: 'tool'; activity: ToolActivity }
  | { type: 'steering'; messageId: string; message: string }
  | { type: 'schedule_change'; scheduleYaml: string }
  | { type: 'proposal'; diff: string }
  | { type: 'optimization'; activity: OptimizationActivity }
  | { type: 'optimization_progress'; activity: OptimizationProgressActivity }
  | { type: 'done' | 'stopped' }
  | { type: 'stale' | 'error'; message: string }
  | { type: 'context_usage'; usage: ContextUsage }
  | { type: 'history_trimmed'; dropped: number }
) & { runId?: string };

export type SessionEventHandler = (event: SessionEvent) => void;

/** Adapt callback consumers to one handler without string-indexed invocation. */
export function sessionEventCallbacks(handle: SessionEventHandler, runId?: string): StreamCallbacks {
  const emit = (event: SessionEvent) => handle(
    event.runId !== undefined || runId === undefined ? event : { ...event, runId },
  );
  return {
    onEvent: emit,
    onReset: reset => emit({ type: 'session_reset', reset }),
    onRunContext: runId => emit({ type: 'run_context', runId }),
    onRunStart: (runId, trigger) => emit({ type: 'run_start', runId, trigger }),
    onDelta: text => emit({ type: 'delta', text }),
    onReasoning: text => emit({ type: 'reasoning', text }),
    onTruncated: () => emit({ type: 'truncated' }),
    onToolStart: activity => emit({ type: 'tool_start', activity }),
    onTool: activity => emit({ type: 'tool', activity }),
    onSteering: (messageId, message) => emit({ type: 'steering', messageId, message }),
    onScheduleChange: scheduleYaml => emit({ type: 'schedule_change', scheduleYaml }),
    onProposal: diff => emit({ type: 'proposal', diff }),
    onOptimization: activity => emit({ type: 'optimization', activity }),
    onOptimizationProgress: activity => emit({ type: 'optimization_progress', activity }),
    onDone: runId => emit({ type: 'done', runId }),
    onStopped: runId => emit({ type: 'stopped', runId }),
    onStale: message => emit({ type: 'stale', message }),
    onError: message => emit({ type: 'error', message }),
    onContextUsage: usage => emit({ type: 'context_usage', usage }),
    onHistoryTrimmed: dropped => emit({ type: 'history_trimmed', dropped }),
  };
}
