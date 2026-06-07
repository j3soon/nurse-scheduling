/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2026 Johnson Sun
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
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

import { useEffect } from 'react';

const TAB_SWITCH_WARNING_KEY = 'nurse-scheduling-tab-switch-warning-active';

function getTabSwitchWarningCount(): number {
  if (typeof window === 'undefined') return 0;

  const count = parseInt(window.sessionStorage.getItem(TAB_SWITCH_WARNING_KEY) ?? '0', 10);
  return Number.isNaN(count) ? 0 : Math.max(0, count);
}

export function incrementTabSwitchWarningActive(): void {
  if (typeof window === 'undefined') return;

  window.sessionStorage.setItem(TAB_SWITCH_WARNING_KEY, String(getTabSwitchWarningCount() + 1));
}

export function decrementTabSwitchWarningActive(): void {
  if (typeof window === 'undefined') return;

  const count = getTabSwitchWarningCount();
  if (count <= 1) {
    window.sessionStorage.removeItem(TAB_SWITCH_WARNING_KEY);
  } else {
    window.sessionStorage.setItem(TAB_SWITCH_WARNING_KEY, String(count - 1));
  }
}

export function hasTabSwitchWarningActive(): boolean {
  return getTabSwitchWarningCount() > 0;
}

export function useTabSwitchWarning(isActive: boolean): void {
  useEffect(() => {
    if (!isActive) return;

    incrementTabSwitchWarningActive();

    return () => {
      decrementTabSwitchWarningActive();
    };
  }, [isActive]);
}

export function hasSaveAndLoadEditingWarningActive(): boolean {
  return hasTabSwitchWarningActive();
}
