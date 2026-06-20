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

import {
  syncCoefficientPairs,
  updateCoefficientPair,
  validateCoefficientPairs,
} from '@/utils/countShiftTypeCoefficients';

const shiftTypeData = {
  items: [
    { id: 'D', description: 'Day' },
    { id: 'N', description: 'Night' },
  ],
  groups: [{ id: 'WORK', members: ['D', 'N'], description: 'Working shifts' }],
};

describe('countShiftTypeCoefficients', () => {
  it('drops deselected coefficients and preserves selected coefficients', () => {
    const afterDeselect = syncCoefficientPairs(['N'], [['D', 3], ['N', 2]]);
    const afterReselect = syncCoefficientPairs(['N', 'D'], afterDeselect);

    expect(afterDeselect).toEqual([['N', 2]]);
    expect(afterReselect).toEqual([['N', 2], ['D', 1]]);
  });

  it('updates one coefficient while preserving selected pairs', () => {
    expect(updateCoefficientPair(['D', 'N'], [['D', 1], ['N', 2]], 'D', 4)).toEqual([
      ['D', 4],
      ['N', 2],
    ]);
  });

  it('returns field errors before checking overlap', () => {
    expect(validateCoefficientPairs(['D', 'WORK'], [['D', 0], ['WORK', 3]], shiftTypeData)).toEqual({
      coefficients: [],
      errorsById: {
        D: 'Coefficient for D must be an integer of at least 1',
      },
    });
  });

  it('omits defaults and detects overlap among non-default coefficients', () => {
    expect(validateCoefficientPairs(['D', 'WORK'], [['D', 2], ['WORK', 3]], shiftTypeData)).toEqual({
      coefficients: [['D', 2], ['WORK', 3]],
      errorsById: {},
      overlapError: 'Shift type coefficients overlap: D, WORK include D',
    });
  });
});
