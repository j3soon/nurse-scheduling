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

import { useMemo, useState } from 'react';
import { FiChevronLeft, FiChevronRight } from 'react-icons/fi';
import { DateRange } from '@/types/scheduling';

interface DateRangeCalendarPickerProps {
  value: DateRange;
  onChange: (value: DateRange) => void;
}

function dateToString(date?: Date): string {
  return date ? date.toISOString().split('T')[0] : '';
}

function startOfMonth(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
}

function endOfMonth(date: Date): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0));
}

function addMonths(date: Date, months: number): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + months, 1));
}

function addDays(date: Date, days: number): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + days));
}

function formatMonthYear(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric', timeZone: 'UTC' });
}

export default function DateRangeCalendarPicker({ value, onChange }: DateRangeCalendarPickerProps) {
  const [calendarMonth, setCalendarMonth] = useState<Date>(() => {
    const anchorDate = value.startDate ?? new Date();
    return startOfMonth(anchorDate);
  });
  const [dragAnchorDate, setDragAnchorDate] = useState<Date | undefined>(undefined);
  const [clickAnchorDate, setClickAnchorDate] = useState<Date | undefined>(undefined);
  const [hoverDate, setHoverDate] = useState<Date | undefined>(undefined);
  const [didDrag, setDidDrag] = useState(false);

  const calendarDates = useMemo(() => {
    const firstDay = startOfMonth(calendarMonth);
    const monthLength = endOfMonth(calendarMonth).getUTCDate();
    const leadingBlankCount = firstDay.getUTCDay();

    return [
      ...Array.from({ length: leadingBlankCount }, () => undefined),
      ...Array.from({ length: monthLength }, (_, dayIndex) => addDays(firstDay, dayIndex)),
    ];
  }, [calendarMonth]);
  const suggestedMonthLabel = formatMonthYear(calendarMonth);
  const selectedDayCount = value.startDate && value.endDate
    ? Math.ceil((value.endDate.getTime() - value.startDate.getTime()) / (1000 * 60 * 60 * 24)) + 1
    : 0;
  const previewRange = useMemo<DateRange>(() => {
    const anchorDate = dragAnchorDate ?? clickAnchorDate;
    if (!anchorDate || !hoverDate) {
      return {};
    }

    if (hoverDate >= anchorDate) {
      return { startDate: anchorDate, endDate: hoverDate };
    }

    return {
      startDate: hoverDate,
      endDate: dragAnchorDate ? anchorDate : hoverDate,
    };
  }, [clickAnchorDate, dragAnchorDate, hoverDate]);

  const setRangeFromDates = (firstDate: Date, secondDate: Date) => {
    const startDate = firstDate <= secondDate ? firstDate : secondDate;
    const endDate = firstDate <= secondDate ? secondDate : firstDate;
    onChange({ startDate, endDate });
  };

  const isRangeEndpoint = (date: Date, range: DateRange): boolean => {
    return date.getTime() === range.startDate?.getTime() || date.getTime() === range.endDate?.getTime();
  };

  const isRangeMiddleDate = (date: Date, range: DateRange): boolean => {
    return Boolean(range.startDate && range.endDate && date > range.startDate && date < range.endDate);
  };

  const handleCalendarDateMouseDown = (date: Date) => {
    setDragAnchorDate(date);
    setHoverDate(date);
    setDidDrag(false);
  };

  const handleCalendarDateMouseEnter = (date: Date) => {
    setHoverDate(date);
    if (!dragAnchorDate) {
      return;
    }
    if (date.getTime() !== dragAnchorDate.getTime()) {
      setDidDrag(true);
    }
  };

  const handleCalendarDateMouseUp = (date: Date) => {
    if (dragAnchorDate && didDrag) {
      setRangeFromDates(dragAnchorDate, date);
      setClickAnchorDate(undefined);
    } else if (clickAnchorDate) {
      if (date >= clickAnchorDate) {
        onChange({ startDate: clickAnchorDate, endDate: date });
        setClickAnchorDate(undefined);
      } else {
        onChange({ startDate: date, endDate: undefined });
        setClickAnchorDate(date);
      }
    } else {
      onChange({ startDate: date, endDate: date });
      setClickAnchorDate(date);
    }
    setDragAnchorDate(undefined);
    setHoverDate(undefined);
    setDidDrag(false);
  };

  const handleUseSuggestedMonth = () => {
    const startDate = startOfMonth(calendarMonth);
    const endDate = endOfMonth(calendarMonth);
    setCalendarMonth(startDate);
    setClickAnchorDate(undefined);
    setHoverDate(undefined);
    onChange({ startDate, endDate });
  };

  return (
    <div className="w-full max-w-sm rounded-md border border-gray-200 bg-gray-50 p-4">
      <div className="mb-3 space-y-3">
        <div className="grid grid-cols-2 gap-2" aria-live="polite">
          <div className={`rounded-md border bg-white px-3 py-2 ${
            clickAnchorDate ? 'border-gray-200' : 'border-blue-500 ring-1 ring-blue-500'
          }`}>
            <div className={`text-xs font-medium ${clickAnchorDate ? 'text-gray-500' : 'text-blue-700'}`}>
              Start
            </div>
            <div className="mt-0.5 text-sm font-medium text-gray-900">
              {dateToString(value.startDate) || 'Select date'}
            </div>
          </div>
          <div className={`rounded-md border bg-white px-3 py-2 ${
            clickAnchorDate ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'
          }`}>
            <div className={`text-xs font-medium ${clickAnchorDate ? 'text-blue-700' : 'text-gray-500'}`}>
              End
            </div>
            <div className="mt-0.5 text-sm font-medium text-gray-900">
              {dateToString(value.endDate) || 'Select date'}
            </div>
          </div>
        </div>
        {value.startDate && value.endDate && (
          <div className="text-sm text-gray-600">
            {selectedDayCount} day{selectedDayCount === 1 ? '' : 's'} selected
          </div>
        )}
        <button
          type="button"
          onClick={handleUseSuggestedMonth}
          className="w-full rounded-md border border-blue-200 bg-white px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50"
        >
          Use full {suggestedMonthLabel}
        </button>
      </div>

      <div className="flex items-center justify-between border-y border-gray-200 py-2">
        <button
          type="button"
          aria-label="Previous month"
          onClick={() => setCalendarMonth(prev => addMonths(prev, -1))}
          className="rounded-md p-2 text-gray-600 hover:bg-white hover:text-gray-900"
        >
          <FiChevronLeft className="h-5 w-5" />
        </button>
        <div className="text-sm font-semibold text-gray-900">{formatMonthYear(calendarMonth)}</div>
        <button
          type="button"
          aria-label="Next month"
          onClick={() => setCalendarMonth(prev => addMonths(prev, 1))}
          className="rounded-md p-2 text-gray-600 hover:bg-white hover:text-gray-900"
        >
          <FiChevronRight className="h-5 w-5" />
        </button>
      </div>

      <div className="mt-3 grid grid-cols-7 gap-1 text-center text-xs font-medium text-gray-500">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(dayName => (
          <div key={dayName}>{dayName}</div>
        ))}
      </div>
      <div
        className="mt-2 grid grid-cols-7 gap-1"
        onMouseLeave={() => {
          setDragAnchorDate(undefined);
          setHoverDate(undefined);
          setDidDrag(false);
        }}
      >
        {calendarDates.map((date, index) => (
          date ? (
            <button
              key={date.toISOString()}
              type="button"
              aria-label={`Select ${dateToString(date)}`}
              onMouseDown={() => handleCalendarDateMouseDown(date)}
              onMouseEnter={() => handleCalendarDateMouseEnter(date)}
              onMouseUp={() => handleCalendarDateMouseUp(date)}
              className={`aspect-square rounded-md text-sm font-medium transition-colors ${
                isRangeEndpoint(date, previewRange)
                  ? 'bg-blue-100 text-blue-900 ring-1 ring-blue-500'
                  : isRangeMiddleDate(date, previewRange)
                    ? 'bg-blue-100 text-blue-900'
                    : isRangeEndpoint(date, value)
                      ? 'bg-blue-600 text-white hover:bg-blue-700'
                      : isRangeMiddleDate(date, value)
                        ? 'bg-blue-600 text-white hover:bg-blue-700'
                        : 'bg-white text-gray-800 hover:bg-blue-50'
              }`}
            >
              {date.getUTCDate()}
            </button>
          ) : (
            <div key={`blank-${index}`} aria-hidden="true" />
          )
        ))}
      </div>
    </div>
  );
}
