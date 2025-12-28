/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2025 Johnson Sun
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

// The shift affinities management page for Tab "9. Shift Affinities"
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { FiHelpCircle, FiEdit2, FiTrash2, FiAlertCircle } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { ShiftAffinityPreference, SHIFT_AFFINITY } from '@/types/scheduling';
import { CheckboxList } from '@/components/CheckboxList';
import ToggleButton from '@/components/ToggleButton';
import { isValidWeightValue, getWeightWithPositivePrefix } from '@/utils/numberParsing';
import WeightInput from '@/components/WeightInput';

interface ShiftAffinityForm {
  description: string;
  date: string[];
  people1: string[];
  people2: string[];
  shift_types: string[];
  weight: number | string;
}

export default function ShiftAffinitiesPage() {
  const {
    getPreferencesByType,
    updatePreferencesByType,
    shiftTypeData,
    peopleData,
    dateData
  } = useSchedulingData();

  // Get shift affinities from the flattened preferences
  const shiftAffinities = getPreferencesByType<ShiftAffinityPreference>(SHIFT_AFFINITY);
  const updateShiftAffinities = (newPrefs: ShiftAffinityPreference[]) =>
    updatePreferencesByType(SHIFT_AFFINITY, newPrefs);

  const [isFormVisible, setIsFormVisible] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [showInstructions, setShowInstructions] = useState(false);
  const [formData, setFormData] = useState<ShiftAffinityForm>({
    description: '',
    date: [],
    people1: [],
    people2: [],
    shift_types: [],
    weight: 1
  });
  const [errors, setErrors] = useState<{[key: string]: string}>({});

  const instructions = [
    "Define shift affinity preferences to encourage or discourage people working together",
    "Select the dates when this affinity rule applies",
    "Select the first group of people (People 1)",
    "Select the second group of people (People 2)",
    "Select which shift types this affinity applies to",
    "Set positive weight to encourage working together and negative weight to discourage it",
    "Navigate using the tabs or keyboard shortcuts (1, 2, etc.) to continue setup"
  ];

  const resetForm = () => {
    setFormData({
      description: '',
      date: [],
      people1: [],
      people2: [],
      shift_types: [],
      weight: 1
    });
    setErrors({});
    setEditingIndex(null);
  };

  const handleStartAdd = () => {
    resetForm();
    setIsFormVisible(true);
  };

  const handleStartEdit = (index: number) => {
    const shiftAffinity = shiftAffinities[index];
    setFormData({
      description: shiftAffinity.description ?? '',
      date: shiftAffinity.date,
      people1: shiftAffinity.people1,
      people2: shiftAffinity.people2,
      shift_types: shiftAffinity.shiftTypes,
      weight: shiftAffinity.weight
    });
    setEditingIndex(index);
    setIsFormVisible(true);
    setErrors({});
    // Scroll to top of the page
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  const handleCancel = () => {
    setIsFormVisible(false);
    resetForm();
  };

  const validateForm = (): boolean => {
    const newErrors: {[key: string]: string} = {};

    if (formData.date.length === 0) {
      newErrors.date = 'At least one date must be selected';
    }

    if (formData.people1.length === 0) {
      newErrors.people1 = 'At least one person must be selected for People 1';
    }

    if (formData.people2.length === 0) {
      newErrors.people2 = 'At least one person must be selected for People 2';
    }

    if (formData.shift_types.length === 0) {
      newErrors.shiftTypes = 'At least one shift type must be selected';
    }

    if (!isValidWeightValue(formData.weight)) {
      newErrors.weight = 'Weight must be a valid number, Infinity, or -Infinity';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = () => {
    if (!validateForm()) return;

    const newShiftAffinity: ShiftAffinityPreference = {
      type: SHIFT_AFFINITY,
      description: formData.description,
      date: formData.date,
      people1: formData.people1,
      people2: formData.people2,
      shiftTypes: formData.shift_types,
      weight: formData.weight as number
    };

    let newAffinities;
    if (editingIndex !== null) {
      // Edit existing shift affinity
      newAffinities = [...shiftAffinities];
      newAffinities[editingIndex] = newShiftAffinity;
    } else {
      // Add new shift affinity
      newAffinities = [...shiftAffinities, newShiftAffinity];
    }

    updateShiftAffinities(newAffinities);
    setIsFormVisible(false);
    resetForm();
  };

  const handleDelete = (index: number) => {
    const newShiftAffinities = shiftAffinities.filter((_, i) => i !== index);
    updateShiftAffinities(newShiftAffinities);
  };

  const handleArrayFieldToggle = (field: 'date' | 'people1' | 'people2' | 'shift_types', id: string) => {
    setFormData(prev => ({
      ...prev,
      [field]: prev[field].includes(id)
        ? prev[field].filter(v => v !== id)
        : [...prev[field], id]
    }));
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-800">Shift Affinities</h1>
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
            label="Add Shift Affinity"
            isToggled={isFormVisible}
            onToggle={() => {
              if (isFormVisible) {
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

      {/* Add/Edit Form */}
      {isFormVisible && (
        <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
          <div className="px-6 py-4">
            <h2 className="text-lg font-semibold mb-4 text-gray-800">
              {editingIndex !== null ? 'Edit Shift Affinity' : 'Add New Shift Affinity'}
            </h2>

            <div className="space-y-6">
              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Description (optional)
                </label>
                <input
                  type="text"
                  value={formData.description}
                  onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                  className="block w-full px-4 py-2 text-sm text-gray-900 bg-white border border-gray-300 rounded-lg shadow-sm transition-colors duration-200 ease-in-out focus:border-blue-500 focus:ring-blue-200 placeholder-gray-400 focus:outline-none focus:ring-2 hover:border-gray-400"
                  placeholder="e.g., Encourage newcomers and seniors to work together"
                />
              </div>

              {/* Dates */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Dates *
                </label>
                <div className="max-h-32 overflow-y-auto">
                  {dateData.items.length === 0 && dateData.groups.length === 0 ? (
                    <div className="text-sm text-gray-500 italic p-4 text-center border border-gray-200 rounded-lg bg-gray-50">
                      No dates available. Please set up dates in the{' '}
                      <Link href="/dates" className="text-blue-600 hover:text-blue-800 underline">
                        Dates
                      </Link>{' '}
                      tab first.
                    </div>
                  ) : (
                    <CheckboxList
                      items={[
                        ...dateData.items.map(date => ({
                          id: date.id,
                          description: date.description
                        })),
                        ...dateData.groups.map(group => ({
                          id: group.id,
                          description: group.description
                        }))
                      ]}
                      selectedIds={formData.date}
                      onToggle={(id) => handleArrayFieldToggle('date', id)}
                      label=""
                    />
                  )}
                </div>
                {errors.date && (
                  <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {errors.date}
                  </p>
                )}
              </div>

              {/* People 1 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  People 1 *
                </label>
                {peopleData.items.length === 0 && peopleData.groups.length === 0 ? (
                  <div className="text-sm text-gray-500 italic p-4 text-center border border-gray-200 rounded-lg bg-gray-50">
                    No people available. Please set up people in the{' '}
                    <Link href="/people" className="text-blue-600 hover:text-blue-800 underline">
                      People
                    </Link>{' '}
                    tab first.
                  </div>
                ) : (
                  <CheckboxList
                    items={[
                      ...peopleData.items.map(person => ({
                        id: person.id,
                        description: person.description
                      })),
                      ...peopleData.groups.map(group => ({
                        id: group.id,
                        description: group.description
                      }))
                    ]}
                    selectedIds={formData.people1}
                    onToggle={(id) => handleArrayFieldToggle('people1', id)}
                    label=""
                  />
                )}
                {errors.people1 && (
                  <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {errors.people1}
                  </p>
                )}
              </div>

              {/* People 2 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  People 2 *
                </label>
                {peopleData.items.length === 0 && peopleData.groups.length === 0 ? (
                  <div className="text-sm text-gray-500 italic p-4 text-center border border-gray-200 rounded-lg bg-gray-50">
                    No people available. Please set up people in the{' '}
                    <Link href="/people" className="text-blue-600 hover:text-blue-800 underline">
                      People
                    </Link>{' '}
                    tab first.
                  </div>
                ) : (
                  <CheckboxList
                    items={[
                      ...peopleData.items.map(person => ({
                        id: person.id,
                        description: person.description
                      })),
                      ...peopleData.groups.map(group => ({
                        id: group.id,
                        description: group.description
                      }))
                    ]}
                    selectedIds={formData.people2}
                    onToggle={(id) => handleArrayFieldToggle('people2', id)}
                    label=""
                  />
                )}
                {errors.people2 && (
                  <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {errors.people2}
                  </p>
                )}
              </div>

              {/* Shift Types */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Shift Types *
                </label>
                {shiftTypeData.items.length === 0 && shiftTypeData.groups.length === 0 ? (
                  <div className="text-sm text-gray-500 italic p-4 text-center border border-gray-200 rounded-lg bg-gray-50">
                    No shift types available. Please set up shift types in the{' '}
                    <Link href="/shift-types" className="text-blue-600 hover:text-blue-800 underline">
                      Shift Types
                    </Link>{' '}
                    tab first.
                  </div>
                ) : (
                  <CheckboxList
                    items={[
                      ...shiftTypeData.items.map(shiftType => ({
                        id: shiftType.id,
                        description: shiftType.description
                      })),
                      ...shiftTypeData.groups.map(group => ({
                        id: group.id,
                        description: group.description
                      }))
                    ]}
                    selectedIds={formData.shift_types}
                    onToggle={(id) => handleArrayFieldToggle('shift_types', id)}
                    label=""
                  />
                )}
                {errors.shiftTypes && (
                  <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {errors.shiftTypes}
                  </p>
                )}
              </div>

              {/* Weight */}
              <WeightInput
                value={formData.weight}
                onChange={(value) => setFormData(prev => ({ ...prev, weight: value }))}
                error={errors.weight}
                placeholder="e.g., 1, 10, ∞"
              />

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
                  {editingIndex !== null ? 'Update' : 'Add'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Shift Affinities List */}
      <div className="bg-white shadow-md rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-800">Current Shift Affinities</h3>
        </div>

        {shiftAffinities.length === 0 ? (
          <div className="px-6 py-8 text-center text-gray-500">
            No shift affinities defined yet. Click &quot;Add Shift Affinity&quot; to get started.
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {shiftAffinities.map((shiftAffinity, index) => (
              <div key={index} className="px-6 py-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    {shiftAffinity.description && (
                      <h4 className="font-medium text-gray-900 mb-3">{shiftAffinity.description}</h4>
                    )}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-sm text-gray-600">
                      <div className="md:col-span-2 lg:col-span-3">
                        <span className="font-medium">Dates:</span>{' '}
                        {shiftAffinity.date.join(', ')}
                      </div>
                      <div className="md:col-span-2 lg:col-span-3">
                        <span className="font-medium">People 1:</span>{' '}
                        {shiftAffinity.people1.join(', ')}
                      </div>
                      <div className="md:col-span-2 lg:col-span-3">
                        <span className="font-medium">People 2:</span>{' '}
                        {shiftAffinity.people2.join(', ')}
                      </div>
                      <div className="md:col-span-2 lg:col-span-3">
                        <span className="font-medium">Shift Types:</span>{' '}
                        {shiftAffinity.shiftTypes.join(', ')}
                      </div>
                      <div>
                        <span className="font-medium">Weight:</span> {getWeightWithPositivePrefix(shiftAffinity.weight)}
                      </div>
                    </div>
                  </div>
                  <div className="flex justify-end space-x-2 ml-4">
                    <button
                      onClick={() => handleStartEdit(index)}
                      className="text-blue-600 hover:text-blue-900 flex items-center gap-1 text-sm"
                    >
                      <FiEdit2 className="h-4 w-4" />
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(index)}
                      className="text-red-600 hover:text-red-900 flex items-center gap-1 text-sm"
                    >
                      <FiTrash2 className="h-4 w-4" />
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
