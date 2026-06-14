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
  addDays,
  addMonths,
  endOfMonth,
  formatMonthYear,
  getDateIdForRange,
  getCalendarMonthDates,
  isFullCalendarMonth,
  startOfMonth,
} from '@/utils/calendar';

describe('calendar utilities', () => {
  it('performs month and day arithmetic in UTC', () => {
    const date = new Date('2026-05-15T12:00:00.000Z');

    expect(startOfMonth(date).toISOString()).toBe('2026-05-01T00:00:00.000Z');
    expect(endOfMonth(date).toISOString()).toBe('2026-05-31T00:00:00.000Z');
    expect(addMonths(date, 1).toISOString()).toBe('2026-06-01T00:00:00.000Z');
    expect(addDays(date, 1).toISOString()).toBe('2026-05-16T00:00:00.000Z');
    expect(formatMonthYear(date)).toBe('May 2026');
  });

  it('builds a month grid with leading blank days', () => {
    const dates = getCalendarMonthDates(new Date('2026-05-15'));

    expect(dates).toHaveLength(36);
    expect(dates.slice(0, 5)).toEqual([undefined, undefined, undefined, undefined, undefined]);
    expect(dates[5]?.toISOString().slice(0, 10)).toBe('2026-05-01');
    expect(dates.at(-1)?.toISOString().slice(0, 10)).toBe('2026-05-31');
  });

  it('recognizes complete calendar months including leap-year February', () => {
    expect(isFullCalendarMonth({
      startDate: new Date('2028-02-01T12:00:00.000Z'),
      endDate: new Date('2028-02-29T12:00:00.000Z'),
    })).toBe(true);
    expect(isFullCalendarMonth({
      startDate: new Date('2028-02-01'),
      endDate: new Date('2028-02-28'),
    })).toBe(false);
  });

  it('formats date IDs according to the configured range scope', () => {
    const date = new Date('2026-06-01');

    expect(getDateIdForRange(date, {
      startDate: new Date('2026-06-01'),
      endDate: new Date('2026-06-30'),
    })).toBe('01');
    expect(getDateIdForRange(date, {
      startDate: new Date('2026-05-01'),
      endDate: new Date('2026-06-30'),
    })).toBe('06-01');
    expect(getDateIdForRange(date, {
      startDate: new Date('2025-12-01'),
      endDate: new Date('2026-06-30'),
    })).toBe('2026-06-01');
  });
});
