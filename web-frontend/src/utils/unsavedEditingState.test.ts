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

import { renderHook } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import {
  UnsavedEditingStateProvider,
  useUnsavedEditingState,
  useTabSwitchWarning,
} from '@/utils/unsavedEditingState';

describe('useTabSwitchWarning', () => {
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(UnsavedEditingStateProvider, null, children);

  it('sets the warning while active and clears it on cleanup', () => {
    const active = renderHook(() => {
      useTabSwitchWarning(true);
      return useUnsavedEditingState();
    }, { wrapper });

    expect(active.result.current.hasTabSwitchWarningActive()).toBe(true);

    active.unmount();
    expect(active.result.current.hasTabSwitchWarningActive()).toBe(false);
  });

  it('clears the warning when rerendered inactive', () => {
    const { result, rerender } = renderHook(({ isActive }) => {
      useTabSwitchWarning(isActive);
      return useUnsavedEditingState();
    }, {
      initialProps: { isActive: true },
      wrapper,
    });

    expect(result.current.hasTabSwitchWarningActive()).toBe(true);

    rerender({ isActive: false });
    expect(result.current.hasTabSwitchWarningActive()).toBe(false);
  });

  it('keeps the warning active until all active hooks clean up', () => {
    const { result, rerender } = renderHook(({ firstActive, secondActive }) => {
      useTabSwitchWarning(firstActive);
      useTabSwitchWarning(secondActive);
      return useUnsavedEditingState();
    }, {
      initialProps: { firstActive: true, secondActive: true },
      wrapper,
    });

    rerender({ firstActive: false, secondActive: true });
    expect(result.current.hasTabSwitchWarningActive()).toBe(true);

    rerender({ firstActive: false, secondActive: false });
    expect(result.current.hasTabSwitchWarningActive()).toBe(false);
  });

  it('keeps provider warnings active until all provider registrations clear', () => {
    const { result } = renderHook(() => useUnsavedEditingState(), { wrapper });

    result.current.setTabSwitchWarningActive();
    result.current.setTabSwitchWarningActive();

    result.current.clearTabSwitchWarningActive();
    expect(result.current.hasTabSwitchWarningActive()).toBe(true);

    result.current.clearTabSwitchWarningActive();
    result.current.clearTabSwitchWarningActive();
    expect(result.current.hasTabSwitchWarningActive()).toBe(false);
  });
});
