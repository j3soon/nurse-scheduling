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

// This code is mostly AI generated.

import { CURRENT_APP_VERSION } from '@/utils/version';
import { HISTORY_RETENTION_MS, parseStoredConversation, type StoredChatConversation } from './chatConversation';

export const AI_HISTORY_STORAGE_KEY = 'nurse-scheduling-ai-history';
export const AI_HISTORY_LOCK_NAME = AI_HISTORY_STORAGE_KEY;
export const AI_HISTORY_CHANGED = 'ai-chat-history-changed';
export { HISTORY_RETENTION_MS } from './chatConversation';

export class ChatHistoryLockUnavailableError extends Error {
  constructor() {
    super('Recent chats cannot be saved or removed in this browser. The open chat remains available in this tab.');
    this.name = 'ChatHistoryLockUnavailableError';
  }
}

export type HistorySaveResult = 'saved' | 'missing' | 'expired' | 'newer' | 'cleared';

export interface RecentChat {
  conversation: StoredChatConversation;
  lastActivityAt: number;
}

export function chatKey(chat: Pick<StoredChatConversation, 'endpoint' | 'sessionId'>): string {
  return `${chat.endpoint}\n${chat.sessionId}`;
}

export function chatTitle(chat: StoredChatConversation): string {
  return chat.messages.find(message => message.role === 'user' && !message.source)?.content.trim().slice(0, 80) || 'New chat';
}

/** Keep the clear marker in the same record so clearing is one atomic storage write. */
export function readChatHistoryGeneration(): string {
  const raw = localStorage.getItem(AI_HISTORY_STORAGE_KEY);
  if (!raw) return '';
  const stored = JSON.parse(raw) as { clearGeneration?: unknown } | null;
  const generation = stored?.clearGeneration ?? '';
  if (typeof generation !== 'string') throw new Error('The saved chat history has an invalid clear marker.');
  return generation;
}

function writeHistory(entries: RecentChat[], clearGeneration = readChatHistoryGeneration()): boolean {
  const next = entries.length || clearGeneration
    ? JSON.stringify({ appVersion: CURRENT_APP_VERSION, entries, ...(clearGeneration ? { clearGeneration } : {}) }) : null;
  if (localStorage.getItem(AI_HISTORY_STORAGE_KEY) === next) return false;
  if (next) localStorage.setItem(AI_HISTORY_STORAGE_KEY, next);
  else localStorage.removeItem(AI_HISTORY_STORAGE_KEY);
  return true;
}

async function mutateHistory<T>(change: () => { result: T; changed: boolean }, signal?: AbortSignal): Promise<T> {
  if (!navigator.locks) throw new ChatHistoryLockUnavailableError();
  const { result, changed } = await navigator.locks.request(AI_HISTORY_LOCK_NAME, { mode: 'exclusive', signal }, change);
  if (changed) window.dispatchEvent(new Event(AI_HISTORY_CHANGED));
  return result;
}

/** Expiration is based on chat activity, never on viewing or saving a snapshot. */
export function readChatHistory(now?: number): RecentChat[] {
  const raw = localStorage.getItem(AI_HISTORY_STORAGE_KEY);
  return parseChatHistory(raw, now ?? Date.now());
}

function parseChatHistory(raw: string | null, now: number): RecentChat[] {
  if (!raw) return [];
  let stored: { appVersion?: string; entries?: unknown[]; clearGeneration?: unknown };
  try { stored = JSON.parse(raw); } catch { return []; }
  if (typeof stored?.appVersion !== 'string' || !stored.appVersion.trim() || !Array.isArray(stored.entries)) return [];
  if (stored.clearGeneration !== undefined && typeof stored.clearGeneration !== 'string') return [];
  const seen = new Set<string>();
  const entries: RecentChat[] = [];
  for (const entry of stored.entries) {
    if (typeof entry !== 'object' || entry === null) continue;
    const candidate = entry as Partial<RecentChat>;
    const conversation = parseStoredConversation(candidate.conversation);
    const activity = candidate.lastActivityAt;
    if (!conversation || typeof activity !== 'number' || !Number.isFinite(activity)
      || (conversation.historyGeneration ?? '') !== (stored.clearGeneration ?? '')
      || activity > now || activity + HISTORY_RETENTION_MS <= now || seen.has(chatKey(conversation))) continue;
    seen.add(chatKey(conversation));
    entries.push({ conversation, lastActivityAt: activity });
  }
  return entries.sort((a, b) => b.lastActivityAt - a.lastActivityAt);
}

export function saveChatHistory(conversation: StoredChatConversation, create = false, signal?: AbortSignal): Promise<HistorySaveResult> {
  return mutateHistory<HistorySaveResult>(() => {
    if ((conversation.historyGeneration ?? '') !== readChatHistoryGeneration()) return { result: 'cleared', changed: false };
    const entries = readChatHistory();
    const index = entries.findIndex(entry => chatKey(entry.conversation) === chatKey(conversation));
    // Only the first save may create a record. Later saves must respect removal.
    if (index < 0 && !create) return { result: 'missing', changed: false };
    const lastActivityAt = conversation.lastActivityAt ?? Date.now();
    if (lastActivityAt + HISTORY_RETENTION_MS <= Date.now()) return { result: 'expired', changed: false };
    if (index >= 0 && entries[index].lastActivityAt > lastActivityAt) return { result: 'newer', changed: false };
    const entry = { conversation, lastActivityAt };
    if (index < 0) entries.push(entry);
    else entries[index] = entry;
    return { result: 'saved', changed: writeHistory(entries) };
  }, signal);
}

export function forgetChat(key: string): Promise<void> {
  return mutateHistory(() => ({ result: undefined, changed: writeHistory(readChatHistory().filter(entry => chatKey(entry.conversation) !== key)) }));
}

export function clearChatHistory(): Promise<void> {
  return mutateHistory(() => {
    const clearGeneration = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('');
    return { result: undefined, changed: writeHistory([], clearGeneration) };
  });
}

export function pruneChatHistory(): Promise<RecentChat[]> {
  return mutateHistory(() => {
    const entries = readChatHistory();
    return { result: entries, changed: writeHistory(entries) };
  });
}
