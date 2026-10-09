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
import { applyModelInput, type ChatMessage } from './chatTranscript';
import type { ModelInput } from './aiClient';

const input: ModelInput = {
  system: 'System policy',
  messages: [
    { kind: 'app', index: 5, title: 'Schedule changed', content: 'Changed schedule' },
    { kind: 'question', content: 'Exact question' },
    { kind: 'status', content: 'Current status' },
  ],
};

describe('model input transcript placement', () => {
  it('places request context before its original answer and keeps later replies in place', () => {
    const messages: ChatMessage[] = [
      { id: 'question', role: 'user', content: 'Question' },
      { id: 'answer', role: 'assistant', content: 'First answer' },
      { id: 'later', role: 'assistant', content: 'Later answer' },
    ];
    const projected = applyModelInput(messages, input, { questionId: 'question', assistantId: 'answer' });
    expect(projected.map(message => message.content)).toEqual([
      'System policy', 'Changed schedule', 'Exact question', 'Current status', 'First answer', 'Later answer',
    ]);
    const replayed = applyModelInput(projected, input, { questionId: 'question', assistantId: 'answer' });
    expect(replayed.map(message => message.id)).toEqual(projected.map(message => message.id));
    expect(messages[0].content).toBe('Question');
  });

  it('replaces optimizer input beside its answer without moving other answers', () => {
    const messages: ChatMessage[] = [
      { id: 'answer', role: 'assistant', content: 'Optimizer review' },
      { id: 'later', role: 'assistant', content: 'Later answer' },
    ];
    const optimizer: ModelInput = { system: 'Policy', messages: [{ kind: 'optimizer', content: 'Optimizer result' }] };
    const projected = applyModelInput(messages, optimizer, { questionId: null, assistantId: 'answer' });
    const replaced = applyModelInput(projected, {
      ...optimizer, messages: [{ kind: 'optimizer', content: 'Updated result' }],
    }, { questionId: null, assistantId: 'answer' });
    expect(replaced.map(message => message.content)).toEqual(['Policy', 'Updated result', 'Optimizer review', 'Later answer']);
    expect(applyModelInput(messages, input, { questionId: null, assistantId: 'missing' })).toBe(messages);
  });
});
