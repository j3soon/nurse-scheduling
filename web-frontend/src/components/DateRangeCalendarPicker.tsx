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

import { useCallback, useMemo, useState } from 'react';
import {
  CalendarDayButton,
  CalendarMonthView,
  getCalendarDayCategoryClassName,
  useCalendarMonthNavigation,
  useMouseDragLifecycle,
} from '@/components/CalendarMonthView';
import { DateRange } from '@/types/scheduling';
import {
  endOfMonth,
  formatMonthYear,
  startOfMonth,
} from '@/utils/calendar';

interface DateRangeCalendarPickerProps {
  value: DateRange;
  onChange: (value: DateRange) => void;
  onActiveEndpointChange?: (endpoint: 'start' | 'end') => void;
}

function dateToString(date?: Date): string {
  return date ? date.toISOString().split('T')[0] : '';
}

export default function DateRangeCalendarPicker({
  value,
  onChange,
  onActiveEndpointChange,
}: DateRangeCalendarPickerProps) {
  const {
    activeMonth: calendarMonth,
    setActiveMonth: setCalendarMonth,
  } = useCalendarMonthNavigation({
    initialMonth: value.startDate ?? new Date(),
  });
  const [dragAnchorDate, setDragAnchorDate] = useState<Date | undefined>(undefined);
  const [clickAnchorDate, setClickAnchorDate] = useState<Date | undefined>(undefined);
  const [hoverDate, setHoverDate] = useState<Date | undefined>(undefined);
  const [didDrag, setDidDrag] = useState(false);
  const resetDragState = useCallback(() => {
    setDragAnchorDate(undefined);
    setHoverDate(undefined);
    setDidDrag(false);
    document.body.style.removeProperty('user-select');
  }, []);
  const { disableTextSelection } = useMouseDragLifecycle(resetDragState);

  const suggestedMonthLabel = formatMonthYear(calendarMonth);
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
    disableTextSelection();
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
      onActiveEndpointChange?.('start');
    } else if (clickAnchorDate) {
      if (date >= clickAnchorDate) {
        onChange({ startDate: clickAnchorDate, endDate: date });
        setClickAnchorDate(undefined);
        onActiveEndpointChange?.('start');
      } else {
        onChange({ startDate: date, endDate: undefined });
        setClickAnchorDate(date);
        onActiveEndpointChange?.('end');
      }
    } else {
      onChange({ startDate: date, endDate: date });
      setClickAnchorDate(date);
      onActiveEndpointChange?.('end');
    }
    resetDragState();
  };

  const handleUseSuggestedMonth = () => {
    const startDate = startOfMonth(calendarMonth);
    const endDate = endOfMonth(calendarMonth);
    setCalendarMonth(startDate);
    setClickAnchorDate(undefined);
    setHoverDate(undefined);
    onChange({ startDate, endDate });
    onActiveEndpointChange?.('start');
  };

  return (
    <CalendarMonthView
      activeMonth={calendarMonth}
      onActiveMonthChange={setCalendarMonth}
      onGridMouseLeave={resetDragState}
      renderDay={(date) => {
        const isPreviewEndpoint = isRangeEndpoint(date, previewRange);
        const isPreviewMiddle = isRangeMiddleDate(date, previewRange);
        const isSelected = isRangeEndpoint(date, value) || isRangeMiddleDate(date, value);

        return (
          <CalendarDayButton
            key={date.toISOString()}
            date={date}
            ariaLabel={`Select ${dateToString(date)}`}
            onMouseDown={() => handleCalendarDateMouseDown(date)}
            onMouseEnter={() => handleCalendarDateMouseEnter(date)}
            onMouseUp={() => handleCalendarDateMouseUp(date)}
            stateClassName={
              isPreviewEndpoint
                ? 'bg-indigo-200 font-medium text-indigo-950'
                : isPreviewMiddle
                  ? 'bg-indigo-100 text-indigo-900'
                  : isSelected
                    ? 'bg-blue-600 font-medium text-white hover:bg-blue-700'
                    : getCalendarDayCategoryClassName(date)
            }
          />
        );
      }}
      footer={(
        <button
          type="button"
          onClick={handleUseSuggestedMonth}
          className="mt-4 w-full rounded-md border border-blue-200 bg-white px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50"
        >
          Use full {suggestedMonthLabel}
        </button>
      )}
    />
  );
}
