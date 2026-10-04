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

import { type ChatMessage, applyResponseEvent, beginResponse, createResponse, resetRunMessages, steerResponse } from './chatTranscript';

describe('chat transcript', () => {
  it.each([
    { kind: 'foreground', continuationId: 'next', completedId: 'answer' },
    { kind: 'background', continuationId: 'answer', completedId: 'answer:queued' },
  ])('keeps steering segments and run identity for $kind output', ({ continuationId, completedId }) => {
    const started = beginResponse([], createResponse('answer', 10, 'run'));
    const streamed = applyResponseEvent(started, 'answer', { type: 'delta', text: 'Checking.' }, 15);
    const user: ChatMessage = { id: 'queued', runId: 'run', role: 'user', content: 'Check Tuesday.', createdAt: 17 };
    const steered = steerResponse(streamed, 'answer', user, 20, continuationId, completedId);

    expect(steered.map(message => [message.id, message.runId, message.content])).toEqual([
      [completedId, 'run', 'Checking.'],
      ['queued', 'run', 'Check Tuesday.'],
      [continuationId, 'run', ''],
    ]);
    expect(steered[0].responseCompletedAt).toBe(20);
    expect(steered[2].responseStartedAt).toBe(20);
    expect(steerResponse(steered, continuationId, user, 25, 'duplicate')).toBe(steered);
  });

  it('replaces recovered output without removing its original prompt or another run', () => {
    const prompt: ChatMessage = { id: 'prompt', role: 'user', content: 'Question.' };
    const other = createResponse('other', 5, 'other-run');
    const transcript = [prompt, other, createResponse('early', 10), createResponse('old', 12, 'run')];
    const recovered = resetRunMessages(transcript, ['run'], createResponse('answer', 20, 'run'), new Set(['early']));
    const resumed = beginResponse(recovered, createResponse('answer', 30, 'run'));
    const completed = applyResponseEvent(resumed, 'answer', { type: 'done' }, 40);

    expect(completed.map(message => message.id)).toEqual(['prompt', 'other', 'answer']);
    expect(completed[0]).toBe(prompt);
    expect(completed[1]).toBe(other);
    expect(completed[2].responseStartedAt).toBe(20);
    expect(completed[2].responseCompletedAt).toBe(40);
    expect(completed[2].status).toBeUndefined();
  });
});
