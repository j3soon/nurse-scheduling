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

import type { OptimizationProgressPoint } from '@/components/OptimizationProgressChart';
import type { OptimizationActivity } from './aiClient';
import type { ChatMessage } from './chatTranscript';
import { optimizationMessage } from './optimizerMessage';
import type { SessionEvent } from './sessionEvents';

export interface ActiveOptimization extends OptimizationActivity {
  points: OptimizationProgressPoint[];
}

type OptimizationEvent = Extract<SessionEvent, { type: 'optimization' | 'optimization_progress' }>;

// A solver can emit a progress event per incumbent solution, and the whole series is
// persisted with the conversation. Halving the oldest points keeps the sparkline shape
// while bounding the array and the tab storage a long run consumes.
const OPTIMIZATION_PROGRESS_POINT_LIMIT = 500;

export function applyOptimizationEvent(
  current: ActiveOptimization | null, event: OptimizationEvent,
): ActiveOptimization | null {
  if (event.type === 'optimization') {
    const { activity } = event;
    if (activity.terminal) return current?.jobId === activity.jobId ? null : current;
    return { ...activity, points: current?.jobId === activity.jobId ? current.points : [] };
  }
  const { jobId, point } = event.activity;
  if (current !== null && current.jobId !== jobId) return current;
  const previous = current?.points ?? [];
  const last = previous.at(-1);
  if (last?.elapsedSeconds === point.elapsedSeconds && last.currentBestScore === point.currentBestScore) {
    return current;
  }
  const retained = previous.length >= OPTIMIZATION_PROGRESS_POINT_LIMIT
    ? previous.filter((_, index) => index % 2 === 0 || index === previous.length - 1)
    : previous;
  return {
    jobId,
    state: current?.state ?? 'running',
    terminal: false,
    downloadable: false,
    points: [...retained, point],
  };
}

export function appendOptimizationResult(
  messages: ChatMessage[], activity: OptimizationActivity, occurredAt: number,
): ChatMessage[] {
  const id = `optimizer-${activity.jobId}`;
  if (messages.some(message => message.id === id)) return messages;
  return [...messages, {
    id,
    role: 'optimizer',
    createdAt: occurredAt,
    content: optimizationMessage(activity),
    optimizerJob: { jobId: activity.jobId, downloadable: activity.downloadable },
  }];
}
