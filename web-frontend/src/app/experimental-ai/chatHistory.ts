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
export const AI_HISTORY_CHANGED = 'ai-chat-history-changed';
export { HISTORY_RETENTION_MS } from './chatConversation';

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

function writeHistory(entries: RecentChat[]): void {
  if (entries.length) localStorage.setItem(AI_HISTORY_STORAGE_KEY, JSON.stringify({ appVersion: CURRENT_APP_VERSION, entries }));
  else localStorage.removeItem(AI_HISTORY_STORAGE_KEY);
  window.dispatchEvent(new Event(AI_HISTORY_CHANGED));
}

/** Expiration is based on chat activity, never on viewing or saving a snapshot. */
export function readChatHistory(now = Date.now()): RecentChat[] {
  const raw = localStorage.getItem(AI_HISTORY_STORAGE_KEY);
  if (!raw) return [];
  let stored: { appVersion?: string; entries?: unknown[] };
  try { stored = JSON.parse(raw); } catch { return []; }
  if (typeof stored?.appVersion !== 'string' || !stored.appVersion.trim() || !Array.isArray(stored.entries)) return [];
  const seen = new Set<string>();
  const entries: RecentChat[] = [];
  for (const entry of stored.entries) {
    if (typeof entry !== 'object' || entry === null) continue;
    const candidate = entry as Partial<RecentChat>;
    const conversation = parseStoredConversation(candidate.conversation);
    const activity = candidate.lastActivityAt;
    if (!conversation || typeof activity !== 'number' || !Number.isFinite(activity)
      || activity > now || activity + HISTORY_RETENTION_MS <= now || seen.has(chatKey(conversation))) continue;
    seen.add(chatKey(conversation));
    entries.push({ conversation, lastActivityAt: activity });
  }
  return entries.sort((a, b) => b.lastActivityAt - a.lastActivityAt);
}

export function saveChatHistory(conversation: StoredChatConversation, create = false): void {
  const entries = readChatHistory();
  const index = entries.findIndex(entry => chatKey(entry.conversation) === chatKey(conversation));
  // A forgotten or expired chat must not reappear from an open tab's next save.
  if (index < 0 && !create) return;
  const lastActivityAt = conversation.lastActivityAt ?? Date.now();
  if (lastActivityAt + HISTORY_RETENTION_MS <= Date.now()) return;
  if (index >= 0 && entries[index].lastActivityAt > lastActivityAt) return;
  const entry = { conversation, lastActivityAt };
  if (index < 0) entries.push(entry);
  else entries[index] = entry;
  writeHistory(entries);
}

export function forgetChat(key: string): void {
  writeHistory(readChatHistory().filter(entry => chatKey(entry.conversation) !== key));
}

export function clearChatHistory(): void {
  writeHistory([]);
}

export function pruneChatHistory(): RecentChat[] {
  const entries = readChatHistory();
  // Do not dispatch a change while reading in a storage event handler.
  const raw = localStorage.getItem(AI_HISTORY_STORAGE_KEY);
  const next = entries.length ? JSON.stringify({ appVersion: CURRENT_APP_VERSION, entries }) : null;
  if (next !== raw) {
    if (next) localStorage.setItem(AI_HISTORY_STORAGE_KEY, next);
    else localStorage.removeItem(AI_HISTORY_STORAGE_KEY);
  }
  return entries;
}
