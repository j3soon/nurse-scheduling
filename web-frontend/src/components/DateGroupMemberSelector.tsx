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

import { useState } from 'react';
import { CheckboxList } from '@/components/CheckboxList';
import { DateRange, Item } from '@/types/scheduling';

interface DateGroupMemberSelectorProps {
  dateRange: DateRange;
  items: Item[];
  selectedIds: string[];
  onToggle: (id: string) => void;
}

function isFullCalendarMonth(dateRange: DateRange): boolean {
  const { startDate, endDate } = dateRange;
  if (!startDate || !endDate || startDate.getUTCDate() !== 1) {
    return false;
  }

  const lastDay = new Date(Date.UTC(startDate.getUTCFullYear(), startDate.getUTCMonth() + 1, 0));
  return endDate.getUTCFullYear() === lastDay.getUTCFullYear()
    && endDate.getUTCMonth() === lastDay.getUTCMonth()
    && endDate.getUTCDate() === lastDay.getUTCDate();
}

export function DateGroupMemberSelector({
  dateRange,
  items,
  selectedIds,
  onToggle,
}: DateGroupMemberSelectorProps) {
  const [view, setView] = useState<'calendar' | 'list'>('calendar');

  if (!isFullCalendarMonth(dateRange) || !dateRange.startDate) {
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
  const monthLength = dateRange.endDate!.getUTCDate();
  const calendarItems = Array.from({ length: monthLength }, (_, index) => {
    const id = String(index + 1).padStart(2, '0');
    return itemById.get(id);
  }).filter((item): item is Item => Boolean(item));
  const calendarIds = new Set(calendarItems.map(item => item.id));
  const otherItems = items.filter(item => !calendarIds.has(item.id));
  const monthLabel = dateRange.startDate.toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });

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
        <div className="max-w-md rounded-md border border-gray-200 bg-gray-50 p-3">
          <div className="text-center text-sm font-semibold text-gray-900">{monthLabel}</div>
          <div className="mt-3 grid grid-cols-7 gap-1 text-center text-xs font-medium text-gray-500">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(dayName => (
              <div key={dayName}>{dayName}</div>
            ))}
          </div>
          <CheckboxList
            items={calendarItems}
            selectedIds={selectedIds}
            onToggle={onToggle}
            label=""
            itemsClassName="mt-2 grid grid-cols-7 gap-1"
            inputClassName="sr-only"
            textClassName="text-sm text-inherit"
            getItemClassName={(_item, isSelected) => `aspect-square cursor-pointer justify-center rounded-md border text-sm ${
              isSelected
                ? 'border-blue-600 bg-blue-600 text-white'
                : 'border-gray-200 bg-white hover:bg-blue-50'
            }`}
            getItemStyle={(item, index) => index === 0
              ? { gridColumnStart: (dateRange.startDate!.getUTCDay() + Number(item.id) - 1) % 7 + 1 }
              : undefined}
          />
        </div>
      ) : (
        <CheckboxList
          items={calendarItems}
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
