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

import { AI_CONVERSATION_STORAGE_KEY, type StoredChatConversation } from './chatConversation';
import { chatKey, saveChatHistory } from './chatHistory';

type Listener = (error?: unknown) => void;
interface WriterCache { writers: Map<string, ChatHistoryWriter>; key: string }
const pendingWriters = new WeakMap<object, Map<string, ChatHistoryWriter>>();

/** A remounted page must reuse creation permission already queued in this tab. */
export function getChatHistoryWriter(key: string, create: boolean): ChatHistoryWriter {
  const owner = navigator.locks ?? navigator;
  let writers = pendingWriters.get(owner);
  if (!writers) {
    writers = new Map();
    pendingWriters.set(owner, writers);
  }
  return writers.get(key) ?? new ChatHistoryWriter(create, undefined, { writers, key });
}

/** Serialize one conversation's saves and retain only its latest waiting snapshot. */
export class ChatHistoryWriter {
  private pending: StoredChatConversation | null = null;
  private latest: StoredChatConversation | null = null;
  private running: AbortController | null = null;
  private paused = false;
  private removed = false;
  private readonly listeners = new Set<Listener>();

  constructor(private create: boolean, onSettled?: Listener, private readonly cache?: WriterCache) {
    if (onSettled) this.listeners.add(onSettled);
  }

  get needsCreation(): boolean { return this.create; }
  get forgotten(): boolean { return this.removed; }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  private notify(error?: unknown): void {
    for (const listener of this.listeners) listener(error);
  }

  private retain(): void { this.cache?.writers.set(this.cache.key, this); }

  private releaseIfIdle(): void {
    if (!this.running && !this.pending && !this.paused && this.cache?.writers.get(this.cache.key) === this) {
      this.cache.writers.delete(this.cache.key);
    }
  }

  private acknowledgeCreation(snapshot: StoredChatConversation): void {
    try {
      const raw = sessionStorage.getItem(AI_CONVERSATION_STORAGE_KEY);
      const stored = raw ? JSON.parse(raw) as StoredChatConversation : null;
      if (stored?.historyPending && chatKey(stored) === chatKey(snapshot)) {
        // The page may have unmounted. Preserve any newer transcript in its tab backup.
        sessionStorage.setItem(AI_CONVERSATION_STORAGE_KEY, JSON.stringify({ ...stored, historyPending: false }));
      }
    } catch {
      // A tab backup failure does not undo a successful shared-history write.
    }
  }

  save(snapshot: StoredChatConversation): void {
    if (this.removed) return;
    this.latest = snapshot;
    this.pending = snapshot;
    this.start();
  }

  pause(): void {
    this.paused = true;
    this.retain();
    this.running?.abort();
  }

  resume(): void {
    if (this.removed) return;
    this.paused = false;
    this.pending = this.latest;
    this.start();
    this.releaseIfIdle();
  }

  forget(): void {
    if (this.removed) return;
    this.removed = true;
    this.paused = false;
    this.create = false;
    this.pending = null;
    this.running?.abort();
    this.notify();
    this.releaseIfIdle();
  }

  private start(): void {
    if (this.running || this.paused || this.removed || !this.pending) return;
    const snapshot = this.pending;
    this.pending = null;
    const controller = new AbortController();
    this.running = controller;
    this.retain();
    void saveChatHistory(snapshot, this.create, controller.signal).then(result => {
      if (this.create && (result === 'saved' || result === 'newer')) this.acknowledgeCreation(snapshot);
      this.create = false;
      if (result === 'missing' || result === 'expired') {
        this.removed = true;
        this.pending = null;
      }
      this.notify();
    }, error => {
      if (controller.signal.aborted) return;
      // Retry on the next explicit save, rather than looping on unavailable storage.
      this.pending = null;
      this.notify(error);
    }).finally(() => {
      this.running = null;
      this.start();
      this.releaseIfIdle();
    });
  }
}
