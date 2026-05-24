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

import { dateStrToDate } from '@/utils/dateParsing';

describe('dateStrToDate', () => {
  const dateRange = {
    startDate: new Date(Date.UTC(2026, 6, 20, 12)),
    endDate: new Date(Date.UTC(2026, 6, 27, 12)),
  };

  it('parses full YYYY-MM-DD format directly', () => {
    const result = dateStrToDate('2025-12-31', dateRange);
    expect(result.toISOString().slice(0, 10)).toBe('2025-12-31');
  });

  it('infers year for MM-DD format from date range start', () => {
    const result = dateStrToDate('03-15', dateRange);
    expect(result.toISOString().slice(0, 10)).toBe('2026-03-15');
  });

  it('infers year and month for DD format from date range start', () => {
    const result = dateStrToDate('09', dateRange);
    expect(result.toISOString().slice(0, 10)).toBe('2026-07-09');
  });

  it('returns current date fallback on invalid input', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const now = Date.now();
    const result = dateStrToDate('invalid', dateRange);
    expect(Math.abs(result.getTime() - now)).toBeLessThan(5_000);
    expect(errorSpy).toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
