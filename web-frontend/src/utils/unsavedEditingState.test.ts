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
import {
  hasTabSwitchWarningActive,
  useTabSwitchWarning,
} from '@/utils/unsavedEditingState';

describe('useTabSwitchWarning', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it('keeps the warning active until every active hook is cleaned up', () => {
    const first = renderHook(() => useTabSwitchWarning(true));
    const second = renderHook(() => useTabSwitchWarning(true));

    first.unmount();
    expect(hasTabSwitchWarningActive()).toBe(true);

    second.unmount();
    expect(hasTabSwitchWarningActive()).toBe(false);
  });

  it('does not decrement the count for inactive hooks', () => {
    const active = renderHook(() => useTabSwitchWarning(true));
    const inactive = renderHook(() => useTabSwitchWarning(false));

    inactive.unmount();
    expect(hasTabSwitchWarningActive()).toBe(true);

    active.unmount();
    expect(hasTabSwitchWarningActive()).toBe(false);
  });
});
