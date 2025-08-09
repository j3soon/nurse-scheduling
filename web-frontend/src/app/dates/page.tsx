// The date management page for Tab "1. Dates"
'use client';

import { useState } from 'react';
import { FiAlertCircle } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import ItemGroupEditorPage from '@/components/ItemGroupEditorPage';
import ToggleButton from '@/components/ToggleButton';
import { Mode } from '@/constants/modes';
import { DateRange, DataType } from '@/types/scheduling';

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
  // Error messages for start date and end date
  const [errors, setErrors] = useState<{[key: string]: string}>({});

  // Helper functions to convert between Date and string for form inputs
  const dateToString = (date?: Date): string => {
    return date ? date.toISOString().split('T')[0] : '';
  };

  const stringToDate = (dateStr: string): Date | undefined => {
    return dateStr ? new Date(dateStr) : undefined;
  };

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
                  day: 'numeric'
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
                  day: 'numeric'
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
              onChange={(e) => setDraft(prev => ({ ...prev, startDate: stringToDate(e.target.value) }))}
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
              onChange={(e) => setDraft(prev => ({ ...prev, endDate: stringToDate(e.target.value) }))}
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
