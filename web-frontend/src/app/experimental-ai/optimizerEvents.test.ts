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

// This test is mostly AI generated.

import { describe, expect, it } from 'vitest';
import { applyOptimizationEvent, appendOptimizationResult } from './optimizerEvents';
import { parseOptimizerMessage } from './optimizerMessage';
import type { SessionEvent } from './sessionEvents';

describe('optimizer event projection', () => {
  it('preserves early progress through status updates and ignores duplicate or foreign points', () => {
    const progress: SessionEvent = {
      type: 'optimization_progress',
      activity: { jobId: 'job-1', point: { currentBestScore: 0, elapsedSeconds: 1 } },
    };
    const early = applyOptimizationEvent(null, progress);
    const active = applyOptimizationEvent(early, {
      type: 'optimization',
      activity: { jobId: 'job-1', state: 'running', terminal: false, downloadable: false },
    });

    expect(active?.points).toEqual([progress.activity.point]);
    expect(applyOptimizationEvent(active, progress)).toBe(active);
    expect(applyOptimizationEvent(active, {
      type: 'optimization_progress',
      activity: { jobId: 'another-job', point: { currentBestScore: 9, elapsedSeconds: 2 } },
    })).toBe(active);
  });

  it('records a replayed completion once without clearing a different active job', () => {
    const active = applyOptimizationEvent(null, {
      type: 'optimization',
      activity: { jobId: 'new-job', state: 'running', terminal: false, downloadable: false },
    });
    const completion: SessionEvent = {
      type: 'optimization',
      activity: {
        jobId: 'old-job', state: 'completed', terminal: true, downloadable: true,
        result: { score: 0 }, error: { message: 'A detail\nSolver: continuation text' },
      },
    };
    const messages = appendOptimizationResult([], completion.activity, 100);

    expect(applyOptimizationEvent(active, completion)).toBe(active);
    expect(appendOptimizationResult(messages, completion.activity, 200)).toBe(messages);
    expect(messages[0]).toMatchObject({
      id: 'optimizer-old-job', createdAt: 100, role: 'optimizer',
      optimizerJob: { jobId: 'old-job', downloadable: true },
    });
    expect(parseOptimizerMessage(messages[0].content).details).toEqual([
      { label: 'Final score', value: '0' },
      { label: 'Error', value: 'A detail\nSolver: continuation text' },
    ]);
    expect(applyOptimizationEvent(active, {
      ...completion, activity: { ...completion.activity, jobId: 'new-job' },
    })).toBeNull();
  });
});
