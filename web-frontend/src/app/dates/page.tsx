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

// The date management page for Tab "1. Dates"
'use client';

import { useMemo, useState } from 'react';
import { FiAlertCircle } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import DateRangeCalendarPicker from '@/components/DateRangeCalendarPicker';
import { DateGroupMemberSelector } from '@/components/DateGroupMemberSelector';
import ItemGroupEditorPage from '@/components/ItemGroupEditorPage';
import ToggleButton from '@/components/ToggleButton';
import { Mode } from '@/constants/modes';
import { DateRange, DataType } from '@/types/scheduling';
import {
  getTaiwanHolidaySupportLabel,
  getTaiwanHolidayEntriesInRange,
  includesUnimportedTaiwanLaborDay,
  isTaiwanHolidayRangeSupported,
} from '@/utils/taiwanHolidays';
import { useTabSwitchWarning } from '@/utils/unsavedEditingState';
import { isFullCalendarMonth } from '@/utils/calendar';

export default function DatePage() {
  const {
    updateDateRange,
    dateData,
    // Get functions to pass as props
    addItem,
    addGroup,
    duplicateItem,
    duplicateGroup,
    updateItem,
    updateGroup,
    deleteItem,
    deleteGroup,
    removeItemFromGroup,
    reorderItems,
    reorderGroups,
  } = useSchedulingData();

  // Mode state for date range and item group editing
  const [mode, setMode] = useState<Mode>(Mode.NORMAL);
  const [draft, setDraft] = useState<DateRange>({
    startDate: undefined,
    endDate: undefined,
  });
  const [shouldImportTaiwanHolidays, setShouldImportTaiwanHolidays] = useState(true);
  const [activeCalendarEndpoint, setActiveCalendarEndpoint] = useState<'start' | 'end'>('start');
  // Error messages for start date and end date
  const [errors, setErrors] = useState<{[key: string]: string}>({});
  // Helper functions to convert between Date and string for form inputs
  const dateToString = (date?: Date): string => {
    return date ? date.toISOString().split('T')[0] : '';
  };

  const stringToDate = (dateStr: string): Date | undefined => {
    return dateStr ? new Date(dateStr) : undefined;
  };
  const formatHolidayWeekday = (dateStr: string): string => {
    return new Date(dateStr).toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' });
  };
  const shouldShowHolidayTypeBadge = (dateStr: string, isFreeday: boolean): boolean => {
    const weekday = new Date(dateStr).getUTCDay();
    const isWeekend = weekday === 0 || weekday === 6;
    return isWeekend ? !isFreeday : isFreeday;
  };
  const isTaiwanHolidayImportSupported = useMemo(
    () => isTaiwanHolidayRangeSupported(draft),
    [draft]
  );
  useTabSwitchWarning(mode === Mode.DATE_RANGE_EDITING);

  const warnings = useMemo<{[key: string]: string}>(() => {
    if (mode !== Mode.DATE_RANGE_EDITING) {
      return {};
    }

    const newWarnings: {[key: string]: string} = {};
    if (!isFullCalendarMonth(draft)) {
      newWarnings.dateRange = 'Selected dates do not represent a full month (first day to last day of the same month)';
    }
    if (shouldImportTaiwanHolidays && isTaiwanHolidayImportSupported && includesUnimportedTaiwanLaborDay(draft)) {
      newWarnings.laborDay = 'Taiwan holiday import does not include Labor Day on May 1. If needed, please manually adjust it after update.';
    }

    return newWarnings;
  }, [draft, isTaiwanHolidayImportSupported, mode, shouldImportTaiwanHolidays]);

  const taiwanHolidaySupportLabel = getTaiwanHolidaySupportLabel();
  const includedTaiwanHolidays = useMemo(
    () => getTaiwanHolidayEntriesInRange(draft).filter(
      (entry) => shouldShowHolidayTypeBadge(entry.date, entry.isFreeday)
    ),
    [draft]
  );
  const selectedDayCount = draft.startDate && draft.endDate
    ? Math.ceil((draft.endDate.getTime() - draft.startDate.getTime()) / (1000 * 60 * 60 * 24)) + 1
    : 0;

  // Instructions for the help component
  const instructions = [
    "Set the start and end dates for your scheduling period",
    "The end date must be after the start date",
    "Dates are automatically generated based on your date range",
    "Create groups to organize dates (e.g., \"Weekdays\", \"Weekends\", \"Workdays\", \"Freedays\")",
    "When enabled, updating the date range can create or overwrite editable Taiwan holiday date groups such as WORKDAY and FREEDAY",
    "Click and drag through checkboxes to quickly select multiple dates when adding or editing",
    "Drag and drop to reorder groups",
    "Double-click to edit names or descriptions",
    "Navigate using the tabs or keyboard shortcuts (1, 2, etc.) to continue setup"
  ];

  const validateForm = () => {
    const newErrors: {[key: string]: string} = {};

    if (!draft.startDate) {
      newErrors.startDate = 'Start date is required';
    }

    if (!draft.endDate) {
      newErrors.endDate = 'End date is required';
    }

    if (draft.startDate && draft.endDate && draft.startDate > draft.endDate) {
      newErrors.endDate = 'End date must be after start date';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = () => {
    if (validateForm()) {
      updateDateRange({
        startDate: draft.startDate,
        endDate: draft.endDate,
      }, {
        importTaiwanHolidays: shouldImportTaiwanHolidays && isTaiwanHolidayImportSupported,
      });
      setMode(Mode.NORMAL);
    }
  };

  const handleStartEditingDateRange = () => {
    // Toggle form visibility: if already editing date range, cancel; otherwise start editing
    if (mode === Mode.DATE_RANGE_EDITING) {
      handleCancel();
    } else {
      setMode(Mode.DATE_RANGE_EDITING);
      // Reset draft to current values
      if (dateData.range) {
        setDraft({
          startDate: dateData.range.startDate,
          endDate: dateData.range.endDate,
        });
      }
      setShouldImportTaiwanHolidays(true);
      setActiveCalendarEndpoint('start');
      setErrors({});
    }
  };

  const handleCancel = () => {
    setMode(Mode.NORMAL);
    // Reset to original values
    if (dateData.range) {
      setDraft({
        startDate: dateData.range.startDate,
        endDate: dateData.range.endDate,
      });
    }
    setShouldImportTaiwanHolidays(true);
    setActiveCalendarEndpoint('start');
    setErrors({});
  };

  // DateRange components to inject as children
  const dateRangeComponents = (
    <div>
      {/* Current Date Range Display */}
      {mode !== Mode.DATE_RANGE_EDITING && (
        <div className="mb-6 p-4 bg-white shadow-md rounded-lg">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <span className="text-sm font-medium text-gray-700">Start Date:</span>
              <div className="text-lg font-semibold text-gray-900">
                {dateData.range && dateData.range.startDate ? dateData.range.startDate.toLocaleDateString('en-US', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                  timeZone: 'UTC'
                }) : '-'}
              </div>
            </div>
            <div>
              <span className="text-sm font-medium text-gray-700">End Date:</span>
              <div className="text-lg font-semibold text-gray-900">
                {dateData.range && dateData.range.endDate ? dateData.range.endDate.toLocaleDateString('en-US', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                  timeZone: 'UTC'
                }) : '-'}
              </div>
            </div>
          </div>
          {dateData.range.startDate && dateData.range.endDate && (
            <div className="mt-3 text-sm text-blue-700">
              Duration: {Math.ceil((dateData.range.endDate.getTime() - dateData.range.startDate.getTime()) / (1000 * 60 * 60 * 24) + 1)} days
            </div>
          )}
        </div>
      )}
    </div>
  );

  // Edit Date Range Form component to inject as children
  const editDateRangeForm = mode === Mode.DATE_RANGE_EDITING && (
    <div className="mb-6 bg-white shadow-md rounded-lg p-6">
      <h3 className="text-lg font-semibold mb-4 text-gray-800">
        Set Date Range
      </h3>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(22rem,0.95fr)]">
        <div className="space-y-5">
          <section>
            <h4 className="mb-3 text-sm font-semibold text-gray-900">Date range</h4>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="startDate" className="block text-sm font-medium text-gray-700 mb-2">
                  Start Date *
                </label>
                <input
                  type="date"
                  id="startDate"
                  value={dateToString(draft.startDate)}
                  onChange={(e) => {
                    setErrors(prev => ({ ...prev, startDate: '' }));
                    setDraft(prev => ({ ...prev, startDate: stringToDate(e.target.value) }));
                  }}
                  onFocus={() => setActiveCalendarEndpoint('start')}
                  className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                    errors.startDate
                      ? 'border-red-500'
                      : activeCalendarEndpoint === 'start'
                        ? 'border-blue-500 ring-1 ring-blue-500'
                        : 'border-gray-300'
                  }`}
                />
                {errors.startDate && (
                  <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4 shrink-0" />
                    {errors.startDate}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="endDate" className="block text-sm font-medium text-gray-700 mb-2">
                  End Date *
                </label>
                <input
                  type="date"
                  id="endDate"
                  value={dateToString(draft.endDate)}
                  onChange={(e) => {
                    setErrors(prev => ({ ...prev, endDate: '' }));
                    setDraft(prev => ({ ...prev, endDate: stringToDate(e.target.value) }));
                  }}
                  onFocus={() => setActiveCalendarEndpoint('end')}
                  className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                    errors.endDate
                      ? 'border-red-500'
                      : activeCalendarEndpoint === 'end'
                        ? 'border-blue-500 ring-1 ring-blue-500'
                        : 'border-gray-300'
                  }`}
                />
                {errors.endDate && (
                  <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4 shrink-0" />
                    {errors.endDate}
                  </p>
                )}
              </div>
            </div>
            {draft.startDate && draft.endDate && (
              <p className="mt-3 text-sm text-gray-600" aria-live="polite">
                {selectedDayCount} day{selectedDayCount === 1 ? '' : 's'} selected
              </p>
            )}
          </section>

          {Object.keys(warnings).length > 0 && (
            <section className="rounded-md border border-yellow-200 bg-yellow-50 p-4" aria-labelledby="date-range-review">
              <h4 id="date-range-review" className="text-sm font-semibold text-yellow-900">
                Review
              </h4>
              <div className="mt-2 space-y-2">
                {Object.entries(warnings).map(([warningKey, warningMessage]) => (
                  <p key={warningKey} className="flex items-start gap-2 text-sm text-yellow-800">
                    <FiAlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-yellow-600" />
                    <span>{warningMessage}</span>
                  </p>
                ))}
              </div>
            </section>
          )}

          <section className="rounded-md border border-gray-200 bg-gray-50 p-4" aria-labelledby="holiday-import-heading">
            <div className="flex items-start gap-3">
              <input
                id="importTaiwanHolidays"
                type="checkbox"
                checked={shouldImportTaiwanHolidays && isTaiwanHolidayImportSupported}
                disabled={!isTaiwanHolidayImportSupported}
                onChange={(e) => setShouldImportTaiwanHolidays(e.target.checked)}
                className="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
              />
              <div className="min-w-0 flex-1">
                <label id="holiday-import-heading" htmlFor="importTaiwanHolidays" className="text-sm font-medium text-gray-900">
                  Import Taiwan holidays into date groups
                </label>
                <p className="mt-1 text-sm text-gray-600">
                  Saving with this enabled will create or overwrite normal editable Taiwan holiday date groups once, including WORKDAY and FREEDAY.
                </p>
                {!isTaiwanHolidayImportSupported && (
                  <p className="mt-2 text-sm text-amber-700">
                    Available only when the selected date range stays within {taiwanHolidaySupportLabel}.
                  </p>
                )}
                {isTaiwanHolidayImportSupported && includedTaiwanHolidays.length === 0 && (
                  <p className="mt-2 text-sm text-gray-500">No holiday changes in the selected range.</p>
                )}
                {isTaiwanHolidayImportSupported && includedTaiwanHolidays.length > 0 && (
                  <details open className="mt-3 rounded-md border border-gray-200 bg-white">
                    <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50">
                      {includedTaiwanHolidays.length} holiday {includedTaiwanHolidays.length === 1 ? 'change' : 'changes'}
                    </summary>
                    <div className="max-h-56 space-y-2 overflow-y-auto border-t border-gray-200 p-3">
                      {includedTaiwanHolidays.map((entry) => (
                        <div key={entry.date} className="rounded border border-gray-100 bg-gray-50 px-3 py-2 text-sm">
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-mono text-gray-700">{entry.date} ({formatHolidayWeekday(entry.date)})</span>
                            {shouldShowHolidayTypeBadge(entry.date, entry.isFreeday) && (
                              <span className={`rounded px-2 py-0.5 text-xs font-medium ${
                                entry.isFreeday
                                  ? 'bg-emerald-100 text-emerald-800'
                                  : 'bg-blue-100 text-blue-800'
                              }`}>
                                {entry.isFreeday ? 'FREEDAY' : 'WORKDAY'}
                              </span>
                            )}
                          </div>
                          <div className="mt-1 text-gray-600">{entry.reason}</div>
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            </div>
          </section>
        </div>

        <section className="w-full lg:justify-self-center" aria-label="Calendar date range picker">
          <DateRangeCalendarPicker
            value={draft}
            onChange={(value) => {
              setDraft(value);
              setErrors(prev => ({ ...prev, startDate: '', endDate: '' }));
            }}
            onActiveEndpointChange={setActiveCalendarEndpoint}
          />
        </section>

        {/* Action Buttons */}
        <div className="flex justify-end gap-3 border-t border-gray-200 pt-4 lg:col-span-2">
          <button
            onClick={handleCancel}
            className="px-4 py-2 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            {dateData.range ? 'Update' : 'Apply'}
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <ItemGroupEditorPage
      title="Date Management"
      instructions={instructions}
      data={dateData}
      dataType={DataType.DATES}
      itemsReadOnly={true}
      mode={mode}
      setMode={setMode}
      addItem={addItem}
      addGroup={addGroup}
      duplicateItem={duplicateItem}
      duplicateGroup={duplicateGroup}
      updateItem={updateItem}
      updateGroup={updateGroup}
      deleteItem={deleteItem}
      deleteGroup={deleteGroup}
      removeItemFromGroup={removeItemFromGroup}
      reorderItems={reorderItems}
      reorderGroups={reorderGroups}
      filterItemGroups={x => x}
      renderGroupMemberSelector={({ items, selectedIds, onToggle }) => (
        <DateGroupMemberSelector
          dateRange={dateData.range}
          items={items}
          selectedIds={selectedIds}
          onToggle={onToggle}
        />
      )}
      extraButtons={
        <ToggleButton
          label="Set Date Range"
          isToggled={mode === Mode.DATE_RANGE_EDITING}
          onToggle={handleStartEditingDateRange}
        />
      }
    >
      {dateRangeComponents}
      {editDateRangeForm}
    </ItemGroupEditorPage>
  );
}
