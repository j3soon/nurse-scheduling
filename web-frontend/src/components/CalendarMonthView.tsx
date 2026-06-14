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

import { useEffect, useState } from 'react';
import { FiChevronLeft, FiChevronRight } from 'react-icons/fi';
import { addMonths, formatMonthYear, getCalendarMonthDates, isSameMonth, startOfMonth, WEEKDAY_LABELS } from '@/utils/calendar';
import { getTaiwanDayType } from '@/utils/taiwanHolidays';

export function getCalendarDayCategoryClassName(date: Date): string {
  const taiwanDayType = getTaiwanDayType(date);
  const isWeekend = date.getUTCDay() === 0 || date.getUTCDay() === 6;

  if (taiwanDayType === 'FREEDAY' && !isWeekend) {
    return 'bg-amber-50/70 font-medium text-amber-800 hover:bg-sky-100 hover:text-sky-900';
  }
  if (taiwanDayType === 'WORKDAY' && isWeekend) {
    return 'bg-white font-medium text-slate-700 hover:bg-sky-100 hover:text-sky-900';
  }
  if (isWeekend) {
    return 'bg-amber-50/70 text-amber-700 hover:bg-sky-100 hover:text-sky-900';
  }
  return 'bg-white text-slate-700 hover:bg-sky-100 hover:text-sky-900';
}

interface CalendarDayButtonProps {
  date: Date;
  ariaLabel: string;
  ariaPressed?: boolean;
  disabled?: boolean;
  stateClassName: string;
  onMouseDown?: () => void;
  onMouseEnter?: () => void;
  onMouseUp?: () => void;
}

export function CalendarDayButton({
  date,
  ariaLabel,
  ariaPressed,
  disabled = false,
  stateClassName,
  onMouseDown,
  onMouseEnter,
  onMouseUp,
}: CalendarDayButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      aria-label={ariaLabel}
      aria-pressed={ariaPressed}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
        }
      }}
      onMouseDown={(event) => {
        if (event.button === 0) onMouseDown?.();
      }}
      onMouseEnter={onMouseEnter}
      onMouseUp={(event) => {
        if (event.button === 0) onMouseUp?.();
      }}
      className={`relative aspect-square rounded border-2 border-gray-50 text-sm transition-colors ${stateClassName}`}
    >
      {date.getUTCDate()}
    </button>
  );
}

interface CalendarMonthNavigationOptions {
  initialMonth: Date;
  minimumMonth?: Date;
  maximumMonth?: Date;
}

export function useCalendarMonthNavigation({
  initialMonth,
  minimumMonth,
  maximumMonth,
}: CalendarMonthNavigationOptions) {
  const normalizedMinimum = minimumMonth ? startOfMonth(minimumMonth) : undefined;
  const normalizedMaximum = maximumMonth ? startOfMonth(maximumMonth) : undefined;
  const [requestedActiveMonth, setRequestedActiveMonth] = useState(() => startOfMonth(initialMonth));
  const clampMonth = (month: Date): Date => {
    const normalizedMonth = startOfMonth(month);
    if (normalizedMinimum && normalizedMonth < normalizedMinimum) return normalizedMinimum;
    if (normalizedMaximum && normalizedMonth > normalizedMaximum) return normalizedMaximum;
    return normalizedMonth;
  };
  const activeMonth = clampMonth(requestedActiveMonth);

  return {
    activeMonth,
    setActiveMonth: (month: Date) => setRequestedActiveMonth(clampMonth(month)),
    isPreviousMonthDisabled: Boolean(normalizedMinimum && isSameMonth(activeMonth, normalizedMinimum)),
    isNextMonthDisabled: Boolean(normalizedMaximum && isSameMonth(activeMonth, normalizedMaximum)),
  };
}

export function useMouseDragLifecycle(onGlobalMouseUp: () => void) {
  useEffect(() => {
    window.addEventListener('mouseup', onGlobalMouseUp);
    return () => {
      window.removeEventListener('mouseup', onGlobalMouseUp);
      document.body.style.removeProperty('user-select');
    };
  }, [onGlobalMouseUp]);

  return {
    disableTextSelection: () => document.body.style.setProperty('user-select', 'none'),
  };
}

interface CalendarMonthViewProps {
  activeMonth: Date;
  onActiveMonthChange: (month: Date) => void;
  isPreviousMonthDisabled?: boolean;
  isNextMonthDisabled?: boolean;
  onGridMouseLeave?: () => void;
  renderDay: (date: Date) => React.ReactNode;
  footer?: React.ReactNode;
}

export function CalendarMonthView({
  activeMonth,
  onActiveMonthChange,
  isPreviousMonthDisabled = false,
  isNextMonthDisabled = false,
  onGridMouseLeave,
  renderDay,
  footer,
}: CalendarMonthViewProps) {
  const calendarDates = getCalendarMonthDates(activeMonth);

  return (
    <div className="w-full max-w-md rounded-md border border-gray-200 bg-gray-50 p-4">
      <div className="flex items-center justify-between border-b border-gray-200 pb-2">
        <button
          type="button"
          aria-label="Previous month"
          disabled={isPreviousMonthDisabled}
          onClick={() => onActiveMonthChange(addMonths(activeMonth, -1))}
          className="rounded-md p-2 text-gray-600 hover:bg-white hover:text-gray-900 disabled:cursor-not-allowed disabled:text-gray-300 disabled:hover:bg-transparent"
        >
          <FiChevronLeft className="h-5 w-5" />
        </button>
        <div className="text-sm font-semibold text-gray-900">{formatMonthYear(activeMonth)}</div>
        <button
          type="button"
          aria-label="Next month"
          disabled={isNextMonthDisabled}
          onClick={() => onActiveMonthChange(addMonths(activeMonth, 1))}
          className="rounded-md p-2 text-gray-600 hover:bg-white hover:text-gray-900 disabled:cursor-not-allowed disabled:text-gray-300 disabled:hover:bg-transparent"
        >
          <FiChevronRight className="h-5 w-5" />
        </button>
      </div>

      <div className="mt-3 grid grid-cols-7 gap-1 text-center text-xs font-medium text-gray-500">
        {WEEKDAY_LABELS.map(dayName => (
          <div key={dayName}>{dayName}</div>
        ))}
      </div>
      <div data-testid="calendar-month-grid" className="mt-2 grid grid-cols-7" onMouseLeave={onGridMouseLeave}>
        {calendarDates.map((date, index) => date
          ? renderDay(date)
          : <div key={`blank-${index}`} aria-hidden="true" />)}
      </div>
      {footer}
    </div>
  );
}
