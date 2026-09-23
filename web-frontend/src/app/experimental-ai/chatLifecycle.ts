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

import type { StreamCallbacks } from './aiClient';

type Kind = 'foreground' | 'background';
export interface Operation {
  readonly kind: Kind;
  readonly id: string;
}
interface ActiveOperation {
  token: Operation;
  phase: 'running' | 'stopping' | 'interrupted';
}
interface LifecycleState {
  foreground: ActiveOperation | null;
  background: ActiveOperation | null;
}
type Action =
  | { type: 'begin'; token: Operation; phase: ActiveOperation['phase'] }
  | { type: 'finish'; token: Operation }
  | { type: 'stop' | 'stopFailed'; tokens: Operation[] }
  | { type: 'reset' };

const EMPTY: LifecycleState = { foreground: null, background: null };

export function reduceLifecycle(state: LifecycleState, action: Action): LifecycleState {
  if (action.type === 'reset') return EMPTY;
  if (action.type === 'begin') {
    return { ...state, [action.token.kind]: { token: action.token, phase: action.phase } };
  }
  if (action.type === 'finish') {
    return state[action.token.kind]?.token === action.token ? { ...state, [action.token.kind]: null } : state;
  }
  let next = state;
  for (const token of action.tokens) {
    const active = next[token.kind];
    if (active?.token !== token || active.phase === 'interrupted') continue;
    next = { ...next, [token.kind]: { token, phase: action.type === 'stop' ? 'stopping' : 'running' } };
  }
  return next;
}

/** A single synchronous owner for async operation identity, observed by React. */
export class ChatLifecycle {
  private state = EMPTY;
  private generation = 0;
  private listeners = new Set<() => void>();

  getSnapshot = (): LifecycleState => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private dispatch(action: Action) {
    const next = reduceLifecycle(this.state, action);
    if (next === this.state) return;
    this.state = next;
    this.listeners.forEach(listener => listener());
  }

  begin(kind: Kind, id: string, phase: ActiveOperation['phase'] = 'running'): Operation {
    const current = this.state[kind];
    // Reconnection resumes the same operation, including a pending Stop request.
    if (current?.token.id === id) {
      if (current.phase === 'interrupted') this.dispatch({ type: 'begin', token: current.token, phase });
      return current.token;
    }
    const token = { kind, id };
    this.dispatch({ type: 'begin', token, phase });
    return token;
  }

  current(kind: Kind): Operation | undefined {
    return this.state[kind]?.token;
  }

  owns(token: Operation): boolean {
    return this.current(token.kind) === token;
  }

  finish(token: Operation | undefined) {
    if (token) this.dispatch({ type: 'finish', token });
  }

  stop(): Operation[] {
    const tokens = Object.values(this.state).flatMap(active => active ? [active.token] : []);
    this.dispatch({ type: 'stop', tokens });
    return tokens;
  }

  stopFailed(tokens: Operation[]) {
    this.dispatch({ type: 'stopFailed', tokens });
  }

  reset() {
    this.generation += 1;
    this.dispatch({ type: 'reset' });
  }

  capture(): () => boolean {
    const generation = this.generation;
    return () => generation === this.generation;
  }

  get busy(): boolean {
    return Object.values(this.state).some(active => active !== null && active.phase !== 'interrupted');
  }
}

/** Revoke every callback together when a connection or conversation is replaced. */
export function scopedCallbacks(callbacks: StreamCallbacks, owns: () => boolean): StreamCallbacks {
  return Object.fromEntries(Object.entries(callbacks).map(([name, value]) => [
    name,
    typeof value === 'function'
      ? (...args: unknown[]) => { if (owns()) return (value as (...args: unknown[]) => unknown)(...args); }
      : value,
  ])) as StreamCallbacks;
}
