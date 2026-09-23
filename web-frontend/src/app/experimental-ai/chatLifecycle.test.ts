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

import { ChatLifecycle, scopedCallbacks } from './chatLifecycle';

describe('chat operation ownership', () => {
  it.each(['foreground', 'background'] as const)(
    'keeps the other stream busy when %s finishes first',
    first => {
      const lifecycle = new ChatLifecycle();
      const foreground = lifecycle.begin('foreground', 'request');
      const background = lifecycle.begin('background', 'optimizer-turn');
      const stopping = lifecycle.stop();
      const completed = first === 'foreground' ? foreground : background;
      const remaining = first === 'foreground' ? background : foreground;
      lifecycle.finish(completed);
      expect(lifecycle.busy).toBe(true);
      expect(lifecycle.getSnapshot()[remaining.kind]?.phase).toBe('stopping');
      lifecycle.finish(remaining);
      lifecycle.stopFailed(stopping);
      expect(lifecycle.busy).toBe(false);
    },
  );

  it('cannot release a newer conversation or undo its Stop with stale callbacks', () => {
    const lifecycle = new ChatLifecycle();
    const old = lifecycle.begin('foreground', 'same-message-id');
    const stop = lifecycle.stop();
    lifecycle.reset();
    const current = lifecycle.begin('foreground', 'same-message-id');
    lifecycle.stop();
    lifecycle.finish(old);
    lifecycle.stopFailed(stop);
    expect(lifecycle.owns(current)).toBe(true);
    expect(lifecycle.getSnapshot().foreground?.phase).toBe('stopping');
  });

  it('resumes an interrupted turn with one identity and preserves Stop across reconnects', () => {
    const lifecycle = new ChatLifecycle();
    const restored = lifecycle.begin('background', 'turn', 'interrupted');
    expect(lifecycle.busy).toBe(false);
    expect(lifecycle.begin('background', 'turn')).toBe(restored);
    expect(lifecycle.busy).toBe(true);
    lifecycle.stop();
    expect(lifecycle.begin('background', 'turn')).toBe(restored);
    expect(lifecycle.getSnapshot().background?.phase).toBe('stopping');
  });

  it('revokes output, proposals and cursors together when a stream loses ownership', () => {
    let owns = true;
    const handlers = { onDelta: vi.fn(), onProposal: vi.fn(), onEventId: vi.fn(), onDone: vi.fn() };
    const callbacks = scopedCallbacks(handlers, () => owns);
    callbacks.onDelta('accepted');
    owns = false;
    callbacks.onDelta('late');
    callbacks.onProposal?.('late proposal');
    callbacks.onEventId?.(8);
    callbacks.onDone?.('old');
    expect(handlers.onDelta).toHaveBeenCalledExactlyOnceWith('accepted');
    expect(handlers.onProposal).not.toHaveBeenCalled();
    expect(handlers.onEventId).not.toHaveBeenCalled();
    expect(handlers.onDone).not.toHaveBeenCalled();
  });
});
