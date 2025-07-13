// The shift requests management page for Tab "5. Shift Requests"
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { FiHelpCircle, FiEdit2 } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { ShiftRequestPreference, SHIFT_REQUEST_PREFERENCE } from '@/types/scheduling';
import ShiftPreferenceEditor from '@/components/ShiftPreferenceEditor';
import { getWeightDisplayLabel } from '@/utils/numberParsing';
import { ERROR_SHOULD_NOT_HAPPEN } from '@/constants/errors';

export default function ShiftRequestsPage() {
  const {
    dateData,
    peopleData,
    shiftTypeData,
    dateRange,
    shiftRequestPreferences,
    updateShiftRequestPreferences,
    addPersonHistory,
    updatePersonHistory,
  } = useSchedulingData();

  const [showInstructions, setShowInstructions] = useState(false);
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
    const allDaysEntry = { id: '', description: 'All Days' };
    return [allDaysEntry, ...dateData.items];
  };

  // Helper function to get shift preferences for a person-date combination
  const getShiftPreferences = (personId: string, dateId: string): ShiftRequestPreference[] => {
    return shiftRequestPreferences.filter(
      p => p.person === personId && p.date === dateId
    );
  };

  // Helper function to update shift preferences for a person-date combination
  const updateShiftPreferences = (personId: string, dateId: string, preferences: { shiftTypeId: string; weight: number }[]) => {
    // Remove existing preferences for this person-date combination
    const newPreferences = shiftRequestPreferences.filter(
      p => !(p.person === personId && p.date === dateId)
    );

    // Add new preferences
    preferences.forEach(pref => {
      if (pref.weight !== 0) {
        const newPreference: ShiftRequestPreference = {
          type: SHIFT_REQUEST_PREFERENCE,
          person: personId,
          date: dateId,
          shift_type: pref.shiftTypeId,
          weight: pref.weight,
        };
        newPreferences.push(newPreference);
      }
    });

    updateShiftRequestPreferences(newPreferences);
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
      const indexA = getAllShiftTypes().findIndex(st => st.id === a.shift_type);
      const indexB = getAllShiftTypes().findIndex(st => st.id === b.shift_type);
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

  // Instructions for the help component
  const instructions = [
    "This table shows shift preferences for each person on each date",
    "History columns (H-1, H-2, etc.) show previous shift types assigned to each person",
    "Click on any history cell to set or edit shift types for that time period",
    "Each row represents a person, followed by their history, then date columns",
    "The 'All Days' column allows you to set preferences that apply to all days for each person",
    "Click on any cell to set shift preferences with weights for different shift types",
    "Green cells indicate positive preferences (wants this shift type)",
    "Red cells indicate negative preferences (wants to avoid this shift type)",
    "Yellow cells indicate a mix of positive and negative preferences",
    "The displayed shift type prioritizes the one with the strongest preference or avoidance",
    "Use the navigation tabs or keyboard shortcuts to move between pages"
  ];



  // Check if we have the required data
  const hasRequiredData = (dateRange?.startDate && dateRange?.endDate && dateData.items.length > 0 && peopleData.items.length > 0 && (shiftTypeData.items.length > 0 || shiftTypeData.groups.length > 0));

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
            {(!dateRange?.startDate || !dateRange?.endDate || dateData.items.length === 0) ? (
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
                      >
                        <div className="whitespace-nowrap">H-{historyColumnsCount - index}</div>
                      </th>
                    ))}
                    {getCombinedDateEntries().map((dateEntry) => (
                      <th
                        key={dateEntry.id || 'all-days'}
                        className={`px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider ${
                          dateEntry.id === ''
                            ? 'border-l-2 border-r-2 border-l-blue-200 border-r-blue-200'
                            : ''
                        }`}
                      >
                        <div className="whitespace-nowrap">{dateEntry.id === '' ? 'All Days' : dateEntry.id}</div>
                      </th>
                    ))}
                  </tr>
                </thead>

                {/* Body */}
                <tbody className="bg-white divide-y divide-gray-200">
                  {peopleData.items.map((person) => (
                    <tr key={person.id} className="hover:bg-gray-50">
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
                            onClick={() => isClickable && openHistoryEditor(person.id, index)}
                            title={isClickable ? 'Click to edit history' : ''}
                          >
                            <div className={`text-sm font-medium ${isClickable ? 'text-gray-900' : 'text-gray-300'}`}>
                              {!isClickable ? '' : (historyValue || '—')}
                            </div>
                          </td>
                        );
                      })}
                      {getCombinedDateEntries().map((dateEntry) => {
                        const display = getPreferenceDisplay(person.id, dateEntry.id);

                        return (
                          <td
                            key={`${person.id}-${dateEntry.id || 'all-days'}`}
                            className={`px-1 py-1 text-center cursor-pointer hover:bg-gray-50 transition-colors duration-150 ${
                              dateEntry.id === '' ? 'border-l-2 border-r-2 border-l-blue-200 border-r-blue-200' : ''
                            }`}
                            onClick={() => openEditor(person.id, dateEntry.id)}
                          >
                            <div
                              className={`min-w-16 w-auto h-12 mx-auto rounded-lg border-2 transition-all duration-200 flex flex-col items-center justify-center gap-0 shadow-sm hover:shadow-md ${
                                display
                                  ? `${display.color} ${display.textColor} hover:scale-105`
                                  : 'border-gray-300 hover:border-gray-400 hover:bg-gray-50'
                              }`}
                              title={dateEntry.id === '' ? `Click to edit all-days preferences for ${person.id}` : `Click to edit preferences for ${person.id} on date ${dateEntry.id}`}
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
                                          {pref.shift_type} ({getWeightDisplayLabel(pref.weight)})
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
                  // Get person and date descriptions for display
                  const person = peopleData.items.find(p => p.id === preference.person);
                  const date = dateData.items.find(d => d.id === preference.date);
                  const shiftType = getAllShiftTypes().find(st => st.id === preference.shift_type);

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
                                {preference.date === '' ? 'All Days' : preference.date}
                              </span>
                              {preference.date === '' ? (
                                <div className="text-xs text-blue-500 mt-1">Applies to all days</div>
                              ) : (
                                date?.description && (
                                  <div className="text-xs text-blue-500 mt-1">{date.description}</div>
                                )
                              )}
                            </div>
                            <div>
                              <span className="font-medium">Shift Type:</span>{' '}
                              <span className="text-blue-900">{preference.shift_type}</span>
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
                        <div className="flex justify-end space-x-2 ml-4">
                          <button
                            onClick={() => openEditor(preference.person, preference.date)}
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
        initialPreferences={getShiftPreferences(editorState.personId, editorState.dateId).map(p => ({ shiftTypeId: p.shift_type, weight: p.weight }))}
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
