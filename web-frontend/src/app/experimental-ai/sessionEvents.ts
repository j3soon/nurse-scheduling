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

export interface SessionStreamOptions {
  onEvent: SessionEventHandler;
  lastEventId?: number;
  onEventId?: (id: number) => void;
}
