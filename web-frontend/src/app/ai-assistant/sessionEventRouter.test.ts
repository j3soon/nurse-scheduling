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

  it('replays covered foreground output once after multiple resets', () => {
    const router = new SessionEventRouter();
    const background = vi.fn(), handle = vi.fn();
    const run = router.begin(handle, vi.fn(), vi.fn());
    const first = { type: 'session_reset' as const, reset };
    const second = { type: 'session_reset' as const, reset: { ...reset, runIds: ['accepted'] } };
    const review = { type: 'delta' as const, runId: 'review', text: 'Recovered review' };
    const answer = { type: 'delta' as const, runId: 'accepted', text: 'Recovered answer' };

    router.dispatch(first, background, () => true);
    router.dispatch(review, background, () => true);
    router.dispatch({ ...answer, text: 'Superseded answer' }, background, () => true);
    router.dispatch(second, background, () => true);
    router.dispatch(answer, background, () => true);
    router.acknowledge(run, 'accepted', vi.fn());

    expect(background.mock.calls).toEqual([[first], [second], [review]]);
    expect(handle.mock.calls).toEqual([[{ ...second, runId: 'accepted' }], [answer]]);
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

  it('flushes deferred background events when a foreground run finishes without acknowledgement', () => {
    const router = new SessionEventRouter();
    const background = vi.fn();
    const run = router.begin(vi.fn(), vi.fn(), vi.fn());
    router.dispatch({ type: 'run_start', runId: 'review', trigger: 'optimizer' }, background, () => true);
    router.dispatch({ type: 'delta', runId: 'review', text: 'Done.' }, background, () => true);
    router.dispatch({ type: 'done', runId: 'review' }, background, () => true);
    expect(background).not.toHaveBeenCalled();

    router.finish(run);

    expect(background).toHaveBeenCalledTimes(3);
    expect(background).toHaveBeenNthCalledWith(1, { type: 'run_start', runId: 'review', trigger: 'optimizer' });
    expect(background).toHaveBeenNthCalledWith(3, { type: 'done', runId: 'review' });
  });

  it.each([{ runIds: ['review'] }, { runIds: [] }])('only drops deferred output for runs the reset replaces, runIds=$runIds', ({ runIds }) => {
    const router = new SessionEventRouter();
    const background = vi.fn();
    const run = router.begin(vi.fn(), vi.fn(), vi.fn());
    const previous = { type: 'delta' as const, runId: 'review', text: 'previous' };
    const replay = { type: 'delta' as const, runId: 'review', text: 'replayed or new' };
    const sessionReset = { type: 'session_reset' as const, reset: { ...reset, runIds, terminalRunIds: [], activeRunId: 'review' } };
    router.dispatch(previous, background, () => true);
    router.dispatch(sessionReset, background, () => true);
    router.dispatch(replay, background, () => true);

    router.finish(run);

    expect(background.mock.calls).toEqual(runIds.length
      ? [[sessionReset], [replay]]
      : [[sessionReset], [previous], [replay]]);
  });
});
