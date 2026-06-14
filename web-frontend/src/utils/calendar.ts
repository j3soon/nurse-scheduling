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

import { DateRange } from '@/types/scheduling';

export const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'] as const;

export function startOfMonth(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
}

export function endOfMonth(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0));
}

export function addMonths(date: Date, months: number): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + months, 1));
}

export function addDays(date: Date, days: number): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + days));
}

export function formatMonthYear(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });
}

export function getCalendarMonthDates(date: Date): Array<Date | undefined> {
  const firstDay = startOfMonth(date);
  const monthLength = endOfMonth(date).getUTCDate();

  return [
    ...Array.from({ length: firstDay.getUTCDay() }, () => undefined),
    ...Array.from({ length: monthLength }, (_, dayIndex) => addDays(firstDay, dayIndex)),
  ];
}

export function isFullCalendarMonth(dateRange: DateRange): boolean {
  const { startDate, endDate } = dateRange;
  if (!startDate || !endDate || startDate.getUTCDate() !== 1) {
    return false;
  }

  const lastDay = endOfMonth(startDate);
  return endDate.getUTCFullYear() === lastDay.getUTCFullYear()
    && endDate.getUTCMonth() === lastDay.getUTCMonth()
    && endDate.getUTCDate() === lastDay.getUTCDate();
}

export function isSameMonth(firstDate: Date, secondDate: Date): boolean {
  return firstDate.getUTCFullYear() === secondDate.getUTCFullYear()
    && firstDate.getUTCMonth() === secondDate.getUTCMonth();
}

export function getDateIdForRange(date: Date, dateRange: DateRange): string {
  const dateString = date.toISOString().split('T')[0];
  const { startDate, endDate } = dateRange;
  if (!startDate || !endDate) {
    return dateString;
  }

  if (isSameMonth(startDate, endDate)) {
    return dateString.slice(-2);
  }
  if (startDate.getUTCFullYear() === endDate.getUTCFullYear()) {
    return dateString.slice(5);
  }
  return dateString;
}
