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
import { applyAssistantEvent } from './assistantEvents';
import { applyModelInput, type ChatMessage } from './chatTranscript';
import type { ModelInput } from './aiClient';

const input: ModelInput = {
  system: 'System policy',
  messages: [
    { kind: 'app', index: 5, title: 'Schedule Spec changed', content: 'Changed schedule' },
    { kind: 'question', content: 'Exact question' },
    { kind: 'status', content: 'Current status' },
  ],
};

describe('model input transcript placement', () => {
  it('places a legacy proposal follow-up after the original reply and keeps its prompt once on replay', () => {
    const messages: ChatMessage[] = [
      { id: 'question', role: 'user', content: 'Make a proposal' },
      { id: 'answer', role: 'assistant', content: 'Proposed' },
      { id: 'follow-up', role: 'assistant', content: 'Reviewing the decision' },
    ];
    const followUp: ModelInput = {
      system: 'Policy',
      messages: [
        { kind: 'app', index: 2, title: 'Proposal Approved', content: 'The user approved the proposal.' },
        { kind: 'app', index: 3, content: 'The user selected Approve. The proposal is now the current Schedule Spec.' },
        { kind: 'status', content: 'Current status' },
      ],
    };
    const turn = { questionId: 'question', assistantId: 'follow-up' };
    const projected = applyModelInput(messages, followUp, turn);
    expect(projected.map(message => message.content)).toEqual([
      'Make a proposal', 'Proposed', 'Policy', 'The user approved the proposal.',
      'The user selected Approve. The proposal is now the current Schedule Spec.', 'Current status', 'Reviewing the decision',
    ]);
    expect(applyModelInput(projected, followUp, turn).map(message => message.id)).toEqual(projected.map(message => message.id));
  });

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


it('retains initial and changed schedule snapshots through retries, AI edits, and browser reload', () => {
  const request = (yaml: string): ModelInput => ({ system: 'Policy', scheduleSpecYaml: yaml,
    messages: [{ kind: 'question', content: 'Check schedule' }] });
  let messages: ChatMessage[] = [];
  const send = (id: string, yaml: string) => {
    messages.push({ id: `q-${id}`, role: 'user', content: 'Check schedule' },
      { id, role: 'assistant', content: '' });
    messages = applyModelInput(messages, request(yaml), { questionId: `q-${id}`, assistantId: id });
  };
  send('a', '');
  expect(messages.find(message => message.source === 'schedule')).toMatchObject({
    title: 'Initial Schedule Spec sent', content: '',
  });
  messages = applyModelInput(messages, request(''), { questionId: 'q-a', assistantId: 'a' });
  send('b', '');
  expect(messages.filter(message => message.source === 'schedule')).toHaveLength(1);
  messages = messages.map(message => message.id === 'b' ? applyAssistantEvent(message,
    { type: 'schedule_spec_applied', diff: 'Changed', scheduleSpecYaml: '# AI edit\npeople: []\n' }) : message);
  messages = applyModelInput(messages, request(''), { questionId: 'q-b', assistantId: 'b' });
  // Reload retains the last accepted schedule, including AI changes.
  messages = JSON.parse(JSON.stringify(messages));
  send('c', '# AI edit\npeople: []\n');
  expect(messages.filter(message => message.source === 'schedule')).toHaveLength(1);
  send('d', '# App edit\npeople: []\n');
  const snapshots = messages.filter(message => message.source === 'schedule');
  expect(snapshots.map(message => [message.title, message.content])).toEqual([
    ['Initial Schedule Spec sent', ''], ['Updated Schedule Spec sent', '# App edit\npeople: []\n'],
  ]);
  expect(messages.indexOf(snapshots[1]) + 1).toBe(messages.findIndex(message => message.id === 'q-d'));
  expect(messages.find(message => message.id === 'schedule-a')?.content).toBe('');
});
