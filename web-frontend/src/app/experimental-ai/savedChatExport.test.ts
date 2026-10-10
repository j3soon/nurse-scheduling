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

import snapshot from '../../../../core/tests/ai_fixtures/chat-export.json';
import { buildSavedChatExport, parseSavedChatSnapshot, projectSavedChat } from './savedChatExport';

describe('saved chat export', () => {
  it('keeps every role and ordered activity from the saved journal', () => {
    const projected = projectSavedChat(parseSavedChatSnapshot(snapshot));
    expect(projected.messages.filter(message => message.role === 'system')).toHaveLength(2);
    expect(projected.messages.some(message => message.source === 'app')).toBe(true);
    expect(projected.messages.some(message => message.source === 'optimizer')).toBe(true);
    expect(projected.messages.filter(message => message.source === 'status')).toHaveLength(1);
    const activities = projected.messages.flatMap(message => message.activity ?? []);
    expect(activities.filter(activity => activity.kind === 'tool').map(activity => activity.name)).toEqual([
      'read', 'read', 'bash', 'edit', 'write', 'optimizer', 'read', 'read', 'bash', 'optimizer',
    ]);
    expect(activities).toContainEqual({ kind: 'schedule-change', before: 'description: Original\n', after: 'description: Updated\n' });
    expect(projected.messages.some(message => message.status === 'failed')).toBe(true);
    expect(projected.messages.some(message => message.status === 'stopped')).toBe(true);
    expect(projected.messages.some(message => message.status === 'pending')).toBe(true);
    expect(projected.messages.some(message => message.downloadId === 'zip-1')).toBe(true);
  });

  it.each(['html', 'markdown'] as const)('exports the complete example as %s', format => {
    const output = buildSavedChatExport(snapshot, format);
    for (const content of ['staff.csv', 'ward.png', 'Command exited with code 7', 'score 17', 'Pending proposal',
      'Optimization running', 'Keep the original names.', 'Download the generated files', 'The current schedule changed.']) {
      expect(output).toContain(content);
    }
    expect(output).toContain('v0.4.3');
    if (format === 'html') {
      expect(output).not.toContain('<script>');
      expect(output).toContain('[Remote image omitted: Ward]');
      expect(output).toContain(' UTC');
    }
  });

  it('refuses invalid timestamps and unsupported snapshot schemas', () => {
    expect(() => buildSavedChatExport({ ...snapshot, schema_version: 2 }, 'html')).toThrow('invalid saved chat snapshot');
    expect(() => buildSavedChatExport({ ...snapshot, snapshot_at: Number.NaN }, 'html')).toThrow('invalid saved chat snapshot');
  });

  it('skips runs without saved events and finalizes only the observed reply', () => {
    const { messages } = projectSavedChat(parseSavedChatSnapshot({
      ...snapshot,
      runs: [
        { ...snapshot.runs[0], id: 'unobserved', prompt: 'Earlier question', started_at: 1 },
        { ...snapshot.runs[0], id: 'observed', prompt: 'Later question', started_at: 2, status: 'cancelled', finished_at: 4 },
      ],
      events: [{ type: 'delta', data: { run_id: 'observed', text: 'Partial answer' }, occurred_at: 3 }],
    }));

    expect(messages.map(message => [message.role, message.content])).toEqual([
      ['user', 'Later question'], ['assistant', 'Partial answer'],
    ]);
    expect(messages[1].status).toBe('stopped');
    expect(messages[1].responseCompletedAt).toBe(4);
  });

  it.each([1, 2])('keeps %s steering messages before one assistant when no output has started', count => {
    const runId = snapshot.runs[0].id;
    const events = [
      { type: 'run_start', data: { run_id: runId }, occurred_at: 1 },
      { type: 'delta', data: { run_id: runId, text: '' }, occurred_at: 2 },
      { type: 'truncated', data: { run_id: runId }, occurred_at: 3 },
      ...Array.from({ length: count }, (_, index) => ({
        type: 'steering', data: { run_id: runId, message_id: `queued-${index}`, message: `Queued ${index}` }, occurred_at: 4 + index,
      })),
      { type: 'delta', data: { run_id: runId, text: 'Answer' }, occurred_at: 7 },
      { type: 'done', data: { run_id: runId }, occurred_at: 8 },
    ];
    const { messages } = projectSavedChat(parseSavedChatSnapshot({
      ...snapshot, runs: [{ ...snapshot.runs[0], prompt: 'First' }], events,
    }));
    expect(messages.map(message => [message.role, message.content])).toEqual([
      ['user', 'First'], ...Array.from({ length: count }, (_, index) => ['user', `Queued ${index}`]), ['assistant', 'Answer'],
    ]);
    expect(messages.at(-1)?.truncated).toBe(true);
  });

  it('inserts a steering reply after its previous output when an optimizer notice arrived meanwhile', () => {
    const runId = snapshot.runs[0].id;
    const events = [
      { type: 'run_start', data: { run_id: runId }, occurred_at: 1 },
      { type: 'reasoning', data: { run_id: runId, text: 'Checking' }, occurred_at: 2 },
      { type: 'optimization', data: { job_id: 'job-1', state: 'cancelled', terminal: true, downloadable: false }, occurred_at: 3 },
      { type: 'steering', data: { run_id: runId, message_id: 'queued', message: 'Queued' }, occurred_at: 4 },
      { type: 'delta', data: { run_id: runId, text: 'Answer' }, occurred_at: 5 },
      { type: 'done', data: { run_id: runId }, occurred_at: 6 },
    ];
    const { messages } = projectSavedChat(parseSavedChatSnapshot({
      ...snapshot, runs: [{ ...snapshot.runs[0], prompt: 'First' }], events,
    }));
    expect(messages.map(message => message.role)).toEqual(['user', 'assistant', 'user', 'assistant', 'optimizer']);
    expect(messages[1].activity).toEqual([{ kind: 'reasoning', text: 'Checking' }]);
    expect(messages[1].responseCompletedAt).toBe(4);
    expect(messages[3].content).toBe('Answer');
  });
});
