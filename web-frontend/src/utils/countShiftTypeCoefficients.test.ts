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
  getCoefficientShiftTypeIds,
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
    const afterDeselect = syncCoefficientPairs(['N'], [['D', 3], ['N', 2]], shiftTypeData);
    const afterReselect = syncCoefficientPairs(['N', 'D'], afterDeselect, shiftTypeData);

    expect(afterDeselect).toEqual([['N', 2]]);
    expect(afterReselect).toEqual([['D', ''], ['N', 2], ['WORK', '']]);
  });

  it('uses selected item coverage to include fully covered groups', () => {
    expect(getCoefficientShiftTypeIds(['D', 'N'], shiftTypeData)).toEqual(['D', 'N', 'WORK']);
  });

  it('expands selected groups into coefficient item options', () => {
    expect(syncCoefficientPairs(['WORK'], [['D', 2]], shiftTypeData)).toEqual([
      ['D', 2],
      ['N', ''],
      ['WORK', ''],
    ]);
  });

  it('leaves missing coefficients blank and omits them from output', () => {
    expect(validateCoefficientPairs(['D', 'N'], [], shiftTypeData)).toEqual({
      coefficients: [],
      errorsById: {},
      overlapError: undefined,
    });
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

  it('detects overlap among explicit coefficients', () => {
    expect(validateCoefficientPairs(['D', 'WORK'], [['D', 2], ['WORK', 3]], shiftTypeData)).toEqual({
      coefficients: [['D', 2], ['WORK', 3]],
      errorsById: {},
      overlapError: 'Shift type coefficients overlap: D, WORK include D',
    });
  });

  it('keeps explicit coefficient one and detects overlap against containing groups', () => {
    expect(validateCoefficientPairs(['D', 'WORK'], [['D', 1], ['WORK', 2]], shiftTypeData)).toEqual({
      coefficients: [['D', 1], ['WORK', 2]],
      errorsById: {},
      overlapError: 'Shift type coefficients overlap: D, WORK include D',
    });
  });
});
