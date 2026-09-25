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

// A person's history is right-anchored: the last entry is the day before the
// schedule starts, and the solver only matches suffixes of it against
// succession patterns. An entry the schedule can no longer explain therefore
// makes every older entry unusable as well, because no suffix reaching them
// avoids it. Dropping the entry instead of blanking it would shift the
// remaining days, and keeping a blank would emit a history value the backend
// rejects, so the usable suffix is what survives.

export const UNKNOWN_HISTORY_ENTRY = '';

export function truncateHistoryAfterUnusable(
  history: string[],
  isUnusable: (entry: string) => boolean
): string[] {
  for (let index = history.length - 1; index >= 0; index -= 1) {
    if (isUnusable(history[index])) {
      return history.slice(index + 1);
    }
  }
  return history;
}

export function truncateHistoryAtUnknownEntries(history: string[]): string[] {
  return truncateHistoryAfterUnusable(history, entry => entry === UNKNOWN_HISTORY_ENTRY);
}
