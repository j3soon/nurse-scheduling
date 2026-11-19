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

import { SessionEventRouter } from './sessionEventRouter';

const reset = { runIds: ['review'], terminalRunIds: ['review'], activeRunId: null, incomplete: true, proposalDiff: null };

describe('session event routing after a pre-acknowledgement reset', () => {
  it('refreshes the reset after acknowledgement before rejecting an expired run', () => {
    const router = new SessionEventRouter();
    const reject = vi.fn(), refresh = vi.fn();
    const run = router.begin(vi.fn(), reject, refresh);
    router.dispatch({ type: 'session_reset', reset }, vi.fn(), () => true);
    router.acknowledge(run, 'accepted', vi.fn());
    expect(refresh).toHaveBeenCalledOnce();
    expect(reject).not.toHaveBeenCalled();
    router.dispatch({ type: 'session_reset', reset }, vi.fn(), () => true);
    expect(reject).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('expired') }));
  });

  it('keeps a fresh run whose start occurred after the earlier reset', () => {
    const router = new SessionEventRouter();
    const reject = vi.fn(), refresh = vi.fn(), handle = vi.fn();
    const run = router.begin(handle, reject, refresh);
    router.dispatch({ type: 'session_reset', reset }, vi.fn(), () => true);
    router.acknowledge(run, 'fresh', vi.fn());
    expect(refresh).toHaveBeenCalledOnce();
    router.dispatch({ type: 'session_reset', reset: { ...reset, runIds: ['fresh'], activeRunId: 'fresh' } }, vi.fn(), () => true);
    router.dispatch({ type: 'done', runId: 'fresh' }, vi.fn(), () => true);
    expect(reject).not.toHaveBeenCalled();
    expect(handle).toHaveBeenCalledWith({ type: 'done', runId: 'fresh' });
  });

  it('does not refresh an answer whose terminal event was already buffered', () => {
    const router = new SessionEventRouter();
    const refresh = vi.fn();
    const run = router.begin(vi.fn(), vi.fn(), refresh);
    router.dispatch({ type: 'session_reset', reset }, vi.fn(), () => true);
    router.dispatch({ type: 'done', runId: 'accepted' }, vi.fn(), () => true);
    router.acknowledge(run, 'accepted', vi.fn());
    expect(refresh).not.toHaveBeenCalled();
  });

  it('keeps covered output when a live terminal arrives after the snapshot', () => {
    const router = new SessionEventRouter();
    const reject = vi.fn(), handle = vi.fn();
    const run = router.begin(handle, reject, vi.fn());
    router.acknowledge(run, 'accepted', vi.fn());
    router.dispatch({ type: 'session_reset', reset: { ...reset, runIds: ['accepted'], terminalRunIds: [] } }, vi.fn(), () => true);
    expect(reject).not.toHaveBeenCalled();
    router.dispatch({ type: 'done', runId: 'accepted' }, vi.fn(), () => true);
    expect(handle).toHaveBeenCalledWith({ type: 'done', runId: 'accepted' });
  });
});
