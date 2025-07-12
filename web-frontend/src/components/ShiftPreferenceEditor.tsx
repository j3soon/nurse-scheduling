// Component for editing shift preferences for a specific person-date combination
'use client';

import { useState, useEffect } from 'react';
import { FiX, FiAlertCircle, FiInfo } from 'react-icons/fi';
import { Item } from '@/types/scheduling';

interface ShiftPreferenceEditorProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (preferences: { shiftTypeId: string; weight: number }[]) => void;
  personId: string;
  dateId: string;
  shiftTypes: Item[];
  initialPreferences: { shiftTypeId: string; weight: number }[];
}

export default function ShiftPreferenceEditor({
  isOpen,
  onClose,
  onSave,
  personId,
  dateId,
  shiftTypes,
  initialPreferences
}: ShiftPreferenceEditorProps) {
  const [preferences, setPreferences] = useState<{ shiftTypeId: string; weight: number | string }[]>(initialPreferences);
  const [errors, setErrors] = useState<{[key: string]: string}>({});

  useEffect(() => {
    setPreferences(initialPreferences);
    setErrors({});
  }, [initialPreferences, isOpen]);

  const handleWeightChange = (shiftTypeId: string, inputValue: string) => {
    let weight: number | string;

    // Handle special string values
    const inputValueLower = inputValue.toLowerCase();
    if (inputValueLower === 'infinity' || inputValueLower === 'inf' || inputValueLower === '∞') {
      weight = Infinity;
    } else if (inputValueLower === '-infinity' || inputValueLower === '-inf' || inputValueLower === '-∞') {
      weight = -Infinity;
    } else {
      weight = parseInt(inputValue);
      if (isNaN(weight)) {
        // Invalid values are left as strings
        weight = inputValue;
      }
    }

    setPreferences(prev => {
      const existing = prev.find(p => p.shiftTypeId === shiftTypeId);
      if (existing) {
        if (weight === 0) {
          // Remove preference if weight is 0
          return prev.filter(p => p.shiftTypeId !== shiftTypeId);
        } else {
          // Update existing preference
          return prev.map(p =>
            p.shiftTypeId === shiftTypeId ? { ...p, weight } : p
          );
        }
      } else if (weight !== 0) {
        // Add new preference
        return [...prev, { shiftTypeId, weight }];
      }
      return prev;
    });
  };

  const getWeight = (shiftTypeId: string): number | string => {
    const preference = preferences.find(p => p.shiftTypeId === shiftTypeId);
    return preference ? preference.weight : 0;
  };

  const getWeightColor = (weight: number | string): string => {
    const numWeight = typeof weight === 'string' ? 0 : weight;
    if (numWeight > 0) return 'text-green-600 bg-green-50';
    if (numWeight < 0) return 'text-red-600 bg-red-50';
    return 'text-gray-500 bg-gray-50';
  };

  const getWeightLabel = (weight: number | string): string => {
    if (weight === Infinity) return '∞';
    if (weight === -Infinity) return '-∞';
    if (typeof weight === 'string') return "Error";
    if (typeof weight === 'number' && weight > 0) return `+${weight}`;
    return weight.toString();
  };

  const validateForm = (): boolean => {
    const newErrors: {[key: string]: string} = {};

    // Check for invalid weights
    for (const preference of preferences) {
      if (typeof preference.weight === 'string') {
        // String values are invalid (parsing failed)
        newErrors[preference.shiftTypeId] = 'Weight must be a valid number, Infinity, or -Infinity';
      } else if (typeof preference.weight === 'number' &&
                 !isFinite(preference.weight) &&
                 preference.weight !== Infinity &&
                 preference.weight !== -Infinity) {
        newErrors[preference.shiftTypeId] = 'Weight must be a valid number, Infinity, or -Infinity';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = () => {
    if (!validateForm()) return;
    // Convert all weights to numbers
    onSave(preferences.map(p => ({ shiftTypeId: p.shiftTypeId, weight: p.weight as number })));
    onClose();
  };

  const handleCancel = () => {
    setPreferences(initialPreferences);
    setErrors({});
    onClose();
  };

  const clearAllPreferences = () => {
    setPreferences([]);
    setErrors({});
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-indigo-50">
          <div>
            <h2 className="text-xl font-bold text-gray-800">
              Shift Preference Matrix
            </h2>
            <p className="text-sm text-gray-600 mt-1">
              Person: <span className="font-medium text-blue-600">{personId}</span> •
              Date: <span className="font-medium text-blue-600">{dateId}</span>
            </p>
          </div>
          <button
            onClick={handleCancel}
            className="text-gray-400 hover:text-gray-600 transition-colors p-2 hover:bg-white rounded-full"
          >
            <FiX className="h-6 w-6" />
          </button>
        </div>

        {/* Content */}
        <div className="overflow-y-auto max-h-[calc(90vh-200px)]">
          <div className="p-6">
            {/* Info Box */}
            <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <div className="flex items-start gap-3">
                <FiInfo className="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" />
                <div>
                  <h4 className="text-sm font-medium text-blue-800 mb-1">Weight Scale Guide</h4>
                  <div className="text-xs text-blue-700 space-y-1">
                    <div><span className="font-medium text-green-600">Positive (+1 to Infinity):</span> Prefer this shift type</div>
                    <div><span className="font-medium text-red-600">Negative (-1 to -Infinity):</span> Avoid this shift type</div>
                    <div><span className="font-medium text-gray-600">Zero (0):</span> No preference</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Preferences Table */}
            <div className="bg-white border border-gray-200 rounded-lg overflow-hidden shadow-sm">
              <div className="bg-gray-50 px-3 sm:px-6 py-3 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-700">Shift Type Preferences</h3>
                  <span className="text-xs text-gray-500">{shiftTypes.length} shift types</span>
                </div>
              </div>

              {/* Table Header */}
              <div className="bg-gray-50 px-3 sm:px-6 py-3 border-b border-gray-200">
                <div className="grid grid-cols-12 gap-2 sm:gap-4 text-xs font-medium text-gray-600 uppercase tracking-wider">
                  <div className="col-span-4 sm:col-span-5">Shift Type</div>
                  <div className="col-span-3 sm:col-span-4 hidden sm:block">Description</div>
                  <div className="col-span-4 sm:col-span-2 text-center">Weight</div>
                  <div className="col-span-4 sm:col-span-1 text-center">Status</div>
                </div>
              </div>

              {/* Table Body */}
              <div className="divide-y divide-gray-200">
                {shiftTypes.map((shiftType, index) => {
                  const weight = getWeight(shiftType.id);
                  const hasError = errors[shiftType.id];

                  return (
                    <div
                      key={shiftType.id}
                      className={`px-3 sm:px-6 py-4 hover:bg-gray-50 transition-colors ${
                        index % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'
                      }`}
                    >
                      <div className="grid grid-cols-12 gap-2 sm:gap-4 items-center">
                        {/* Shift Type */}
                        <div className="col-span-4 sm:col-span-5">
                          <div className="font-medium text-sm text-gray-900 truncate">
                            {shiftType.id}
                          </div>
                          {/* Show description on small screens */}
                          <div className="sm:hidden text-xs text-gray-500 mt-1 truncate">
                            {shiftType.description ? shiftType.description : <span className="italic text-gray-400">No description</span>}
                          </div>
                        </div>

                        {/* Description */}
                        <div className="col-span-3 sm:col-span-4 hidden sm:block">
                          <div className="text-sm text-gray-600 truncate">
                            {shiftType.description ? shiftType.description : <span className="italic text-gray-400">No description</span>}
                          </div>
                        </div>

                        {/* Weight Input */}
                        <div className="col-span-4 sm:col-span-2 flex justify-center">
                          <input
                            type="text"
                            value={weight}
                            onChange={(e) => handleWeightChange(shiftType.id, e.target.value)}
                            className={`w-18 sm:w-20 px-2 sm:px-3 py-2 text-sm text-center border rounded-md transition-all ${
                              hasError
                                ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
                                : 'border-gray-300 focus:border-blue-500 focus:ring-blue-200'
                            } focus:ring-2 focus:ring-opacity-50`}
                          />
                        </div>

                        {/* Status Indicator */}
                        <div className="col-span-4 sm:col-span-1 flex justify-center">
                          {hasError ? (
                            <FiAlertCircle className="h-5 w-5 text-red-500" />
                          ) : (
                            <div className={`px-1 sm:px-2 py-1 rounded-full text-xs font-medium ${getWeightColor(weight)}`}>
                              {weight === 0 ? '—' : getWeightLabel(weight)}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Error Message */}
                      {hasError && (
                        <div className="mt-2 text-sm text-red-600 flex items-center gap-1">
                          <FiAlertCircle className="h-4 w-4" />
                          {hasError}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Summary Section */}
            {preferences.length > 0 && (
              <div className="mt-6 p-4 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-lg">
                <h4 className="text-sm font-semibold text-blue-800 mb-3 flex items-center gap-2">
                  <span>Active Preferences Summary</span>
                  <span className="bg-blue-200 text-blue-800 px-2 py-1 rounded-full text-xs">
                    {preferences.length}
                  </span>
                </h4>
                <div className="grid grid-cols-2 gap-3">
                  {preferences
                    .filter(p => typeof p.weight === 'number')
                    .sort((a, b) => (b.weight as number) - (a.weight as number))
                    .map((pref) => (
                      <div key={pref.shiftTypeId} className="flex items-center justify-between bg-white px-3 py-2 rounded-md shadow-sm">
                        <span className="text-sm font-medium text-gray-700">{pref.shiftTypeId}</span>
                        <span className={`text-sm font-bold ${
                          (pref.weight as number) > 0 ? 'text-green-600' : 'text-red-600'
                        }`}>
                          {getWeightLabel(pref.weight)}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-between items-center p-3 sm:p-6 border-t border-gray-200 bg-gray-50 gap-2">
          <button
            onClick={clearAllPreferences}
            className="px-3 sm:px-4 py-2 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-100 transition-colors font-medium text-sm sm:text-base"
          >
            Clear All
          </button>
          <div className="flex gap-2 sm:gap-3">
            <button
              onClick={handleCancel}
              className="px-4 sm:px-6 py-2 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-100 transition-colors font-medium text-sm sm:text-base"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={Object.keys(errors).length > 0}
              className="px-4 sm:px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors font-medium text-sm sm:text-base"
            >
              Save Preferences
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
