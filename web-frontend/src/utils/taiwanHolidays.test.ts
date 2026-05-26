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

import {
  buildTaiwanHolidayGroups,
  getTaiwanHolidayEntriesInRange,
  includesUnimportedTaiwanLaborDay,
  isTaiwanHolidayRangeSupported,
  TAIWAN_FREEDAY_GROUP_ID,
  TAIWAN_WORKDAY_GROUP_ID,
} from '@/utils/taiwanHolidays';

describe('taiwanHolidays', () => {
  it('accepts only ranges fully inside the supported window', () => {
    expect(isTaiwanHolidayRangeSupported({
      startDate: new Date('2026-01-01'),
      endDate: new Date('2026-01-31'),
    })).toBe(true);

    expect(isTaiwanHolidayRangeSupported({
      startDate: new Date('2022-12-31'),
      endDate: new Date('2023-01-31'),
    })).toBe(false);

    expect(isTaiwanHolidayRangeSupported({
      startDate: new Date('2026-12-01'),
      endDate: new Date('2027-01-01'),
    })).toBe(false);
  });

  it('flags only the unimported Labor Day years', () => {
    expect(includesUnimportedTaiwanLaborDay({
      startDate: new Date('2023-05-01'),
      endDate: new Date('2023-05-31'),
    })).toBe(true);

    expect(includesUnimportedTaiwanLaborDay({
      startDate: new Date('2024-04-20'),
      endDate: new Date('2024-05-10'),
    })).toBe(true);

    expect(includesUnimportedTaiwanLaborDay({
      startDate: new Date('2026-05-01'),
      endDate: new Date('2026-05-31'),
    })).toBe(false);
  });

  it('returns Taiwan holiday entries only within supported ranges', () => {
    expect(getTaiwanHolidayEntriesInRange({
      startDate: new Date('2026-05-01'),
      endDate: new Date('2026-05-02'),
    })).toEqual([
      {
        date: '2026-05-01',
        reason: '勞動節',
        isFreeday: true,
      },
    ]);

    expect(getTaiwanHolidayEntriesInRange({
      startDate: new Date('2027-05-01'),
      endDate: new Date('2027-05-31'),
    })).toEqual([]);
  });

  it('returns the correct Taiwan holiday entries for the whole month of February 2025', () => {
    expect(getTaiwanHolidayEntriesInRange({
      startDate: new Date('2025-02-01'),
      endDate: new Date('2025-02-28'),
    })).toEqual([
      {
        date: '2025-02-08',
        reason: '補行上班 (2025-01-27 小年夜)',
        isFreeday: false,
      },
      {
        date: '2025-02-28',
        reason: '和平紀念日',
        isFreeday: true,
      },
    ]);
  });

  it('builds WORKDAY and FREEDAY groups from supported date items', () => {
    const groups = buildTaiwanHolidayGroups(
      [
        { id: '01', description: '' },
        { id: '02', description: '' },
        { id: '04', description: '' },
      ],
      {
        startDate: new Date('2026-05-01'),
        endDate: new Date('2026-05-04'),
      },
    );

    expect(groups).toEqual([
      {
        id: TAIWAN_WORKDAY_GROUP_ID,
        description: 'Taiwan workdays imported from the current holiday calendar',
        members: ['04'],
      },
      {
        id: TAIWAN_FREEDAY_GROUP_ID,
        description: 'Taiwan freedays imported from the current holiday calendar',
        members: ['01', '02'],
      },
    ]);
  });

  it('returns no Taiwan holiday groups for unsupported ranges', () => {
    expect(buildTaiwanHolidayGroups(
      [{ id: '01', description: '' }],
      {
        startDate: new Date('2027-01-01'),
        endDate: new Date('2027-01-31'),
      },
    )).toEqual([]);
  });
});
