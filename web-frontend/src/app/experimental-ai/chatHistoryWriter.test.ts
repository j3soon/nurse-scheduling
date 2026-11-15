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

import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { waitFor } from '@testing-library/react';
import { holdWebLock, installMockWebLocks } from '@/test/mockWebLocks';
import { AI_HISTORY_LOCK_NAME, AI_HISTORY_STORAGE_KEY, clearChatHistory, readChatHistory, readChatHistoryGeneration } from './chatHistory';
import { ChatHistoryWriter } from './chatHistoryWriter';
import { AI_CONVERSATION_STORAGE_KEY, type StoredChatConversation } from './chatConversation';

const snapshot = (content: string): StoredChatConversation => ({
  sessionId: 'session', endpoint: '/ai', lastActivityAt: Date.now(),
  expiresAt: Date.now() + 60000, retentionSeconds: 3600, syncedScheduleSpec: '',
  messages: [{ id: 'question', role: 'user', content }],
});

beforeEach(installMockWebLocks);
afterEach(() => { localStorage.clear(); sessionStorage.clear(); vi.restoreAllMocks(); });

describe('queued chat history saves', () => {
  it('coalesces streaming updates waiting behind the first save', async () => {
    const release = await holdWebLock(AI_HISTORY_LOCK_NAME);
    const write = vi.spyOn(Storage.prototype, 'setItem');
    const writer = new ChatHistoryWriter(true, vi.fn());
    writer.save(snapshot('First'));
    writer.save(snapshot('Intermediate'));
    writer.save(snapshot('Latest'));
    await release();
    await waitFor(() => expect(readChatHistory()[0]?.conversation.messages[0].content).toBe('Latest'));
    expect(write.mock.calls.filter(([key]) => key === AI_HISTORY_STORAGE_KEY)).toHaveLength(2);
    expect(writer.needsCreation).toBe(false);
  });

  it('never uses creation permission again after another tab clears the first save', async () => {
    const release = await holdWebLock(AI_HISTORY_LOCK_NAME);
    const writer = new ChatHistoryWriter(true, vi.fn());
    writer.save(snapshot('First'));
    const cleared = clearChatHistory();
    writer.save(snapshot('Latest'));
    await release();
    await cleared;
    await waitFor(() => expect(writer.forgotten).toBe(true));
    writer.save(snapshot('Must stay forgotten'));
    expect(readChatHistory()).toEqual([]);
  });

  it('cancels a waiting first save before removal completes', async () => {
    const release = await holdWebLock(AI_HISTORY_LOCK_NAME);
    const writer = new ChatHistoryWriter(true, vi.fn());
    writer.save(snapshot('First'));
    writer.pause();
    const cleared = clearChatHistory();
    writer.save(snapshot('While clearing'));
    await release();
    await cleared;
    writer.forget();
    writer.resume();
    writer.save(snapshot('After clearing'));
    expect(readChatHistory()).toEqual([]);
    expect(writer.forgotten).toBe(true);
  });

  it('retries a failed first write only when another save is requested', async () => {
    const settled = vi.fn();
    const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Full', 'QuotaExceededError');
    });
    const writer = new ChatHistoryWriter(true, settled);
    writer.save(snapshot('First'));
    writer.save(snapshot('Latest'));
    await waitFor(() => expect(settled).toHaveBeenCalledWith(expect.objectContaining({ name: 'QuotaExceededError' })));
    expect(writer.needsCreation).toBe(true);
    expect(write).toHaveBeenCalledTimes(1);
    write.mockRestore();
    writer.save(snapshot('Retry'));
    await waitFor(() => expect(readChatHistory()[0]?.conversation.messages[0].content).toBe('Retry'));
    expect(writer.needsCreation).toBe(false);
  });

  it('resumes the latest snapshot when a pending removal fails', async () => {
    const release = await holdWebLock(AI_HISTORY_LOCK_NAME);
    const writer = new ChatHistoryWriter(true, vi.fn());
    writer.save(snapshot('First'));
    writer.pause();
    writer.save(snapshot('Latest'));
    writer.resume();
    await release();
    await waitFor(() => expect(readChatHistory()[0]?.conversation.messages[0].content).toBe('Latest'));
    expect(writer.forgotten).toBe(false);
  });

  it.each([true, false])('clears only its matching tab backup without subscribers (matching: %s)', matching => {
    const chat = snapshot('First');
    sessionStorage.setItem(AI_CONVERSATION_STORAGE_KEY, JSON.stringify({ ...chat, sessionId: matching ? chat.sessionId : 'other', historyPending: true }));
    const previous = sessionStorage.getItem(AI_CONVERSATION_STORAGE_KEY);
    const writer = new ChatHistoryWriter(true);
    writer.pause();
    writer.save(chat);
    writer.forget();
    expect(sessionStorage.getItem(AI_CONVERSATION_STORAGE_KEY)).toBe(matching ? null : previous);
  });

  it('clears a recovered tab backup when its generation is rejected without subscribers', async () => {
    const chat = { ...snapshot('Before clear'), historyGeneration: readChatHistoryGeneration() };
    sessionStorage.setItem(AI_CONVERSATION_STORAGE_KEY, JSON.stringify({ ...chat, historyPending: true }));
    await clearChatHistory();
    const writer = new ChatHistoryWriter(true);
    writer.save(chat);
    await waitFor(() => expect(writer.forgotten).toBe(true));
    expect(sessionStorage.getItem(AI_CONVERSATION_STORAGE_KEY)).toBeNull();
    expect(readChatHistory()).toEqual([]);
  });
});
