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
import { CURRENT_APP_VERSION } from '@/utils/version';
import { AI_HISTORY_STORAGE_KEY, HISTORY_RETENTION_MS, chatKey, clearChatHistory, forgetChat, pruneChatHistory, readChatHistory, saveChatHistory } from './chatHistory';
import { type StoredChatConversation } from './chatConversation';

const conversation = (sessionId = 'one', endpoint = '/ai'): StoredChatConversation => ({
  sessionId, endpoint, lastActivityAt: Date.now(), expiresAt: Date.now() + 30 * 86400_000,
  retentionSeconds: 30 * 86400, syncedSchedule: 'description: Ward A',
  messages: [{ id: 'question', role: 'user', content: 'Review Ward A' }],
});

afterEach(() => { localStorage.clear(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe('recent chat storage', () => {
  it('keeps sessions distinct by endpoint and sorts by actual activity', () => {
    vi.useFakeTimers();
    const first = conversation();
    saveChatHistory({ ...first, lastActivityAt: Date.now() - 1000 }, true);
    saveChatHistory(conversation('two'), true);
    saveChatHistory(conversation('one', 'https://example.com/ai'), true);
    expect(readChatHistory().map(entry => chatKey(entry.conversation))).toEqual([
      '/ai\ntwo', 'https://example.com/ai\none', '/ai\none',
    ]);
    expect(readChatHistory()[2].conversation.syncedSchedule).toBe('description: Ward A');
  });

  it('expires seven days after activity without renewing on snapshot saves or reads', () => {
    vi.useFakeTimers();
    const chat = conversation();
    saveChatHistory(chat, true);
    vi.advanceTimersByTime(HISTORY_RETENTION_MS - 1);
    saveChatHistory({ ...chat, messages: [] });
    expect(readChatHistory()).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(pruneChatHistory()).toEqual([]);
    expect(localStorage.getItem(AI_HISTORY_STORAGE_KEY)).toBeNull();
    saveChatHistory({ ...chat, lastActivityAt: Date.now() });
    expect(readChatHistory()).toEqual([]);
  });

  it('extends retention when there is new chat activity', () => {
    vi.useFakeTimers();
    const chat = conversation();
    saveChatHistory(chat, true);
    vi.advanceTimersByTime(HISTORY_RETENTION_MS - 1);
    saveChatHistory({ ...chat, lastActivityAt: Date.now() });
    vi.advanceTimersByTime(2);
    expect(readChatHistory()).toHaveLength(1);
  });

  it('forgets individual sessions and never recreates them from a later tab save', () => {
    const chat = conversation();
    saveChatHistory(chat, true);
    saveChatHistory(conversation('two'), true);
    forgetChat(chatKey(chat));
    saveChatHistory(chat);
    expect(readChatHistory().map(entry => entry.conversation.sessionId)).toEqual(['two']);
    clearChatHistory();
    saveChatHistory(conversation('two'));
    expect(localStorage.getItem(AI_HISTORY_STORAGE_KEY)).toBeNull();
  });

  it('ignores corrupt entries while preserving valid sessions', () => {
    localStorage.setItem(AI_HISTORY_STORAGE_KEY, '{');
    expect(readChatHistory()).toEqual([]);
    localStorage.setItem(AI_HISTORY_STORAGE_KEY, JSON.stringify({ appVersion: CURRENT_APP_VERSION, entries: [
      { conversation: conversation(), lastActivityAt: Date.now() },
      null, { conversation: {}, lastActivityAt: Date.now() },
      { conversation: conversation('bad'), lastActivityAt: 'yesterday' },
    ] }));
    expect(readChatHistory()).toHaveLength(1);
  });

  it('records the saving appVersion on writes and expiration cleanup', () => {
    vi.useFakeTimers();
    saveChatHistory({ ...conversation('old'), lastActivityAt: Date.now() - HISTORY_RETENTION_MS + 1 }, true);
    saveChatHistory(conversation('recent'), true);
    const stored = JSON.parse(localStorage.getItem(AI_HISTORY_STORAGE_KEY)!);
    expect(stored.appVersion).toBe(CURRENT_APP_VERSION);
    expect(stored).not.toHaveProperty('version');

    // A different app release can read the same supported storage shape.
    stored.appVersion = 'v0.0.1';
    localStorage.setItem(AI_HISTORY_STORAGE_KEY, JSON.stringify(stored));
    expect(readChatHistory()).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(pruneChatHistory().map(entry => entry.conversation.sessionId)).toEqual(['recent']);
    const pruned = JSON.parse(localStorage.getItem(AI_HISTORY_STORAGE_KEY)!);
    expect(pruned.appVersion).toBe(CURRENT_APP_VERSION);
    expect(pruned).not.toHaveProperty('version');
  });

  it.each([undefined, null, 1, ''])('rejects invalid appVersion metadata: %s', appVersion => {
    localStorage.setItem(AI_HISTORY_STORAGE_KEY, JSON.stringify({ appVersion, entries: [
      { conversation: conversation(), lastActivityAt: Date.now() },
    ] }));
    expect(readChatHistory()).toEqual([]);
  });

  it('reports storage write failures to the caller', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Full', 'QuotaExceededError'); });
    expect(() => saveChatHistory(conversation(), true)).toThrow('Full');
  });
});
