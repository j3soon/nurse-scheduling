// The date management page for Tab "1. Dates"
'use client';

import { useState } from 'react';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import ItemGroupEditorPage from '@/components/ItemGroupEditorPage';
import ToggleButton from '@/components/ToggleButton';
import { Mode } from '@/constants/modes';
import { DateRange } from '@/types/scheduling';

export default function DatePage() {
  const {
    dateRange,
    updateDateRange,
    dateData,
    updateDateData
  } = useSchedulingData();

  // Mode state for date range and item group editing
  const [mode, setMode] = useState<Mode>(Mode.NORMAL);
  const [draft, setDraft] = useState<DateRange>({
    startDate: '',
    endDate: '',
  });
  // Error messages for start date and end date
  const [errors, setErrors] = useState<{[key: string]: string}>({});

  // Instructions for the help component
  const instructions = [
    "Set the start and end dates for your scheduling period",
    "The end date must be after the start date",
    "Dates are automatically generated based on your date range",
    "Create groups to organize dates (e.g., \"Weekdays\", \"Weekends\", \"Workdays\", \"Freedays\")",
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

    if (draft.startDate && draft.endDate && new Date(draft.startDate) > new Date(draft.endDate)) {
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
      if (dateRange) {
        setDraft({
          startDate: dateRange.startDate || '',
          endDate: dateRange.endDate || '',
        });
      }
      setErrors({});
    }
  };

  const handleCancel = () => {
    setMode(Mode.NORMAL);
    // Reset to original values
    if (dateRange) {
      setDraft({
        startDate: dateRange.startDate || '',
        endDate: dateRange.endDate || '',
      });
    }
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
                {dateRange && dateRange.startDate ? new Date(dateRange.startDate).toLocaleDateString('en-US', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                }) : '-'}
              </div>
            </div>
            <div>
              <span className="text-sm font-medium text-gray-700">End Date:</span>
              <div className="text-lg font-semibold text-gray-900">
                {dateRange && dateRange.endDate ? new Date(dateRange.endDate).toLocaleDateString('en-US', {
                  weekday: 'long',
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                }) : '-'}
              </div>
            </div>
          </div>
          {dateRange.startDate && dateRange.endDate && (
            <div className="mt-3 text-sm text-blue-700">
              Duration: {Math.ceil((new Date(dateRange.endDate).getDate() - new Date(dateRange.startDate).getDate()) + 1)} days
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
              value={draft.startDate}
              onChange={(e) => setDraft(prev => ({ ...prev, startDate: e.target.value }))}
              className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                errors.startDate ? 'border-red-500' : 'border-gray-300'
              }`}
            />
            {errors.startDate && (
              <p className="mt-1 text-sm text-red-600">{errors.startDate}</p>
            )}
          </div>

          <div className="flex-1">
            <label htmlFor="endDate" className="block text-sm font-medium text-gray-700 mb-2">
              End Date *
            </label>
            <input
              type="date"
              id="endDate"
              value={draft.endDate}
              onChange={(e) => setDraft(prev => ({ ...prev, endDate: e.target.value }))}
              className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 ${
                errors.endDate ? 'border-red-500' : 'border-gray-300'
              }`}
            />
            {errors.endDate && (
              <p className="mt-1 text-sm text-red-600">{errors.endDate}</p>
            )}
          </div>
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
            {dateRange ? 'Update' : 'Apply'}
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
      updateData={updateDateData}
      itemLabel="Date"
      itemLabelPlural="Dates"
      itemsReadOnly={true}
      mode={mode}
      setMode={setMode}
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
