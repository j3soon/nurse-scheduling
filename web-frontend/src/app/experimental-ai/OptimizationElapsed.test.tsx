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

import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import OptimizationElapsed from './OptimizationElapsed';

afterEach(() => { cleanup(); vi.useRealTimers(); });

it('ticks without progress events, distinguishes waiting, and restores elapsed time from the backend start', () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-10-30T00:00:20Z'));
  const { rerender, unmount } = render(<OptimizationElapsed createdAt="2026-10-30T00:00:00Z" />);
  expect(screen.getByText('Waiting: 20s')).toBeTruthy();
  act(() => { vi.advanceTimersByTime(2000); });
  expect(screen.getByText('Waiting: 22s')).toBeTruthy();
  rerender(<OptimizationElapsed createdAt="2026-10-30T00:00:00Z" startedAt="2026-10-30T00:00:10Z" />);
  expect(screen.getByText('Elapsed: 12s')).toBeTruthy();
  unmount();
  vi.setSystemTime(new Date('2026-10-30T00:01:33Z'));
  render(<OptimizationElapsed startedAt="2026-10-30T00:00:10Z" />);
  expect(screen.getByText('Elapsed: 1m 23s')).toBeTruthy();
});
