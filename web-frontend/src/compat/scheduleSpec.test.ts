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

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { loadStateFromStorage, saveStateToStorage } from '@/hooks/schedulingStorage';
import { createDefaultHistoryState } from '@/hooks/schedulingHistory';
import { loadLegacyScheduleSpec } from './scheduleSpec';

beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

function oldHistory() {
  const history = createDefaultHistoryState();
  history.state.description = 'Saved requirements';
  saveStateToStorage(history);
  const raw = localStorage.getItem('nurse-scheduling-spec')!;
  localStorage.removeItem('nurse-scheduling-spec');
  localStorage.setItem('nurse-scheduling-data', raw);
  return raw;
}

describe('legacy Schedule Spec storage', () => {
  it('migrates the full history once and ignores later writes from older tabs', () => {
    const raw = oldHistory();
    expect(loadStateFromStorage().state.description).toBe('Saved requirements');
    expect(localStorage.getItem('nurse-scheduling-spec')).toBe(raw);
    expect(localStorage.getItem('nurse-scheduling-data')).toBeNull();
    localStorage.setItem('nurse-scheduling-data', '{}');
    expect(loadStateFromStorage().state.description).toBe('Saved requirements');
  });

  it("uses another current tab's save published during legacy decoding", () => {
    const raw = oldHistory();
    const newer = JSON.parse(raw);
    newer.state.description = 'Saved by another current tab';
    newer.history.push(newer.state);
    newer.currentHistoryIndex = newer.history.length - 1;
    const newerRaw = JSON.stringify(newer);
    const value = loadLegacyScheduleSpec(localStorage, 'nurse-scheduling-spec', stored => {
      if (stored === raw) localStorage.setItem('nurse-scheduling-spec', newerRaw);
      return JSON.parse(stored);
    });
    expect(value.state.description).toBe('Saved by another current tab');
    expect(localStorage.getItem('nurse-scheduling-spec')).toBe(newerRaw);
    expect(localStorage.getItem('nurse-scheduling-data')).toBe(raw);
  });

  it.each([false, true])("loads another tab's current save after the initial lookup (legacy removed: %s)", removed => {
    const raw = oldHistory();
    const newer = JSON.parse(raw);
    newer.state.description = 'Saved by another current tab';
    newer.history.push(newer.state);
    newer.currentHistoryIndex = newer.history.length - 1;
    const newerRaw = JSON.stringify(newer);
    const getItem = Storage.prototype.getItem;
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (this: Storage, key) {
      const stored = getItem.call(this, key);
      if (key === 'nurse-scheduling-data') {
        localStorage.setItem('nurse-scheduling-spec', newerRaw);
        if (removed) {
          localStorage.removeItem(key);
          return null;
        }
      }
      return stored;
    });
    const loaded = loadStateFromStorage();
    expect(loaded.state.description).toBe('Saved by another current tab');
    expect(loaded.history[loaded.currentHistoryIndex].description).toBe('Saved by another current tab');
    expect(localStorage.getItem('nurse-scheduling-spec')).toBe(newerRaw);
  });

  it('retains valid legacy content when the new write fails', () => {
    const raw = oldHistory();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota'); });
    expect(loadStateFromStorage().state.description).toBe('Saved requirements');
    expect(localStorage.getItem('nurse-scheduling-data')).toBe(raw);
    expect(localStorage.getItem('nurse-scheduling-spec')).toBeNull();
  });

  it('keeps malformed legacy content for recovery', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    localStorage.setItem('nurse-scheduling-data', '{invalid');
    loadStateFromStorage();
    expect(localStorage.getItem('nurse-scheduling-data')).toBe('{invalid');
    expect(localStorage.getItem('nurse-scheduling-spec')).toBeNull();
  });
});
