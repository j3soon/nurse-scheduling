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

export default function DatePage() {
  const {
    updateDateRange,
    dateData,
    // Get functions to pass as props
    addItem,
    addGroup,
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

  // Helper function to check if date range represents a full month
  const isFullMonth = (startDate?: Date, endDate?: Date): boolean => {
    if (!startDate || !endDate) return false;

    // Check if start date is the first day of the month
    const isFirstDay = startDate.getUTCDate() === 1;

    // Check if end date is the last day of the same month/year
    const lastDayOfMonth = new Date(Date.UTC(startDate.getUTCFullYear(), startDate.getUTCMonth() + 1, 0));
    const isLastDay = endDate.getUTCDate() === lastDayOfMonth.getUTCDate() &&
                      endDate.getUTCMonth() === startDate.getUTCMonth() &&
                      endDate.getUTCFullYear() === startDate.getUTCFullYear();

    return isFirstDay && isLastDay;
  };

  const warnings = useMemo<{[key: string]: string}>(() => {
    if (mode !== Mode.DATE_RANGE_EDITING) {
      return {};
    }

    const newWarnings: {[key: string]: string} = {};
    if (!isFullMonth(draft.startDate, draft.endDate)) {
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
      <div className="space-y-4">
        {/* Start Date and End Date */}
        <div className="flex gap-4">
          <div className="flex-1">
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
              className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                errors.startDate ? 'border-red-500' : 'border-gray-300'
              }`}
            />
            {errors.startDate && (
              <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                <FiAlertCircle className="h-4 w-4" />
                {errors.startDate}
              </p>
            )}
          </div>

          <div className="flex-1">
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
              className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                errors.endDate ? 'border-red-500' : 'border-gray-300'
              }`}
            />
            {errors.endDate && (
              <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                <FiAlertCircle className="h-4 w-4" />
                {errors.endDate}
              </p>
            )}
          </div>
        </div>

        {/* Warning message for non-full month selection */}
        {Object.entries(warnings).map(([warningKey, warningMessage]) => (
          <div key={warningKey} className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
            <p className="text-sm text-yellow-800 flex items-center gap-2">
              <FiAlertCircle className="h-4 w-4 text-yellow-600" />
              <span className="font-medium">Warning:</span>
              {warningMessage}
            </p>
          </div>
        ))}

        <div className="rounded-md border border-gray-200 bg-gray-50 p-4">
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={shouldImportTaiwanHolidays && isTaiwanHolidayImportSupported}
              disabled={!isTaiwanHolidayImportSupported}
              onChange={(e) => setShouldImportTaiwanHolidays(e.target.checked)}
              className="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
            />
            <div>
              <div className="text-sm font-medium text-gray-900">
                Import Taiwan holidays into date groups
              </div>
              <p className="mt-1 text-sm text-gray-600">
                Saving with this enabled will create or overwrite normal editable Taiwan holiday date groups once, including WORKDAY and FREEDAY.
              </p>
              {!isTaiwanHolidayImportSupported && (
                <p className="mt-2 text-sm text-amber-700">
                  Available only when the selected date range stays within {taiwanHolidaySupportLabel}.
                </p>
              )}
              {isTaiwanHolidayImportSupported && includedTaiwanHolidays.length > 0 && (
                <div className="mt-3 rounded-md border border-gray-200 bg-white p-3">
                  <div className="text-sm font-medium text-gray-900">
                    Included holiday entries
                  </div>
                  <div className="mt-2 max-h-56 space-y-2 overflow-y-auto pr-1">
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
                </div>
              )}
            </div>
          </label>
        </div>

        {/* Action Buttons */}
        <div className="flex justify-end gap-3 pt-4">
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
      updateItem={updateItem}
      updateGroup={updateGroup}
      deleteItem={deleteItem}
      deleteGroup={deleteGroup}
      removeItemFromGroup={removeItemFromGroup}
      reorderItems={reorderItems}
      reorderGroups={reorderGroups}
      filterItemGroups={x => x}
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
