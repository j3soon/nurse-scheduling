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
import {
  AssistantEvent,
  applyAssistantEvent,
  assistantEventCallbacks,
  stopResponse,
} from './assistantEvents';
import type { ChatExportMessage } from './chatExport';

const empty: ChatExportMessage = { role: 'assistant', content: '', status: 'pending' };

function reduce(events: AssistantEvent[]): ChatExportMessage {
  return events.reduce(applyAssistantEvent, empty);
}

describe('assistant events', () => {
  it('merges consecutive text and reasoning while keeping their order', () => {
    const message = reduce([
      { type: 'reasoning', text: 'Check ' },
      { type: 'reasoning', text: 'people.' },
      { type: 'delta', text: 'Alice ' },
      { type: 'delta', text: 'works.' },
      { type: 'reasoning', text: 'Verify.' },
      { type: 'delta', text: ' Done.' },
    ]);

    expect(message.content).toBe('Alice works. Done.');
    expect(message.activity).toEqual([
      { kind: 'reasoning', text: 'Check people.' },
      { kind: 'response', text: 'Alice works.' },
      { kind: 'reasoning', text: 'Verify.' },
      { kind: 'response', text: ' Done.' },
    ]);
  });

  it('completes the running tool that shares the result call ID', () => {
    const message = reduce([
      { type: 'tool_start', activity: { toolCallId: 'a', name: 'read', arguments: 'a.txt' } },
      { type: 'tool_start', activity: { toolCallId: 'b', name: 'read', arguments: 'b.txt' } },
      { type: 'tool', activity: { toolCallId: 'a', name: 'read', arguments: 'a.txt', result: 'A', ok: true } },
    ]);

    expect(message.activity).toEqual([
      { kind: 'tool', toolCallId: 'a', name: 'read', arguments: 'a.txt', result: 'A', ok: true },
      { kind: 'tool', toolCallId: 'b', name: 'read', arguments: 'b.txt', result: '', ok: true, state: 'running' },
    ]);
  });

  it('matches a result without a call ID to the first running tool of that name', () => {
    const message = reduce([
      { type: 'tool_start', activity: { name: 'read', arguments: 'a.txt' } },
      { type: 'tool_start', activity: { name: 'bash', arguments: 'ls' } },
      { type: 'tool', activity: { name: 'read', arguments: 'a.txt', result: 'A', ok: false } },
    ]);

    expect(message.activity?.map(entry => entry.kind === 'tool' && [entry.name, entry.state, entry.ok])).toEqual([
      ['read', undefined, false],
      ['bash', 'running', true],
    ]);
  });

  it('diffs each preview against the previous working copy', () => {
    const events: AssistantEvent[] = [];
    const working = { current: null as string | null };
    const callbacks = assistantEventCallbacks(event => events.push(event), working, { current: 'v0' });

    callbacks.onScheduleChange('v1');
    callbacks.onScheduleChange('v2');

    expect(events).toEqual([
      { type: 'schedule_change', before: 'v0', after: 'v1' },
      { type: 'schedule_change', before: 'v1', after: 'v2' },
    ]);
    expect(working.current).toBe('v2');
  });

  it('stops a response without adding answer text', () => {
    const message = stopResponse(reduce([
      { type: 'delta', text: 'Partial.' },
      { type: 'tool_start', activity: { toolCallId: 'a', name: 'bash', arguments: 'sleep 60' } },
    ]));

    expect(message.status).toBe('stopped');
    expect(message.content).toBe('Partial.');
    expect(message.activity?.at(-1)).toEqual(expect.objectContaining({ state: 'interrupted' }));
  });
});
