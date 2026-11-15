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

/** Model exclusive browser locks in component tests, including queued cancellation. */
export function installMockWebLocks(): void {
  interface Request {
    start: () => void;
    aborted: boolean;
  }
  const queues = new Map<string, Request[]>();
  const held = new Set<string>();
  const advance = (name: string) => {
    if (held.has(name)) return;
    const queue = queues.get(name);
    let next = queue?.shift();
    while (next?.aborted) next = queue?.shift();
    if (!next) return;
    held.add(name);
    void Promise.resolve().then(next.start);
  };
  const request = <T>(name: string, options: LockOptions | ((lock: Lock) => T | PromiseLike<T>),
    callback?: (lock: Lock) => T | PromiseLike<T>): Promise<T> => {
    const settings = typeof options === 'function' ? {} : options;
    const run = typeof options === 'function' ? options : callback!;
    return new Promise<T>((resolve, reject) => {
      const signal = settings.signal;
      if (signal?.aborted) { reject(signal.reason); return; }
      let started = false;
      const abort = () => {
        if (started) return;
        entry.aborted = true;
        reject(signal?.reason);
      };
      const entry: Request = {
        aborted: false,
        start: () => {
          signal?.removeEventListener('abort', abort);
          if (entry.aborted) {
            held.delete(name);
            advance(name);
            return;
          }
          started = true;
          void Promise.resolve().then(() => run({ name, mode: 'exclusive' } as Lock)).then(resolve, reject).finally(() => {
            held.delete(name);
            advance(name);
          });
        },
      };
      signal?.addEventListener('abort', abort, { once: true });
      const queue = queues.get(name) ?? [];
      queue.push(entry);
      queues.set(name, queue);
      advance(name);
    });
  };
  Object.defineProperty(navigator, 'locks', { configurable: true, value: { request } });
}

export async function holdWebLock(name: string): Promise<() => Promise<void>> {
  let release!: () => void;
  let acquired!: () => void;
  const ready = new Promise<void>(resolve => { acquired = resolve; });
  const held = navigator.locks.request(name, () => {
    acquired();
    return new Promise<void>(resolve => { release = resolve; });
  });
  await ready;
  return async () => { release(); await held; };
}
