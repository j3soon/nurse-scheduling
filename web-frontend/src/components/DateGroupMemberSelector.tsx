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

'use client';

import { useCallback, useMemo, useRef, useState } from 'react';
import {
  CalendarDayButton,
  CalendarMonthView,
  getCalendarDayCategoryClassName,
  useCalendarMonthNavigation,
  useMouseDragLifecycle,
} from '@/components/CalendarMonthView';
import { CheckboxList } from '@/components/CheckboxList';
import { DateRange, Item } from '@/types/scheduling';
import { getDateIdForRange } from '@/utils/calendar';

interface DateGroupMemberSelectorProps {
  dateRange: DateRange;
  items: Item[];
  selectedIds: string[];
  onToggle: (id: string) => void;
}

export function DateGroupMemberSelector({
  dateRange,
  items,
  selectedIds,
  onToggle,
}: DateGroupMemberSelectorProps) {
  const [view, setView] = useState<'calendar' | 'list'>('calendar');
  const {
    activeMonth,
    setActiveMonth,
    isPreviousMonthDisabled,
    isNextMonthDisabled,
  } = useCalendarMonthNavigation({
    initialMonth: dateRange.startDate ?? new Date(),
    minimumMonth: dateRange.startDate,
    maximumMonth: dateRange.endDate,
  });
  const mouseDownIdRef = useRef('');
  const lastEnteredIdRef = useRef('');
  const isDraggingRef = useRef(false);

  const resetDragState = useCallback(() => {
    mouseDownIdRef.current = '';
    lastEnteredIdRef.current = '';
    isDraggingRef.current = false;
    document.body.style.removeProperty('user-select');
  }, []);
  const { disableTextSelection } = useMouseDragLifecycle(resetDragState);

  const generatedIds = useMemo(() => {
    const ids = new Set<string>();
    if (!dateRange.startDate || !dateRange.endDate) {
      return ids;
    }

    const endDateKey = dateRange.endDate.toISOString().split('T')[0];
    for (
      let date = new Date(Date.UTC(
        dateRange.startDate.getUTCFullYear(),
        dateRange.startDate.getUTCMonth(),
        dateRange.startDate.getUTCDate(),
      ));
      date.toISOString().split('T')[0] <= endDateKey;
      date.setUTCDate(date.getUTCDate() + 1)
    ) {
      ids.add(getDateIdForRange(date, dateRange));
    }
    return ids;
  }, [dateRange]);

  if (!dateRange.startDate || !dateRange.endDate) {
    return (
      <CheckboxList
        items={items}
        selectedIds={selectedIds}
        onToggle={onToggle}
        label="Members"
      />
    );
  }

  const itemById = new Map(items.map(item => [item.id, item]));
  const startDateKey = dateRange.startDate.toISOString().split('T')[0];
  const endDateKey = dateRange.endDate.toISOString().split('T')[0];
  const generatedItems = items.filter(item => generatedIds.has(item.id));
  const otherItems = items.filter(item => !generatedIds.has(item.id));

  const getSelectableId = (date: Date): string | undefined => {
    const dateKey = date.toISOString().split('T')[0];
    if (dateKey < startDateKey || dateKey > endDateKey) {
      return undefined;
    }

    const id = getDateIdForRange(date, dateRange);
    return itemById.has(id) ? id : undefined;
  };

  const handleDateMouseDown = (id: string) => {
    mouseDownIdRef.current = id;
    lastEnteredIdRef.current = id;
    isDraggingRef.current = false;
    disableTextSelection();
  };

  const handleDateMouseEnter = (id: string) => {
    if (!mouseDownIdRef.current || id === lastEnteredIdRef.current) {
      return;
    }

    if (!isDraggingRef.current) {
      isDraggingRef.current = true;
      onToggle(mouseDownIdRef.current);
    }
    onToggle(id);
    lastEnteredIdRef.current = id;
  };

  const handleDateMouseUp = (id: string) => {
    if (!isDraggingRef.current) {
      onToggle(id);
    }
    resetDragState();
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-medium text-gray-700">Members</h3>
        <div className="inline-flex rounded-md border border-gray-200 bg-gray-50 p-0.5">
          {(['calendar', 'list'] as const).map(option => (
            <button
              key={option}
              type="button"
              aria-pressed={view === option}
              onClick={() => setView(option)}
              className={`rounded px-3 py-1 text-xs font-medium ${
                view === option
                  ? 'bg-white text-blue-700 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {option === 'calendar' ? 'Calendar view' : 'List view'}
            </button>
          ))}
        </div>
      </div>
      {view === 'calendar' ? (
        <CalendarMonthView
          activeMonth={activeMonth}
          onActiveMonthChange={setActiveMonth}
          isPreviousMonthDisabled={isPreviousMonthDisabled}
          isNextMonthDisabled={isNextMonthDisabled}
          onGridMouseLeave={resetDragState}
          renderDay={(date) => {
            const id = getSelectableId(date);
            const isSelected = Boolean(id && selectedIds.includes(id));

            return (
              <CalendarDayButton
                key={date.toISOString()}
                date={date}
                disabled={!id}
                ariaLabel={id ?? `Unavailable ${date.toISOString().split('T')[0]}`}
                ariaPressed={id ? isSelected : undefined}
                onMouseDown={() => id && handleDateMouseDown(id)}
                onMouseEnter={() => id && handleDateMouseEnter(id)}
                onMouseUp={() => id && handleDateMouseUp(id)}
                stateClassName={
                  !id
                    ? 'cursor-not-allowed bg-transparent text-gray-300'
                    : isSelected
                      ? 'bg-blue-600 font-medium text-white hover:bg-blue-700'
                      : getCalendarDayCategoryClassName(date)
                }
              />
            );
          }}
        />
      ) : (
        <CheckboxList
          items={generatedItems}
          selectedIds={selectedIds}
          onToggle={onToggle}
          label=""
        />
      )}
      {otherItems.length > 0 && (
        <CheckboxList
          items={otherItems}
          selectedIds={selectedIds}
          onToggle={onToggle}
          label="Other dates"
        />
      )}
    </div>
  );
}
