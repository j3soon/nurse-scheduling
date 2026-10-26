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

import { describe, expect, it, vi } from 'vitest';
import {
  AssistantEvent,
  applyAssistantEvent,
  invalidateRunSummaries,
  messageId,
  toAssistantEvent,
} from './assistantEvents';
import type { ChatMessage, ChatMessageContent } from './chatTranscript';

const empty: ChatMessageContent = { role: 'assistant', content: '', status: 'pending' };

function reduce(events: AssistantEvent[]): ChatMessageContent {
  return events.reduce((message, event) => applyAssistantEvent(message, event), empty);
}

describe('assistant events', () => {
  it('updates one compaction counter across retries and passes, then retains its final count', () => {
    const result = reduce([
      { type: 'compaction_start', reason: 'manual', tokensBefore: 10000 },
      { type: 'generation_progress', kind: 'compaction', characters: 50, step: 1 },
      { type: 'generation_progress', kind: 'compaction', characters: 0, step: 1 },
      { type: 'generation_progress', kind: 'compaction', characters: 2, step: 2 },
      { type: 'compaction_end', reason: 'manual', tokensBefore: 10000, success: true, aborted: false, summary: '新😀' },
    ]);
    expect(result.activity?.filter(entry => entry.kind === 'compaction')).toEqual([
      expect.objectContaining({ state: 'completed', characters: 2, step: 2, summary: '新😀' }),
    ]);
  });

  it('replaces tool preparation with execution and drops a failed draft before retrying', () => {
    const result = reduce([
      { type: 'generation_progress', kind: 'tool_calls', characters: 100, step: 1 },
      { type: 'provider_retry', message: 'Retrying' },
      { type: 'generation_progress', kind: 'tool_calls', characters: 2, step: 1 },
      { type: 'tool_start', activity: { name: 'read', arguments: '{}', toolCallId: 'one' } },
      { type: 'tool', activity: { name: 'read', arguments: '{}', toolCallId: 'one', result: '新😀', ok: true } },
    ]);
    expect(result.activity).toEqual([
      { kind: 'notice', text: 'Retrying' },
      { kind: 'tool', name: 'read', arguments: '{}', toolCallId: 'one', result: '新😀', ok: true },
    ]);
    const stopped = reduce([{ type: 'generation_progress', kind: 'tool_calls', characters: 4, step: 1 }, { type: 'stopped' }]);
    expect(stopped.activity?.[0]).toMatchObject({ state: 'interrupted', argumentsCharacters: 4 });
  });

  it('invalidates only summaries from the failed run while preserving earlier output', () => {
    const messages: ChatMessage[] = ['other', 'failed', 'failed'].map((runId, index) => ({
      id: `reply-${index}`, runId, role: 'assistant', content: 'Completed output.',
      activity: [{ kind: 'compaction', reason: 'threshold', state: 'completed', summary: `Summary ${index}`, text: 'Summarized.' },
        { kind: 'response', text: 'Completed output.', context: 'complete' }],
    }));
    const updated = invalidateRunSummaries(messages, 'failed');
    expect(updated[0]).toBe(messages[0]);
    for (const message of updated.slice(1)) {
      expect(message.activity?.[0]).toMatchObject({ invalidated: true });
      expect(message.activity?.[1]).toMatchObject({ text: 'Completed output.', context: 'complete' });
      expect(message.status).toBeUndefined();
    }
    expect(messages[1].activity?.[0]).not.toHaveProperty('invalidated');
  });
  it.each([true, false])('records a manual request and skips unchanged context, with start=%s', withStart => {
    const message = reduce([
      ...(withStart ? [{ type: 'compaction_start' as const, reason: 'manual' as const, tokensBefore: 4000 }] : []),
      { type: 'compaction_end', reason: 'manual', tokensBefore: 4000, success: false, aborted: false, skipped: true },
      { type: 'done' },
    ]);
    expect(message.activity).toEqual([
      { kind: 'notice', text: 'You requested context compaction.' },
      { kind: 'compaction', reason: 'manual', state: 'skipped',
        text: 'Nothing to compact. The original context was kept.' },
    ]);
  });
  it('preserves the exact compaction summary and marks it discarded after a failed run', () => {
    const compacted = reduce([
      { type: 'compaction_end', reason: 'threshold', tokensBefore: 25000, success: true, aborted: false,
        summary: 'Keep P1 off nights.', keepMessages: 4 },
    ]);
    const failed = applyAssistantEvent(compacted, { type: 'response_end', stopReason: 'error', contextNote: 'Workspace discarded.' });
    expect(failed.activity?.[0]).toMatchObject({ summary: 'Keep P1 off nights.', keepMessages: 4, invalidated: true });
    expect(compacted.activity?.[0]).not.toHaveProperty('invalidated');
  });
  it('keeps completed exchanges and marks only the failed attempt omitted', () => {
    const message = reduce([
      { type: 'delta', text: 'Checking.' },
      { type: 'response_end', stopReason: 'tool_use' },
      { type: 'tool', activity: { name: 'read', arguments: '{}', result: 'File contents', ok: true } },
      { type: 'delta', text: 'Partial attempt' },
      { type: 'response_end', stopReason: 'error' },
      { type: 'provider_retry', message: 'Retrying.' },
      { type: 'delta', text: 'Recovered answer' },
      { type: 'response_end', stopReason: 'stop' },
      { type: 'done' },
    ]);
    expect(message.activity?.filter(entry => entry.kind === 'response')).toEqual([
      { kind: 'response', text: 'Checking.', context: 'complete' },
      { kind: 'response', text: 'Partial attempt', context: 'omitted' },
      { kind: 'response', text: 'Recovered answer', context: 'complete' },
    ]);
    expect(message.activity?.find(entry => entry.kind === 'tool')).toMatchObject({ result: 'File contents' });
  });

  it('shows the exact workspace interruption note separately from failed output', () => {
    const message = reduce([
      { type: 'delta', text: 'Partial' },
      { type: 'response_end', stopReason: 'aborted', contextNote: '[App event] Workspace discarded.' },
      { type: 'stopped' },
    ]);
    expect(message.activity).toEqual([
      { kind: 'response', text: 'Partial', context: 'omitted' },
      { kind: 'notice', text: 'Sent in future model context: [App event] Workspace discarded.' },
    ]);
  });
  it.each([true, false])('replaces running compaction with its outcome: success=%s', success => {
    const message = reduce([
      { type: 'compaction_start', reason: 'threshold', tokensBefore: 25000 },
      { type: 'compaction_end', reason: 'threshold', tokensBefore: 25000, success, aborted: false },
      { type: 'delta', text: 'Continue.' },
    ]);
    expect(message.activity).toEqual([
      { kind: 'compaction', reason: 'threshold', state: success ? 'completed' : 'failed',
        text: success ? 'The conversation was summarized.' : 'Summarization failed. The original context was kept.' },
      { kind: 'response', text: 'Continue.' },
    ]);
  });

  it('marks a compaction interrupted if its stream terminates', () => {
    const message = reduce([
      { type: 'compaction_start', reason: 'overflow', tokensBefore: 25000 },
      { type: 'stopped' },
    ]);
    expect(message.activity?.[0]).toMatchObject({ kind: 'compaction', state: 'interrupted' });
  });

  it('uses secure random bytes for message IDs when randomUUID is unavailable', () => {
    const getRandomValues = vi.fn((bytes: Uint8Array) => {
      bytes.set(Array.from({ length: 16 }, (_, index) => index));
      return bytes;
    });
    vi.stubGlobal('crypto', { getRandomValues });
    try {
      expect(messageId()).toBe('00010203-0405-4607-8809-0a0b0c0d0e0f');
      expect(getRandomValues).toHaveBeenCalledOnce();
    } finally {
      vi.unstubAllGlobals();
    }
  });

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

  it('keeps the failure reason when an answer already has text', () => {
    const reason = 'The provider returned HTTP 525. Error ID: example.';
    const message = reduce([{ type: 'delta', text: 'Partial answer.' }, { type: 'error', message: reason }]);
    expect(message).toMatchObject({ content: 'Partial answer.', status: 'failed', failureReason: reason });
  });

  it('diffs each preview against the previous working copy', () => {
    const events: AssistantEvent[] = [];
    const working = { current: null as string | null };
    events.push(toAssistantEvent({ type: 'schedule_change', scheduleYaml: 'v1' }, working, { current: 'v0' })!);
    events.push(toAssistantEvent({ type: 'schedule_change', scheduleYaml: 'v2' }, working, { current: 'v0' })!);

    expect(events).toEqual([
      { type: 'schedule_change', before: 'v0', after: 'v1' },
      { type: 'schedule_change', before: 'v1', after: 'v2' },
    ]);
    expect(working.current).toBe('v2');
  });

  it('marks an answer cut off by the output limit without changing its text', () => {
    const message = reduce([{ type: 'delta', text: 'The first half' }, { type: 'truncated' }]);

    expect(message).toEqual(expect.objectContaining({ content: 'The first half', truncated: true }));
  });

  it('stops a response without adding answer text', () => {
    const message = reduce([
      { type: 'delta', text: 'Partial.' },
      { type: 'tool_start', activity: { toolCallId: 'a', name: 'bash', arguments: 'sleep 60' } },
      { type: 'stopped' },
    ]);

    expect(message.status).toBe('stopped');
    expect(message.content).toBe('Partial.');
    expect(message.activity?.at(-1)).toEqual(expect.objectContaining({ state: 'interrupted' }));
  });
});
