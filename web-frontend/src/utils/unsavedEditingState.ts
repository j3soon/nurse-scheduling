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
'use client';

import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';

type UnsavedEditingState = {
  setTabSwitchWarningActive: () => void;
  clearTabSwitchWarningActive: () => void;
  hasTabSwitchWarningActive: () => boolean;
};

const UnsavedEditingStateContext = createContext<UnsavedEditingState | null>(null);

function createUnsavedEditingState(): UnsavedEditingState {
  // Current pages only open one editor at a time, but keep a count so future
  // overlapping warning registrations cannot clear each other.
  let tabSwitchWarningCount = 0;

  return {
    setTabSwitchWarningActive: () => {
      tabSwitchWarningCount += 1;
    },
    clearTabSwitchWarningActive: () => {
      tabSwitchWarningCount = Math.max(0, tabSwitchWarningCount - 1);
    },
    hasTabSwitchWarningActive: () => tabSwitchWarningCount > 0,
  };
}

export function UnsavedEditingStateProvider({ children }: { children: ReactNode }) {
  const [value] = useState(createUnsavedEditingState);

  return createElement(UnsavedEditingStateContext.Provider, { value }, children);
}

export function useUnsavedEditingState(): UnsavedEditingState {
  const value = useContext(UnsavedEditingStateContext);
  if (!value) {
    throw new Error('useUnsavedEditingState must be used within UnsavedEditingStateProvider');
  }

  return value;
}

export function useTabSwitchWarning(isActive: boolean): void {
  const {
    setTabSwitchWarningActive: setActive,
    clearTabSwitchWarningActive: clearActive,
  } = useUnsavedEditingState();

  useEffect(() => {
    if (!isActive) return;

    setActive();

    return () => {
      clearActive();
    };
  }, [clearActive, isActive, setActive]);
}
