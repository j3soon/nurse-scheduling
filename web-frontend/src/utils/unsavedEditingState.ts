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
  setTabSwitchWarningActive: (message?: string) => void;
  clearTabSwitchWarningActive: (message?: string) => void;
  hasTabSwitchWarningActive: () => boolean;
  // Undefined means the default unsaved edits warning.
  tabSwitchWarningMessage: () => string | undefined;
};

const UnsavedEditingStateContext = createContext<UnsavedEditingState | null>(null);

function createUnsavedEditingState(): UnsavedEditingState {
  // Keep one entry per registration so overlapping warnings cannot clear each other.
  // A null entry is an editor with unsaved edits.
  const warnings: (string | null)[] = [];

  return {
    setTabSwitchWarningActive: message => {
      warnings.push(message ?? null);
    },
    clearTabSwitchWarningActive: message => {
      const index = warnings.lastIndexOf(message ?? null);
      if (index !== -1) warnings.splice(index, 1);
    },
    hasTabSwitchWarningActive: () => warnings.length > 0,
    // Unsaved edits are lost on leaving, so their warning comes first.
    tabSwitchWarningMessage: () => (
      warnings.includes(null) ? undefined : warnings.at(-1) ?? undefined
    ),
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

export function useTabSwitchWarning(isActive: boolean, message?: string): void {
  const {
    setTabSwitchWarningActive: setActive,
    clearTabSwitchWarningActive: clearActive,
  } = useUnsavedEditingState();

  useEffect(() => {
    if (!isActive) return;

    setActive(message);

    return () => {
      clearActive(message);
    };
  }, [clearActive, isActive, message, setActive]);
}
