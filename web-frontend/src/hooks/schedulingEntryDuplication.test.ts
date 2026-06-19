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

import { duplicateEntryWithCopiedDescription } from './schedulingEntryDuplication';

describe('duplicateEntryWithCopiedDescription', () => {
  it('copies an entry after the source index with a unique copied description', () => {
    const entries = [
      { description: 'Rule', value: 1 },
      { description: 'Rule Copy', value: 2 },
      { description: 'Other', value: 3 },
    ];

    const result = duplicateEntryWithCopiedDescription(entries, 0, 'rule');

    expect(result).toEqual([
      { description: 'Rule', value: 1 },
      { description: 'Rule copy', value: 1 },
      { description: 'Rule Copy', value: 2 },
      { description: 'Other', value: 3 },
    ]);
    expect(result?.[1]).not.toBe(entries[0]);
  });

  it('uses an empty description when the source description is missing', () => {
    const result = duplicateEntryWithCopiedDescription([{ value: 1 }], 0, 'entry');

    expect(result).toEqual([
      { value: 1 },
      { value: 1, description: 'Copy' },
    ]);
  });

  it('returns null for an invalid source index', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    expect(duplicateEntryWithCopiedDescription([{ description: 'Rule' }], 2, 'rule')).toBeNull();
    expect(errorSpy).toHaveBeenCalledWith(expect.stringContaining('Cannot duplicate rule at index 2'));
  });
});
