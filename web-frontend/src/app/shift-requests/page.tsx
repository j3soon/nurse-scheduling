// The shift requests management page for Tab "5. Shift Requests"
'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { FiHelpCircle, FiEdit2, FiAlertCircle } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { ShiftRequestPreference, SHIFT_REQUEST } from '@/types/scheduling';
import ShiftPreferenceEditor from '@/components/ShiftPreferenceEditor';
import ToggleButton from '@/components/ToggleButton';
import { getWeightDisplayLabel, parseWeightValue, isValidWeightValue } from '@/utils/numberParsing';
import { ERROR_SHOULD_NOT_HAPPEN } from '@/constants/errors';
import { ALL } from '@/utils/keywords';

export default function ShiftRequestsPage() {
  const {
    dateData,
    peopleData,
    shiftTypeData,
    getPreferencesByType,
    updatePreferencesByType,
    addPersonHistory,
    updatePersonHistory,
  } = useSchedulingData();

  // Get shift request preferences from the flattened preferences
  const shiftRequestPreferences = getPreferencesByType<ShiftRequestPreference>(SHIFT_REQUEST);
  const updateShiftRequestPreferences = (newPrefs: ShiftRequestPreference[]) =>
    updatePreferencesByType(SHIFT_REQUEST, newPrefs);

  const [showInstructions, setShowInstructions] = useState(false);
  const [isAddMode, setIsAddMode] = useState(false);
  const [addFormData, setAddFormData] = useState<{
    shiftType: string;
    weight: number | string;
  }>({
    shiftType: '',
    weight: 0,
  });
  const [errors, setErrors] = useState<{[key: string]: string}>({});
  const [editorState, setEditorState] = useState<{
    isOpen: boolean;
    personId: string;
    dateId: string;
  }>({
    isOpen: false,
    personId: '',
    dateId: '',
  });

  const [historyEditState, setHistoryEditState] = useState<{
    isOpen: boolean;
    personId: string;
    historyIndex: number;
  }>({
    isOpen: false,
    personId: '',
    historyIndex: -1,
  });

  enum SelectedCellType {
    PREFERENCE,
    HISTORY,
  }

  const isMultiSelectDragRef = useRef(false);

  // Add event listener for mouse up outside the component to end drag selection
  useEffect(() => {
    const handleGlobalMouseUp = () => {
      // End multi-select drag
      isMultiSelectDragRef.current = false;
      document.body.style.userSelect = '';
    };

    window.addEventListener('mouseup', handleGlobalMouseUp);
    // Cleanup event listener
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp);
      document.body.style.userSelect = '';
    };
  }, []);

  const resetForm = () => {
    setAddFormData({
      shiftType: '',
      weight: 0,
    });
    setErrors({});
  };

  const handleStartAdd = () => {
    resetForm();
    setIsAddMode(true);
  };

  const handleCancel = () => {
    setIsAddMode(false);
    resetForm();
  };

  const validateWeight = (): boolean => {
    const newErrors: {[key: string]: string} = {};

    if (!isValidWeightValue(addFormData.weight)) {
      newErrors.weight = 'Weight must be a valid number, Infinity, or -Infinity';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Compute the history columns count (max history length + 1)
  const historyColumnsCount = Math.max(
    0,
    ...peopleData.items.map(person => person.history?.length || 0)
  ) + 1;

  // Helper function to get all shift types (items and groups combined)
  const getAllShiftTypes = () => {
    return [...shiftTypeData.items, ...shiftTypeData.groups];
  };

  // Helper function to create combined date entries (All Days + regular dates)
  const getCombinedDateEntries = () => {
    const allDaysEntry = { id: ALL, description: 'Group containing all dates' };
    return [allDaysEntry, ...dateData.items];
  };

  // Helper function to get shift preferences for a person-date combination
  const getShiftPreferences = (personId: string, dateId: string): ShiftRequestPreference[] => {
    return shiftRequestPreferences.filter(
      p => p.person[0] === personId && p.date.includes(dateId)
    );
  };

  // Helper function to update shift preferences for a person-date combination
  const updateShiftPreferences = (personId: string, dateId: string, preferences: { shiftTypeId: string; weight: number }[]) => {
    // Remove the date ID to update from the person's preferences
    let filteredPreferences = shiftRequestPreferences.map(pref => {
      if (pref.person[0] === personId) {
        return {
          ...pref,
          date: pref.date.filter(id => id !== dateId),
        };
      }
      return pref;
    });

    // Add the date ID to update to the person's preferences
    for (const preference of preferences) {
      const existingPreference = filteredPreferences.find(
        p => p.person[0] === personId &&
        p.shiftType[0] === preference.shiftTypeId &&
        p.weight === preference.weight
      );
      if (existingPreference) {
        existingPreference.date.push(dateId);
      } else {
        filteredPreferences.push({
          type: SHIFT_REQUEST,
          person: [personId],
          date: [dateId],
          shiftType: [preference.shiftTypeId],
          weight: preference.weight,
        });
      }
    }

    // Remove preferences with empty date
    filteredPreferences = filteredPreferences.filter(p => p.date.length > 0);

    updateShiftRequestPreferences(filteredPreferences);
  };

  // Helper function to get visual representation of preferences
  const getPreferenceDisplay = (personId: string, dateId: string) => {
    const preferences = getShiftPreferences(personId, dateId);
    if (preferences.length === 0) return null;

    // Sort preferences by magnitude (highest first), then by weight (positive first), then by shift type ID
    const sortedPreferences = preferences.sort((a, b) => {
      const magA = Math.abs(a.weight);
      const magB = Math.abs(b.weight);
      if (magB !== magA) {
        return magB - magA;
      }
      if (b.weight !== a.weight) {
        return b.weight - a.weight;
      }
      // Compare shift_type indices in shiftTypeData.items
      const indexA = getAllShiftTypes().findIndex(st => a.shiftType[0] === st.id);
      const indexB = getAllShiftTypes().findIndex(st => b.shiftType[0] === st.id);
      if (indexA < indexB) return -1;
      if (indexA > indexB) return 1;
      return 0;
    });
    // Set cell color based on all weights
    let cellColor = 'bg-yellow-100 border-yellow-400';
    let textColor = 'text-yellow-800';
    if (preferences.every(p => p.weight > 0)) {
      cellColor = 'bg-green-100 border-green-400';
      textColor = 'text-green-800';
    } else if (preferences.every(p => p.weight < 0)) {
      cellColor = 'bg-red-100 border-red-400';
      textColor = 'text-red-800';
    }

    return {
      preferences: sortedPreferences,
      color: cellColor,
      textColor: textColor
    };
  };

  const openEditor = (personId: string, dateId: string) => {
    setEditorState({
      isOpen: true,
      personId,
      dateId,
    });
  };

  const closeEditor = () => {
    setEditorState({
      isOpen: false,
      personId: '',
      dateId: '',
    });
  };

  const handleSavePreferences = (preferences: { shiftTypeId: string; weight: number }[]) => {
    updateShiftPreferences(editorState.personId, editorState.dateId, preferences);
  };

  const handleCellMouseEnter = (selectedCellType: SelectedCellType, personId: string, identifier: string | number) => {
    if (isAddMode && isMultiSelectDragRef.current) {
      if (selectedCellType === SelectedCellType.PREFERENCE) {
        _handleCellSet(personId, identifier as string);
      } else if (selectedCellType === SelectedCellType.HISTORY) {
        handleHistoryCellClickInternal(personId, identifier as number);
      }
    }
  };

  const handleCellMouseDown = (selectedCellType: SelectedCellType, personId: string, identifier: string | number) => {
    isMultiSelectDragRef.current = true;
    if (isAddMode) {
      if (selectedCellType === SelectedCellType.PREFERENCE) {
        _handleCellSet(personId, identifier as string);
      } else if (selectedCellType === SelectedCellType.HISTORY) {
        handleHistoryCellClickInternal(personId, identifier as number);
      }
    }
    document.body.style.userSelect = 'none';
  };

  const handleCellMouseUp = () => {
    // End multi-select drag
    isMultiSelectDragRef.current = false;
    document.body.style.userSelect = '';
  };

  const _handleCellSet = (personId: string, dateId: string) => {
    if (isAddMode) {
      // In add mode, update the preferences with the form data
      // If no shift type is selected, clear all preferences for this person-date combination
      if (!addFormData.shiftType) {
        updateShiftPreferences(personId, dateId, []);
        return;
      }

      // Validate weight before proceeding
      if (!validateWeight()) {
        return;
      }

      // Get current preferences for this person-date combination
      const currentPreferences = getShiftPreferences(personId, dateId);

      // Convert to the format expected by updateShiftPreferences
      const updatedPreferences = currentPreferences.map(pref => ({
        shiftTypeId: pref.shiftType[0],
        weight: pref.weight
      }));

      // Check if there's already a preference for this shift type
      const existingIndex = updatedPreferences.findIndex(pref => pref.shiftTypeId[0] === addFormData.shiftType);

      // Use the parseWeightValue helper to consistently parse the weight
      const weightValue = addFormData.weight as number; // We know it's valid from validateWeight()

      if (existingIndex >= 0) {
        // Update existing preference
        if (weightValue === 0) {
          // Remove preference if weight is 0
          updatedPreferences.splice(existingIndex, 1);
        } else {
          updatedPreferences[existingIndex].weight = weightValue;
        }
      } else {
        // Add new preference (only if weight is not 0)
        if (weightValue !== 0) {
          updatedPreferences.push({
            shiftTypeId: addFormData.shiftType,
            weight: weightValue
          });
        }
      }
      // Apply the changes
      updateShiftPreferences(personId, dateId, updatedPreferences);
    }
  };

  const handleCellClick = (personId: string, dateId: string) => {
    if (isAddMode) {
      _handleCellSet(personId, dateId);
    } else {
      openEditor(personId, dateId);
    }
  };

  const handleHistoryCellClickInternal = (personId: string, historyIndex: number) => {
    if (isAddMode) {
      // In add mode, directly update the history cell
      const person = peopleData.items.find(p => p.id === personId);
      if (!person) {
        console.error(`Person ${personId} not found. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }

      const currentHistory = person.history!;
      const offset = historyColumnsCount - currentHistory.length;

      // If no shift type is selected (Clear mode), clear the history position
      if (!addFormData.shiftType) {
        // If targeting a position after the actual history (empty history cells on the left)
        if (historyIndex >= offset) {
          const position = historyIndex - offset;
          updatePersonHistory(personId, position);
        }
      } else {
        if (!shiftTypeData.items.find(st => st.id === addFormData.shiftType)) {
          // Cannot set history to a shift type group.
          console.warn(`Cannot set history to a shift type group.`);
          return;
        }
        if (historyIndex < offset) {
          // If targeting a position before the actual history, add a new history entry
          addPersonHistory(personId, addFormData.shiftType);
        } else {
          // If targeting a position after the actual history, update the history entry
          const position = historyIndex - offset;
          updatePersonHistory(personId, position, addFormData.shiftType);
        }
      }
    }
  };

  const getHistoryValue = (history: string[], columnIndex: number): string => {
    const offset = historyColumnsCount - history.length;  // Note that we always have one extra column for the history
    if (columnIndex < offset) return '';
    return history[columnIndex - offset];
  };

  const openHistoryEditor = (personId: string, historyIndex: number) => {
    setHistoryEditState({
      isOpen: true,
      personId,
      historyIndex,
    });
  };

  const closeHistoryEditor = () => {
    setHistoryEditState({
      isOpen: false,
      personId: '',
      historyIndex: -1,
    });
  };

  const handleSaveHistory = (shiftTypeId: string) => {
    const person = peopleData.items.find(p => p.id === historyEditState.personId);
    if (!person) {
      console.error(`Person ${historyEditState.personId} not found. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }

    const currentHistory = person.history!;
    const offset = historyColumnsCount - currentHistory.length;

    // If targeting a position before the actual history (empty history cells on the left)
    if (historyEditState.historyIndex < offset) {
      if (shiftTypeId !== '') {
        addPersonHistory(historyEditState.personId, shiftTypeId);
      } // else do nothing
    } else {
      const position = historyEditState.historyIndex - offset;
      if (shiftTypeId !== '') {
        updatePersonHistory(historyEditState.personId, position, shiftTypeId);
      } else {
        updatePersonHistory(historyEditState.personId, position);
      }
    }
    closeHistoryEditor();
  };

  const handleHistoryCellClick = (personId: string, historyIndex: number) => {
    if (isAddMode) {
      handleHistoryCellClickInternal(personId, historyIndex);
    } else {
      openHistoryEditor(personId, historyIndex);
    }
  };

  // Instructions for the help component
  const instructions = [
    "This table shows shift preferences for each person on each date",
    "History columns (H-1, H-2, etc.) show previous shift types assigned to each person",
    "Click on any history cell to set or edit shift types for that time period",
    "Each row represents a person, followed by their history, then date columns",
    "The 'All Days' column allows you to set preferences that apply to all days for each person",
    "Click on any cell to set shift preferences with weights for different shift types",
    "In 'Quick Add Preference' mode, you can drag across multiple cells to quickly apply the same preference",
    "Green cells indicate positive preferences (wants this shift type)",
    "Red cells indicate negative preferences (wants to avoid this shift type)",
    "Yellow cells indicate a mix of positive and negative preferences",
    "The displayed shift type prioritizes the one with the strongest preference or avoidance",
    "Use the navigation tabs or keyboard shortcuts to move between pages"
  ];



  // Check if we have the required data
  const hasRequiredData = (dateData.range?.startDate && dateData.range?.endDate && dateData.items.length > 0 && peopleData.items.length > 0 && (shiftTypeData.items.length > 0 || shiftTypeData.groups.length > 0));

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-800">Shift Requests</h1>
          {instructions.length > 0 && (
            <button
              onClick={() => setShowInstructions(!showInstructions)}
              className="text-gray-500 hover:text-gray-700 transition-colors"
              title="Toggle instructions"
            >
              <FiHelpCircle className="h-6 w-6" />
            </button>
          )}
        </div>
        <div className="flex gap-4">
          <ToggleButton
            label="Quick Add Preference"
            isToggled={isAddMode}
            onToggle={() => {
              if (isAddMode) {
                handleCancel();
              } else {
                handleStartAdd();
              }
            }}
          />
        </div>
      </div>

      {showInstructions && instructions.length > 0 && (
        <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h3 className="text-lg font-medium text-blue-800 mb-3">Instructions</h3>
          <ul className="space-y-2 text-sm text-blue-700">
            {instructions.map((instruction, index) => (
              <li key={index}>• {instruction}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Show appropriate message if data is missing */}
      {!hasRequiredData && (
        <div className="text-center">
          <div className="text-sm text-gray-500 italic p-4 text-center border border-gray-200 rounded-lg bg-gray-50">
            {(!dateData.range?.startDate || !dateData.range?.endDate || dateData.items.length === 0) ? (
              <>
                Please set up your dates first by visiting the{' '}
                <Link href="/dates" className="text-blue-600 hover:text-blue-800 underline">
                  Dates
                </Link>{' '}
                tab.
              </>
            ) : peopleData.items.length === 0 ? (
              <>
                Please set up your people first by visiting the{' '}
                <Link href="/people" className="text-blue-600 hover:text-blue-800 underline">
                  People
                </Link>{' '}
                tab.
              </>
            ) : (
              <>
                Please set up your shift types first by visiting the{' '}
                <Link href="/shift-types" className="text-blue-600 hover:text-blue-800 underline">
                  Shift Types
                </Link>{' '}
                tab.
              </>
            )}
          </div>
        </div>
      )}

      {hasRequiredData && isAddMode && (
        <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
          <div className="px-6 py-4">
            <h2 className="text-lg font-semibold mb-4 text-gray-800">
              Add Shift Preference
            </h2>

            <div className="space-y-6">
              {/* Shift Type Selection */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Shift Type
                </label>
                <div className="flex flex-wrap">
                  {/* Clear selection option */}
                  <label
                    className="inline-flex items-center px-1 py-1"
                    title="Clear selection - clicking cells will clear all preferences"
                  >
                    <input
                      type="radio"
                      name="shiftType"
                      value=""
                      checked={addFormData.shiftType === ''}
                      onChange={(e) => setAddFormData(prev => ({ ...prev, shiftType: e.target.value }))}
                      className="form-checkbox h-4 w-4 text-blue-600"
                    />
                    <span className="ml-2 text-sm text-gray-700 italic">
                      Clear
                    </span>
                  </label>
                  {getAllShiftTypes().map((shiftType) => (
                    <label
                      key={shiftType.id}
                      className="inline-flex items-center px-1 py-1"
                      title={shiftType.description}
                    >
                      <input
                        type="radio"
                        name="shiftType"
                        value={shiftType.id}
                        checked={addFormData.shiftType === shiftType.id}
                        onChange={(e) => setAddFormData(prev => ({ ...prev, shiftType: e.target.value }))}
                        className="form-checkbox h-4 w-4 text-blue-600"
                      />
                      <span className="ml-2 text-sm text-gray-700">
                        {shiftType.id}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Weight Input */}
              <div>
                <label htmlFor="weight" className="block text-sm font-medium text-gray-700 mb-2">
                  Weight (priority)
                </label>
                <input
                  type="text"
                  id="weight"
                  value={addFormData.weight}
                  onChange={(e) => {
                    setAddFormData(prev => ({
                      ...prev,
                      weight: parseWeightValue(e.target.value)
                    }));
                    // Clear error when user starts typing
                    if (errors.weight) {
                      setErrors(prev => ({ ...prev, weight: '' }));
                    }
                  }}
                  className={`block w-full px-4 py-2 text-sm text-gray-900 bg-white border rounded-lg shadow-sm transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 placeholder-gray-400 hover:border-gray-400 ${
                    errors.weight
                      ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
                      : 'border-gray-300 focus:border-blue-500 focus:ring-blue-200'
                  }`}
                  placeholder="Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)"
                />
                {errors.weight && (
                  <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {errors.weight}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Show main content only if we have all required data */}
      {hasRequiredData && (
        <>
          {/* Shift Requests Table */}
          <div className="bg-white shadow-md rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800">Shift Preference Matrix</h3>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                {/* Header */}
                <thead className="bg-gray-50">
                  <tr>
                    <th className="sticky left-0 z-10 bg-gray-50 px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-r border-gray-200 shadow-sm">
                      People
                    </th>
                    {/* History columns */}
                    {Array.from({ length: historyColumnsCount }, (_, index) => (
                      <th
                        key={`history-${index}`}
                        className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider border-r border-gray-200"
                        title={`History position H-${historyColumnsCount - index}`}
                      >
                        <div className="whitespace-nowrap">H-{historyColumnsCount - index}</div>
                      </th>
                    ))}
                    {getCombinedDateEntries().map((dateEntry) => (
                      <th
                        key={dateEntry.id || 'all-days'}
                        className={`px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider ${
                          dateEntry.id === ALL
                            ? 'border-l-2 border-r-2 border-l-blue-200 border-r-blue-200'
                            : ''
                        }`}
                        title={dateEntry.id === ALL ? 'Set preferences that apply to all days' : dateEntry.description || dateEntry.id}
                      >
                        <div className="whitespace-nowrap">{dateEntry.id === ALL ? 'All Days' : dateEntry.id}</div>
                      </th>
                    ))}
                  </tr>
                </thead>

                {/* Body */}
                <tbody className="bg-white divide-y divide-gray-200">
                  {peopleData.items.map((person) => (
                    <tr key={person.id} className="hover:bg-gray-50">
                      {/* Person column */}
                      <td className="sticky left-0 z-10 bg-white px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 border-r border-gray-200 shadow-sm">
                        <div>
                          <div>{person.id}</div>
                          {person.description && (
                            <div className="text-gray-500 text-xs">{person.description}</div>
                          )}
                        </div>
                      </td>
                      {/* History columns */}
                      {Array.from({ length: historyColumnsCount }, (_, index) => {
                        const historyValue = getHistoryValue(person.history!, index);
                        const offset = historyColumnsCount - person.history!.length;

                        // Only show one extra clickable cell, others are empty non-clickable
                        const isClickable = index >= offset - 1;

                        return (
                          <td
                            key={`${person.id}-history-${index}`}
                            className={`px-2 py-2 text-center border-r border-gray-200 ${
                              isClickable
                                ? 'bg-amber-50 cursor-pointer hover:bg-amber-100 transition-colors duration-150'
                                : 'bg-gray-50'
                            }`}
                            onClick={() => isClickable && !isAddMode && handleHistoryCellClick(person.id, index)}
                            onMouseEnter={() => isClickable && handleCellMouseEnter(SelectedCellType.HISTORY, person.id, index)}
                            onMouseDown={() => isClickable && handleCellMouseDown(SelectedCellType.HISTORY, person.id, index)}
                            onMouseUp={() => isClickable && handleCellMouseUp()}
                            title={isClickable ? (isAddMode
                              ? `Click or drag to set history position H-${historyColumnsCount - index} to ${addFormData.shiftType || 'clear'}`
                              : `Click to edit history position H-${historyColumnsCount - index}`) : ''}
                          >
                            <div className={`text-sm font-medium ${isClickable ? 'text-gray-900' : 'text-gray-300'}`}>
                              {!isClickable ? '' : (historyValue || '—')}
                            </div>
                          </td>
                        );
                      })}
                      {/* All days and per-date columns */}
                      {getCombinedDateEntries().map((dateEntry) => {
                        const display = getPreferenceDisplay(person.id, dateEntry.id);

                        return (
                          <td
                            key={`${person.id}-${dateEntry.id || 'all-days'}`}
                            className={`px-1 py-1 text-center cursor-pointer hover:bg-gray-50 transition-colors duration-150 ${
                              dateEntry.id === ALL ? 'border-l-2 border-r-2 border-l-blue-200 border-r-blue-200' : ''
                            }`}
                            onClick={() => !isAddMode && handleCellClick(person.id, dateEntry.id)}
                            onMouseEnter={() => handleCellMouseEnter(SelectedCellType.PREFERENCE, person.id, dateEntry.id)}
                            onMouseDown={() => handleCellMouseDown(SelectedCellType.PREFERENCE, person.id, dateEntry.id)}
                            onMouseUp={() => handleCellMouseUp()}
                          >
                            <div
                              className={`min-w-16 w-auto h-12 mx-auto rounded-lg border-2 transition-all duration-200 flex flex-col items-center justify-center gap-0 shadow-sm hover:shadow-md ${
                                display
                                  ? `${display.color} ${display.textColor} hover:scale-105`
                                  : 'border-gray-300 hover:border-gray-400 hover:bg-gray-50'
                              }`}
                              title={dateEntry.id === ALL
                                ? (isAddMode
                                  ? `Click or drag to update all-days preferences for ${person.id}`
                                  : `Click to update all-days preferences for ${person.id}`)
                                : (isAddMode
                                  ? `Click or drag to update preferences for ${person.id} on date ${dateEntry.id}`
                                  : `Click to update preferences for ${person.id} on date ${dateEntry.id}`)}
                            >
                              {display && (() => {
                                const maxVisible = display.preferences.length <= 3 ? 3 : 2; // Show all if 3 or fewer, otherwise show 2
                                const visiblePreferences = display.preferences.slice(0, maxVisible);
                                const remainingCount = display.preferences.length - maxVisible;

                                return (
                                  <>
                                    {visiblePreferences.map((pref, index) => {
                                      return (
                                        <div key={index} className="text-xs font-semibold leading-tight px-0.5 whitespace-nowrap">
                                          {pref.shiftType} ({getWeightDisplayLabel(pref.weight)})
                                        </div>
                                      );
                                    })}
                                    {remainingCount > 0 && (
                                      <div className="text-[10px] font-medium opacity-75 px-0.5">
                                        +{remainingCount} more
                                      </div>
                                    )}
                                  </>
                                );
                              })()}
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Current Shift Requests */}
          <div className="mt-6 bg-blue-50 shadow-md rounded-lg overflow-hidden border border-blue-200">
            <div className="px-6 py-4 border-b border-blue-200 bg-blue-100">
              <h3 className="text-lg font-semibold text-blue-800">Current Shift Requests</h3>
              <p className="text-sm text-blue-600 mt-1">Auto-computed from the preference matrix above</p>
            </div>

            {shiftRequestPreferences.length === 0 ? (
              <div className="px-6 py-8 text-center text-blue-500">
                No shift requests defined yet. Click on any cell in the matrix above to add preferences.
              </div>
            ) : (
              <div className="divide-y divide-blue-200">
                {shiftRequestPreferences.map((preference, index) => {
                  // Get person and shift type descriptions for display
                  const person = peopleData.items.find(p => p.id === preference.person[0]);
                  const shiftType = getAllShiftTypes().find(st => st.id === preference.shiftType[0]);

                  return (
                    <div key={index} className="px-6 py-5 bg-blue-50">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-3 text-sm text-blue-600">
                            <div>
                              <span className="font-medium">Person:</span>{' '}
                              <span className="text-blue-900">{preference.person}</span>
                              {person?.description && (
                                <div className="text-xs text-blue-500 mt-1">{person.description}</div>
                              )}
                            </div>
                            <div>
                              <span className="font-medium">Date:</span>{' '}
                              <span className="text-blue-900">
                                {preference.date[0] === ALL ? 'All Days' : preference.date.join(', ')}
                              </span>
                              {preference.date[0] === ALL ? (
                                <div className="text-xs text-blue-500 mt-1">Applies to all days</div>
                              ) : null}
                            </div>
                            <div>
                              <span className="font-medium">Shift Type:</span>{' '}
                              <span className="text-blue-900">{preference.shiftType}</span>
                              {shiftType?.description && (
                                <div className="text-xs text-blue-500 mt-1">{shiftType.description}</div>
                              )}
                            </div>
                            <div>
                              <span className="font-medium">Weight:</span>{' '}
                              <span className={`font-medium ${preference.weight > 0 ? 'text-green-600' : preference.weight < 0 ? 'text-red-600' : 'text-blue-900'}`}>
                                {preference.weight > 0 ? '+' : ''}{preference.weight}
                              </span>
                              <div className="text-xs text-blue-500 mt-1">
                                {preference.weight > 0 ? 'Wants this shift' : preference.weight < 0 ? 'Wants to avoid' : 'Neutral'}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Current People History */}
          <div className="mt-6 bg-blue-50 shadow-md rounded-lg overflow-hidden border border-blue-200">
            <div className="px-6 py-4 border-b border-blue-200 bg-blue-100">
              <h3 className="text-lg font-semibold text-blue-800">Current People History</h3>
              <p className="text-sm text-blue-600 mt-1">Auto-computed from the history matrix above</p>
            </div>

            {peopleData.items.every(person => person.history!.length === 0) ? (
              <div className="px-6 py-8 text-center text-blue-500">
                No history entries defined yet. Click on any history cell in the matrix above to add entries.
              </div>
            ) : (
              <div className="divide-y divide-blue-200">
                {peopleData.items.map((person) => {
                  if (!person.history || person.history.length === 0) return null;

                  return (
                    <div key={person.id} className="px-6 py-5 bg-blue-50">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="mb-3">
                            <div className="text-sm font-medium text-blue-800">
                              Person: <span className="text-blue-900">{person.id}</span>
                            </div>
                            {person.description && (
                              <div className="text-xs text-blue-500 mt-1">{person.description}</div>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-x-6 gap-y-3">
                            {person.history.map((shiftTypeId, index) => {
                              const shiftType = getAllShiftTypes().find(st => st.id === shiftTypeId);
                              const historyPosition = person.history!.length - index;

                              return (
                                <div key={index} className="text-sm text-blue-600">
                                  <span className="font-medium">H-{historyPosition}:</span>{' '}
                                  <span className="text-blue-900">{shiftTypeId}</span>
                                  {shiftType?.description && (
                                    <div className="text-xs text-blue-500 mt-1">{shiftType.description}</div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                        <div className="flex justify-end space-x-2 ml-4">
                          <button
                            onClick={() => openHistoryEditor(person.id, historyColumnsCount - person.history!.length)}
                            className="text-blue-600 hover:text-blue-900 flex items-center gap-1 text-sm"
                          >
                            <FiEdit2 className="h-4 w-4" />
                            Edit
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}

      {/* Shift Preference Editor Modal */}
      <ShiftPreferenceEditor
        isOpen={editorState.isOpen}
        onClose={closeEditor}
        onSave={handleSavePreferences}
        personId={editorState.personId}
        dateId={editorState.dateId}
        shiftTypes={getAllShiftTypes()}
        initialPreferences={getShiftPreferences(editorState.personId, editorState.dateId).map(p => ({ shiftTypeId: p.shiftType[0], weight: p.weight }))}
      />

      {/* History Editor Modal */}
      {historyEditState.isOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-sm w-full mx-4">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800">
                Edit History - {historyEditState.personId}
              </h3>
              <p className="text-sm text-gray-600 mt-1">
                Position H-{historyColumnsCount - historyEditState.historyIndex}
              </p>
            </div>

            <div className="px-6 py-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Shift Type:
              </label>
              <select
                value={(() => {
                  const person = peopleData.items.find(p => p.id === historyEditState.personId);
                  if (!person) {
                    console.error(`Person ${historyEditState.personId} not found. ${ERROR_SHOULD_NOT_HAPPEN}`);
                    return '';
                  }
                  return getHistoryValue(person.history!, historyEditState.historyIndex);
                })()}
                onChange={(e) => handleSaveHistory(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                autoFocus
              >
                <option value="">-- Clear --</option>
                {shiftTypeData.items.map((shiftType) => (
                  <option key={shiftType.id} value={shiftType.id}>
                    {shiftType.id} - {shiftType.description}
                  </option>
                ))}
              </select>
            </div>

            <div className="px-6 py-4 border-t border-gray-200 flex justify-end">
              <button
                onClick={closeHistoryEditor}
                className="px-4 py-2 text-gray-600 hover:text-gray-800 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
