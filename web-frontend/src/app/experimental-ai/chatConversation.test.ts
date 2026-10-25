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

import { afterEach, describe, expect, it, vi } from 'vitest';
import { AI_CONVERSATION_STORAGE_KEY, readStoredConversation } from './chatConversation';

afterEach(() => { sessionStorage.clear(); vi.restoreAllMocks(); });
const conversation = () => ({
  sessionId: 'session', endpoint: '/ai', expiresAt: Date.now() + 60000, retentionSeconds: 3600,
  messages: [{ id: 'question', role: 'user', content: 'Question' },
    { id: 'answer', role: 'assistant', content: 'Partial answer', status: 'pending' }],
  syncedSchedule: 'schedule', proposalDiff: null, sessionEventId: 9,
});

describe('stored conversation compatibility', () => {
  it('restores the legacy pending request and retained trim warning without dropping transcript fields', () => {
    sessionStorage.setItem(AI_CONVERSATION_STORAGE_KEY, JSON.stringify({
      ...conversation(), trimmedHistoryCount: 3,
      pendingRequest: { messageId: 'request', question: 'Question', questionId: 'question',
        assistantId: 'answer', createdAt: 100, uploading: true },
    }));
    expect(readStoredConversation()).toMatchObject({
      sessionEventId: 9, trimmedHistoryCount: 3,
      messages: [{ id: 'question', request: { id: 'request', active: true, uploading: true } },
        { id: 'answer', content: 'Partial answer', status: 'pending' }],
    });
  });

  it.each(['completed', 'skipped'])('restores %s conversation summary activity after a reload', state => {
    const summary = { kind: 'compaction', state, reason: 'manual', text: 'Compaction status.' };
    sessionStorage.setItem(AI_CONVERSATION_STORAGE_KEY, JSON.stringify({
      ...conversation(), messages: [{ id: 'answer', role: 'assistant', content: 'Answer', activity: [summary] }],
    }));
    expect(readStoredConversation()?.messages[0].activity).toEqual([summary]);
  });

  it('rejects corrupt activity and pending request data', () => {
    for (const change of [
      { messages: [{ id: 'answer', role: 'assistant', content: '', activity: [{ kind: 'tool' }] }] },
      { messages: [{ id: 'answer', role: 'assistant', content: '', failureReason: 525 }] },
      { messages: [{ id: 'answer', role: 'assistant', content: '',
        activity: [{ kind: 'compaction', state: 'done', reason: 'threshold', text: 'Summarized.' }] }] },
      { pendingRequest: { messageId: 'request', question: 'Question', questionId: 'question',
        assistantId: 'answer', createdAt: 'invalid' } },
      { pendingRequest: { messageId: 'request', question: 'Question', questionId: 'question',
        assistantId: 'answer', createdAt: 100, uploading: true, pendingFiles: [1] } },
      { messages: [{ id: 'answer', role: 'assistant', content: '', unsentFiles: 'two.txt' }] },
      { sessionEventId: -1 },
      { appliedScheduleRuns: { run: 123 } },
      { appliedScheduleRuns: [] },
      { syncedBrowserSchedule: 123 },
    ]) {
      sessionStorage.setItem(AI_CONVERSATION_STORAGE_KEY, JSON.stringify({ ...conversation(), ...change }));
      expect(readStoredConversation()).toBeNull();
    }
  });

  it('keeps the page usable when storage access is denied', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Storage denied'); });
    expect(readStoredConversation()).toBeNull();
  });
});
