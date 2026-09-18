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

import { replaceInfinityValues, restoreInfinityValues } from '@/hooks/schedulingStorage';
import { INFINITY_PLACEHOLDER, NEGATIVE_INFINITY_PLACEHOLDER } from '@/hooks/schedulingConstants';

const roundTrip = (value: unknown) => restoreInfinityValues(JSON.parse(JSON.stringify(replaceInfinityValues(value))));

describe('infinity placeholders', () => {
  it('round-trips infinite weights', () => {
    expect(roundTrip({ weight: Infinity })).toEqual({ weight: Infinity });
    expect(roundTrip({ weight: -Infinity })).toEqual({ weight: -Infinity });
    expect(roundTrip([{ weight: Infinity }, { weight: 3 }])).toEqual([{ weight: Infinity }, { weight: 3 }]);
  });

  it('round-trips an ID that collides with a placeholder', () => {
    for (const id of [
      INFINITY_PLACEHOLDER,
      NEGATIVE_INFINITY_PLACEHOLDER,
      `__ESCAPED__${INFINITY_PLACEHOLDER}`,
    ]) {
      expect(roundTrip({ id })).toEqual({ id });
    }
  });

  it('leaves other values untouched', () => {
    expect(roundTrip({ id: 'Night', weight: 3, note: null })).toEqual({ id: 'Night', weight: 3, note: null });
  });
});
