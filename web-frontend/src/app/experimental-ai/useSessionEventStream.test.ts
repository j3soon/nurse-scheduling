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
import { AiHttpError, streamSessionEvents } from './aiClient';
import type { SessionStreamOptions } from './sessionEvents';
import { useSessionEventStream } from './useSessionEventStream';

vi.mock('./aiClient', async importOriginal => ({
  ...await importOriginal<typeof import('./aiClient')>(),
  streamSessionEvents: vi.fn(),
}));
const stream = vi.mocked(streamSessionEvents);

afterEach(() => { vi.useRealTimers(); vi.resetAllMocks(); });

describe('session event connection', () => {
  it('reconnects with the cursor and revokes the previous reader, then cancels on reset', async () => {
    vi.useFakeTimers();
    const readers: { callbacks: SessionStreamOptions; signal: AbortSignal; end: () => void }[] = [];
    stream.mockImplementation((_id, callbacks, signal) => new Promise(resolve => {
      readers.push({ callbacks, signal, end: resolve });
    }));
    const onDelta = vi.fn();
    const { result } = renderHook(useSessionEventStream);
    act(() => result.current.connect('session', onDelta, null, '/ai', vi.fn()));
    readers[0].callbacks.onEventId?.(7);
    readers[0].end();
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(readers).toHaveLength(2);
    expect(readers[1].callbacks.lastEventId).toBe(7);
    readers[0].callbacks.onEvent({ type: 'delta', text: 'old reader' });
    readers[0].callbacks.onEventId?.(99);
    readers[1].callbacks.onEvent({ type: 'delta', text: 'current reader' });
    expect(onDelta).toHaveBeenCalledExactlyOnceWith({ type: 'delta', text: 'current reader' });
    expect(result.current.cursor.current).toBe(7);
    act(() => result.current.reset());
    expect(readers[1].signal.aborted).toBe(true);
    expect(result.current.cursor.current).toBe(0);
    readers[1].end();
    await act(() => vi.advanceTimersByTimeAsync(60000));
    expect(readers).toHaveLength(2);
  });

  it.each([401, 403, 404])('does not retry HTTP %i until explicitly reconnected', async status => {
    vi.useFakeTimers();
    stream.mockRejectedValueOnce(new AiHttpError('Unavailable', status))
      .mockImplementation(() => new Promise(() => {}));
    const onError = vi.fn();
    const { result, unmount } = renderHook(useSessionEventStream);
    act(() => result.current.connect('session', vi.fn(), 'old', '/ai', onError));
    await act(() => vi.advanceTimersByTimeAsync(60000));
    expect(stream).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(expect.any(AiHttpError), true);
    act(() => result.current.connect('session', vi.fn(), 'new', '/ai', onError));
    expect(stream.mock.calls[1][3]).toBe('new');
    const signal = stream.mock.calls[1][2];
    unmount();
    expect(signal.aborted).toBe(true);
  });
});
