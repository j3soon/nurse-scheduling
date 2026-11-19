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
import { holdWebLock, installMockWebLocks } from '@/test/mockWebLocks';
import { CURRENT_APP_VERSION } from '@/utils/version';
import { AI_HISTORY_LOCK_NAME, ChatHistoryLockUnavailableError, AI_HISTORY_STORAGE_KEY, HISTORY_RETENTION_MS, chatKey, clearChatHistory, forgetChat, pruneChatHistory, readChatHistory, readChatHistoryGeneration, saveChatHistory } from './chatHistory';
import { type StoredChatConversation } from './chatConversation';
import { applyModelInput, type ChatMessage } from './chatTranscript';

const conversation = (sessionId = 'one', endpoint = '/ai'): StoredChatConversation => ({
  sessionId, endpoint, lastActivityAt: Date.now(), expiresAt: Date.now() + 30 * 86400_000,
  retentionSeconds: 30 * 86400, syncedScheduleSpec: 'description: Ward A',
  messages: [{ id: 'question', role: 'user', content: 'Review Ward A' }],
});

beforeEach(installMockWebLocks);
afterEach(() => { localStorage.clear(); vi.useRealTimers(); vi.restoreAllMocks(); });

describe('recent chat storage', () => {
  it('saves long chats that repeatedly use one large unchanged Schedule Spec', async () => {
    const yaml = `# ${'a'.repeat(100_000)}\npeople: []\n`;
    let messages: ChatMessage[] = [];
    for (let index = 0; index < 55; index += 1) {
      const turn = { questionId: `question-${index}`, assistantId: `assistant-${index}` };
      messages.push({ id: turn.questionId, role: 'user', content: `Question ${index}` },
        { id: turn.assistantId, role: 'assistant', content: `Answer ${index}` });
      messages = applyModelInput(messages, { system: 'Policy', scheduleSpecYaml: yaml,
        messages: [{ kind: 'question', content: `Question ${index}` }] }, turn);
    }
    await saveChatHistory({ ...conversation(), syncedScheduleSpec: yaml, messages }, true);
    const saved = readChatHistory()[0].conversation;
    expect(saved.messages.at(-1)?.content).toBe('Answer 54');
    expect(saved.messages.filter(message => message.source === 'schedule')).toHaveLength(1);
    expect(saved.messages.find(message => message.source === 'schedule')?.content).toBe(yaml);
  });

  it('keeps sessions distinct by endpoint and sorts by actual activity', async () => {
    vi.useFakeTimers();
    const first = conversation();
    await saveChatHistory({ ...first, lastActivityAt: Date.now() - 1000 }, true);
    await saveChatHistory(conversation('two'), true);
    await saveChatHistory(conversation('one', 'https://example.com/ai'), true);
    expect(readChatHistory().map(entry => chatKey(entry.conversation))).toEqual([
      '/ai\ntwo', 'https://example.com/ai\none', '/ai\none',
    ]);
    expect(readChatHistory()[2].conversation.syncedScheduleSpec).toBe('description: Ward A');
  });

  it('expires seven days after activity without renewing on snapshot saves or reads', async () => {
    vi.useFakeTimers();
    const chat = conversation();
    await saveChatHistory(chat, true);
    vi.advanceTimersByTime(HISTORY_RETENTION_MS - 1);
    await saveChatHistory({ ...chat, messages: [] });
    expect(readChatHistory()).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(await pruneChatHistory()).toEqual([]);
    expect(localStorage.getItem(AI_HISTORY_STORAGE_KEY)).toBeNull();
    await saveChatHistory({ ...chat, lastActivityAt: Date.now() });
    expect(readChatHistory()).toEqual([]);
  });

  it('extends retention when there is new chat activity', async () => {
    vi.useFakeTimers();
    const chat = conversation();
    await saveChatHistory(chat, true);
    vi.advanceTimersByTime(HISTORY_RETENTION_MS - 1);
    await saveChatHistory({ ...chat, lastActivityAt: Date.now() });
    vi.advanceTimersByTime(2);
    expect(readChatHistory()).toHaveLength(1);
  });

  it('serializes simultaneous first saves without losing either chat', async () => {
    const release = await holdWebLock(AI_HISTORY_LOCK_NAME);
    const first = saveChatHistory(conversation('one'), true);
    const second = saveChatHistory(conversation('two'), true);
    expect(readChatHistory()).toEqual([]);
    await release();
    await Promise.all([first, second]);
    expect(readChatHistory().map(entry => entry.conversation.sessionId)).toEqual(['one', 'two']);
  });

  it.each([false, true])('serializes cleanup and a first save with cleanup first: %s', async cleanupFirst => {
    const release = await holdWebLock(AI_HISTORY_LOCK_NAME);
    const operations = cleanupFirst
      ? [pruneChatHistory(), saveChatHistory(conversation(), true)]
      : [saveChatHistory(conversation(), true), pruneChatHistory()];
    await release();
    await Promise.all(operations);
    expect(readChatHistory()).toHaveLength(1);
  });

  it.each(['remove', 'clear'])('does not recreate a chat when a queued save follows %s', async action => {
    const chat = conversation();
    await saveChatHistory(chat, true);
    const release = await holdWebLock(AI_HISTORY_LOCK_NAME);
    const earlierSave = saveChatHistory({ ...chat, messages: [] });
    const removal = action === 'remove' ? forgetChat(chatKey(chat)) : clearChatHistory();
    const laterSave = saveChatHistory(chat);
    await release();
    await Promise.all([earlierSave, removal]);
    expect(await laterSave).toBe(action === 'clear' ? 'cleared' : 'missing');
    expect(readChatHistory()).toEqual([]);
  });

  it('cancels a save waiting for the lock without writing its snapshot', async () => {
    const release = await holdWebLock(AI_HISTORY_LOCK_NAME);
    const controller = new AbortController();
    const pending = saveChatHistory(conversation(), true, controller.signal);
    const rejected = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    controller.abort();
    await rejected;
    await release();
    expect(readChatHistory()).toEqual([]);
  });

  it('keeps the existing history readable when browser locking is unavailable', async () => {
    await saveChatHistory(conversation(), true);
    const previous = localStorage.getItem(AI_HISTORY_STORAGE_KEY);
    Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined });
    for (const operation of [
      () => saveChatHistory(conversation('two'), true),
      () => forgetChat(chatKey(conversation())),
      () => clearChatHistory(),
      () => pruneChatHistory(),
    ]) {
      await expect(operation()).rejects.toBeInstanceOf(ChatHistoryLockUnavailableError);
      expect(localStorage.getItem(AI_HISTORY_STORAGE_KEY)).toBe(previous);
    }
    expect(readChatHistory()).toHaveLength(1);
  });

  it('forgets individual sessions and never recreates them from a later tab save', async () => {
    const chat = conversation();
    await saveChatHistory(chat, true);
    await saveChatHistory(conversation('two'), true);
    const release = await holdWebLock(AI_HISTORY_LOCK_NAME);
    const removed = forgetChat(chatKey(chat));
    const recovered = saveChatHistory({ ...chat, lastActivityAt: Date.now() }, true);
    const newChat = conversation('one', 'https://example.com/ai');
    const created = saveChatHistory(newChat, true);
    await release();
    await removed;
    expect(await recovered).toBe('missing');
    expect(await created).toBe('saved');
    expect(await saveChatHistory(chat)).toBe('missing');
    expect(new Set(readChatHistory().map(entry => chatKey(entry.conversation)))).toEqual(new Set([chatKey(newChat), '/ai\ntwo']));
    await clearChatHistory();
    await saveChatHistory(conversation('two'));
    expect(JSON.parse(localStorage.getItem(AI_HISTORY_STORAGE_KEY)!)).toEqual({
      appVersion: CURRENT_APP_VERSION, entries: [], clearGeneration: readChatHistoryGeneration(),
    });
  });

  it.each([undefined, 2])('rejects an older cursor (%s) with the same activity time', async sessionEventId => {
    const chat = conversation();
    const latest = { ...chat, sessionEventId: 3 };
    await saveChatHistory(latest, true);
    expect(await saveChatHistory({ ...chat, sessionEventId, messages: [] })).toBe('newer');
    expect(readChatHistory()[0].conversation).toEqual(latest);
    const updated = { ...latest, messages: [...latest.messages, { id: 'followup', role: 'user' as const, content: 'Follow-up' }] };
    expect(await saveChatHistory(updated)).toBe('saved');
    expect(readChatHistory()[0].conversation).toEqual(updated);
  });

  it('ignores corrupt entries while preserving valid sessions', async () => {
    localStorage.setItem(AI_HISTORY_STORAGE_KEY, '{');
    expect(readChatHistory()).toEqual([]);
    localStorage.setItem(AI_HISTORY_STORAGE_KEY, JSON.stringify({ appVersion: CURRENT_APP_VERSION, entries: [
      { conversation: conversation(), lastActivityAt: Date.now() },
      null, { conversation: {}, lastActivityAt: Date.now() },
      { conversation: conversation('bad'), lastActivityAt: 'yesterday' },
    ] }));
    expect(readChatHistory()).toHaveLength(1);
  });

  it('records the saving appVersion on writes and expiration cleanup', async () => {
    vi.useFakeTimers();
    await saveChatHistory({ ...conversation('old'), lastActivityAt: Date.now() - HISTORY_RETENTION_MS + 1 }, true);
    await saveChatHistory(conversation('recent'), true);
    const stored = JSON.parse(localStorage.getItem(AI_HISTORY_STORAGE_KEY)!);
    expect(stored.appVersion).toBe(CURRENT_APP_VERSION);
    expect(stored).not.toHaveProperty('version');

    // A different app release can read the same supported storage shape.
    stored.appVersion = 'v0.0.1';
    localStorage.setItem(AI_HISTORY_STORAGE_KEY, JSON.stringify(stored));
    expect(readChatHistory()).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect((await pruneChatHistory()).map(entry => entry.conversation.sessionId)).toEqual(['recent']);
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

  it('reports storage write failures to the caller', async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('Full', 'QuotaExceededError'); });
    await expect(saveChatHistory(conversation(), true)).rejects.toThrow('Full');
  });

  it('rejects a recovered first save queued after Clear history', async () => {
    const pending = conversation();
    const release = await holdWebLock(AI_HISTORY_LOCK_NAME);
    const cleared = clearChatHistory();
    const recovered = saveChatHistory(pending, true);
    await release();
    await cleared;
    expect(await recovered).toBe('cleared');
    expect(readChatHistory()).toEqual([]);
  });

  it('preserves the clear marker through new saves, removal, and expiry cleanup', async () => {
    vi.useFakeTimers();
    const old = conversation('old');
    await clearChatHistory();
    const historyGeneration = readChatHistoryGeneration();
    expect(historyGeneration).not.toBe('');
    const fresh = { ...conversation('fresh'), historyGeneration };
    expect(await saveChatHistory(fresh, true)).toBe('saved');
    await forgetChat(chatKey(fresh));
    expect(readChatHistoryGeneration()).toBe(historyGeneration);
    expect(await saveChatHistory(old, true)).toBe('cleared');
    expect(await saveChatHistory(fresh, true)).toBe('missing');
    await saveChatHistory({ ...conversation('until-expiry'), historyGeneration }, true);
    vi.advanceTimersByTime(HISTORY_RETENTION_MS);
    await pruneChatHistory();
    expect(readChatHistoryGeneration()).toBe(historyGeneration);
    expect(readChatHistory()).toEqual([]);
    expect(await saveChatHistory({ ...fresh, lastActivityAt: Date.now() }, true)).toBe('missing');
    expect(await saveChatHistory({ ...old, lastActivityAt: Date.now() }, true)).toBe('cleared');
  });

  it('does not advance the boundary or discard entries when Clear cannot be saved', async () => {
    const chat = conversation();
    await saveChatHistory(chat, true);
    const previous = localStorage.getItem(AI_HISTORY_STORAGE_KEY);
    const write = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Full', 'QuotaExceededError');
    });
    await expect(clearChatHistory()).rejects.toThrow('Full');
    expect(localStorage.getItem(AI_HISTORY_STORAGE_KEY)).toBe(previous);
    write.mockRestore();
    expect(await saveChatHistory(chat)).toBe('saved');
  });

  it('starts a distinct boundary for every Clear, including an empty list', async () => {
    await clearChatHistory();
    const first = readChatHistoryGeneration();
    const pending = { ...conversation(), historyGeneration: first };
    await clearChatHistory();
    expect(readChatHistoryGeneration()).not.toBe(first);
    expect(await saveChatHistory(pending, true)).toBe('cleared');
    const fresh = { ...conversation('fresh'), historyGeneration: readChatHistoryGeneration() };
    expect(await saveChatHistory(fresh, true)).toBe('saved');
    expect(readChatHistory().map(entry => entry.conversation.sessionId)).toEqual(['fresh']);
  });
});
