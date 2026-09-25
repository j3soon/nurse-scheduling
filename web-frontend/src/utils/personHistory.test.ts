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

import { truncateHistoryAfterUnusable, truncateHistoryAtUnknownEntries } from '@/utils/personHistory';

describe('personHistory', () => {
  it('keeps history without an unusable entry', () => {
    expect(truncateHistoryAfterUnusable(['D', 'N'], id => id === 'A')).toEqual(['D', 'N']);
    expect(truncateHistoryAfterUnusable([], id => id === 'A')).toEqual([]);
  });

  it('keeps only entries newer than the newest unusable entry', () => {
    expect(truncateHistoryAfterUnusable(['D', 'N', 'D', 'A'], id => id === 'D')).toEqual(['A']);
    expect(truncateHistoryAfterUnusable(['A', 'D', 'N', 'E'], id => id === 'D')).toEqual(['N', 'E']);
  });

  it('drops the whole history when the newest entry is unusable', () => {
    expect(truncateHistoryAfterUnusable(['D', 'N'], id => id === 'N')).toEqual([]);
  });

  it('repairs blank slots left by an earlier deletion', () => {
    expect(truncateHistoryAtUnknownEntries(['', 'N', '', 'A'])).toEqual(['A']);
    expect(truncateHistoryAtUnknownEntries(['D', 'N'])).toEqual(['D', 'N']);
  });
});
