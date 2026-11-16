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

import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamSessionEvents } from './aiClient';
import type { SessionStreamOptions } from './sessionEvents';
import { useSessionEventStream } from './useSessionEventStream';

vi.mock('./aiClient', async importOriginal => ({
  ...await importOriginal<typeof import('./aiClient')>(), streamSessionEvents: vi.fn(),
}));
const stream = vi.mocked(streamSessionEvents);
afterEach(() => { vi.useRealTimers(); vi.resetAllMocks(); });

function setup() {
  vi.useFakeTimers();
  const readers: { callbacks: SessionStreamOptions; signal: AbortSignal; end: () => void }[] = [];
  stream.mockImplementation((_id, callbacks, signal) => new Promise(resolve => {
    readers.push({ callbacks, signal, end: resolve });
  }));
  const options = { sessionId: 'session', endpoint: '/ai', authToken: null as string | null,
    onEvent: vi.fn(), onEventId: vi.fn(), onDisconnect: vi.fn(), onError: vi.fn() };
  return { ...renderHook(useSessionEventStream), readers, options };
}

describe('session event connection ownership', () => {
  it('reconnects from the acknowledged cursor and revokes callbacks from the closed reader', async () => {
    const { result, readers, options } = setup();
    act(() => result.current.connect({ ...options, resetReplay: true }));
    readers[0].callbacks.onEventId?.(7);
    readers[0].end();
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(readers).toHaveLength(2);
    expect(readers[0].callbacks.reset).toBe(true);
    expect(readers[1].callbacks).toMatchObject({ lastEventId: 7, reset: false });
    readers[0].callbacks.onEvent({ type: 'delta', text: 'old' });
    readers[0].callbacks.onEventId?.(99);
    readers[1].callbacks.onEvent({ type: 'delta', text: 'current' });
    expect(options.onEvent).toHaveBeenCalledExactlyOnceWith({ type: 'delta', text: 'current' });
    expect(result.current.cursor.current).toBe(7);
    expect(options.onDisconnect).toHaveBeenCalledTimes(1);
  });

  it('keeps retry ownership during backoff and cancels it when credentials change or the page unmounts', async () => {
    const { result, readers, options, unmount } = setup();
    act(() => result.current.connect(options));
    readers[0].end();
    await act(() => vi.advanceTimersByTimeAsync(1000));
    readers[1].end();
    await act(() => vi.advanceTimersByTimeAsync(1999));
    expect(readers).toHaveLength(2);
    expect(result.current.connected('session', null, '/ai')).toBe(true);
    expect(result.current.connected('session', 'new', '/ai')).toBe(false);
    act(() => result.current.connect({ ...options, authToken: 'new' }));
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(readers).toHaveLength(3);
    expect(stream.mock.calls[2][3]).toBe('new');
    unmount();
    expect(readers[2].signal.aborted).toBe(true);
    readers[2].end();
    await act(() => vi.advanceTimersByTimeAsync(60000));
    expect(readers).toHaveLength(3);
  });

  it('clears cursor and pending retries on conversation reset', async () => {
    const { result, readers, options } = setup();
    act(() => result.current.connect(options));
    readers[0].callbacks.onEventId?.(8);
    readers[0].end();
    await act(() => vi.advanceTimersByTimeAsync(0));
    act(() => result.current.reset());
    expect(result.current.cursor.current).toBe(0);
    expect(result.current.connected()).toBe(false);
    await act(() => vi.advanceTimersByTimeAsync(60000));
    expect(readers).toHaveLength(1);
  });
});
