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
});
