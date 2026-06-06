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

export function setTabSwitchWarningActive(isActive: boolean): void {
  if (typeof window === 'undefined') return;

  if (isActive) {
    window.sessionStorage.setItem(TAB_SWITCH_WARNING_KEY, 'true');
  } else {
    window.sessionStorage.removeItem(TAB_SWITCH_WARNING_KEY);
  }
}

export function hasTabSwitchWarningActive(): boolean {
  if (typeof window === 'undefined') return false;
  return window.sessionStorage.getItem(TAB_SWITCH_WARNING_KEY) === 'true';
}

export function useTabSwitchWarning(isActive: boolean): void {
  useEffect(() => {
    setTabSwitchWarningActive(isActive);

    return () => {
      setTabSwitchWarningActive(false);
    };
  }, [isActive]);
}

export function setSaveAndLoadEditingWarningActive(isActive: boolean): void {
  setTabSwitchWarningActive(isActive);
}

export function hasSaveAndLoadEditingWarningActive(): boolean {
  return hasTabSwitchWarningActive();
}
