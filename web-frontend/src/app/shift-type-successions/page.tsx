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

// The shift type successions management page for Tab "6. Shift Type Successions"
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { FiHelpCircle, FiEdit2, FiTrash2, FiAlertCircle } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { ShiftTypeSuccessionsPreference, SHIFT_TYPE_SUCCESSIONS } from '@/types/scheduling';
import { CheckboxList } from '@/components/CheckboxList';
import ToggleButton from '@/components/ToggleButton';
import { RemovableTag } from '@/components/RemovableTag';
import { isValidWeightValue, getWeightWithPositivePrefix } from '@/utils/numberParsing';
import WeightInput from '@/components/WeightInput';

interface ShiftTypeSuccessionForm {
  description: string;
  person: string[];
  pattern: string[];
  date: string[];
  weight: number | string;
}

export default function ShiftTypeSuccessionsPage() {
  const {
    getPreferencesByType,
    updatePreferencesByType,
    shiftTypeData,
    peopleData,
    dateData
  } = useSchedulingData();

  // Get shift type successions from the flattened preferences
  const shiftTypeSuccessions = getPreferencesByType<ShiftTypeSuccessionsPreference>(SHIFT_TYPE_SUCCESSIONS);
  const updateShiftTypeSuccessions = (newPrefs: ShiftTypeSuccessionsPreference[]) =>
    updatePreferencesByType(SHIFT_TYPE_SUCCESSIONS, newPrefs);

  const [isFormVisible, setIsFormVisible] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [showInstructions, setShowInstructions] = useState(false);
  const [formData, setFormData] = useState<ShiftTypeSuccessionForm>({
    description: '',
    person: [],
    pattern: [],
    date: [],
    weight: -1
  });
  const [errors, setErrors] = useState<{[key: string]: string}>({});
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverGap, setDragOverGap] = useState<number | null>(null);

  const instructions = [
    "Define shift type succession preferences (e.g., \"Forbid Evening -> Day succession\")",
    "Select one or more people or groups this preference applies to",
    "Define the pattern of shift types in succession (minimum 2 shift types required)",
    "Specify specific dates this succession applies to",
    "Set positive weight to encourage successions and negative weight to discourage them",
    "Navigate using the tabs or keyboard shortcuts (1, 2, etc.) to continue setup"
  ];

  const resetForm = () => {
    setFormData({
      description: '',
      person: [],
      pattern: [],
      date: [],
      weight: -1
    });
    setErrors({});
    setEditingIndex(null);
  };

  const handleStartAdd = () => {
    resetForm();
    setIsFormVisible(true);
  };

  const handleStartEdit = (index: number) => {
    const succession = shiftTypeSuccessions[index];
    setFormData({
      description: succession.description ?? '',
      person: succession.person,
      pattern: succession.pattern,
      date: succession.date,
      weight: succession.weight
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

    if (formData.person.length === 0) {
      newErrors.person = 'At least one person must be selected';
    }

    if (formData.pattern.length < 2) {
      newErrors.pattern = 'At least 2 shift types must be selected for a succession pattern';
    }

    if (formData.date.length === 0) {
      newErrors.date = 'At least one date must be selected';
    }

    if (!isValidWeightValue(formData.weight)) {
      newErrors.weight = 'Weight must be a valid number, Infinity, or -Infinity';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = () => {
    if (!validateForm()) return;

    const newSuccession: ShiftTypeSuccessionsPreference = {
      type: SHIFT_TYPE_SUCCESSIONS,
      description: formData.description,
      person: formData.person,
      pattern: formData.pattern,
      date: formData.date,
      weight: formData.weight as number
    };

    let newSuccessions;
    if (editingIndex !== null) {
      // Edit existing succession
      newSuccessions = [...shiftTypeSuccessions];
      newSuccessions[editingIndex] = newSuccession;
    } else {
      // Add new succession
      newSuccessions = [...shiftTypeSuccessions, newSuccession];
    }

    updateShiftTypeSuccessions(newSuccessions);
    setIsFormVisible(false);
    resetForm();
  };

  const handleDelete = (index: number) => {
    const newSuccessions = shiftTypeSuccessions.filter((_, i) => i !== index);
    updateShiftTypeSuccessions(newSuccessions);
  };

  const handleArrayFieldToggle = (field: 'person' | 'date', id: string) => {
    setFormData(prev => ({
      ...prev,
      [field]: prev[field].includes(id)
        ? prev[field].filter(v => v !== id)
        : [...prev[field], id]
    }));
  };

  const addToPattern = (shiftTypeId: string) => {
    setFormData(prev => ({
      ...prev,
      pattern: [...prev.pattern, shiftTypeId]
    }));
  };

  const removeFromPattern = (index: number) => {
    setFormData(prev => ({
      ...prev,
      pattern: prev.pattern.filter((_, i) => i !== index)
    }));
  };

  const movePatternItem = (fromIndex: number, toIndex: number) => {
    if (toIndex < 0 || toIndex >= formData.pattern.length) return;

    const newPattern = [...formData.pattern];
    const [movedItem] = newPattern.splice(fromIndex, 1);
    newPattern.splice(toIndex, 0, movedItem);

    setFormData(prev => ({ ...prev, pattern: newPattern }));
  };

  const handleDragStart = (index: number) => {
    setDraggedIndex(index);
  };

  const handleDragOverGap = (gapIndex: number) => {
    setDragOverGap(gapIndex);
  };

  const handleDragOverElement = (index: number, e: React.DragEvent) => {
    // Determine which gap to highlight based on mouse position within the element
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX;
    const elementCenter = rect.left + rect.width / 2;

    // If mouse is in left half, highlight gap before element (index)
    // If mouse is in right half, highlight gap after element (index + 1)
    const gapIndex = mouseX < elementCenter ? index : index + 1;
    setDragOverGap(gapIndex);
  };

  const handleDragLeave = () => {
    setDragOverGap(null);
  };

  const handleDropOnGap = (gapIndex: number) => {
    if (draggedIndex !== null) {
      // Convert gap index to target position
      // Gap 0 = insert at position 0, Gap 1 = insert at position 1, etc.
      let targetIndex = gapIndex;

      // If we're moving an item from before the target gap, we need to adjust
      if (draggedIndex < gapIndex) {
        targetIndex = gapIndex - 1;
      }

      if (draggedIndex !== targetIndex) {
        movePatternItem(draggedIndex, targetIndex);
      }
    }
    setDraggedIndex(null);
    setDragOverGap(null);
  };

  const handleDropOnElement = (index: number, e: React.DragEvent) => {
    // Determine which gap to drop into based on mouse position
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX;
    const elementCenter = rect.left + rect.width / 2;

    const gapIndex = mouseX < elementCenter ? index : index + 1;
    handleDropOnGap(gapIndex);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
    setDragOverGap(null);
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-800">Shift Type Successions</h1>
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
            label="Add Succession"
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
              {editingIndex !== null ? 'Edit Succession' : 'Add New Succession'}
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
                  placeholder="e.g., Forbid Evening -> Day succession"
                />
              </div>

              {/* People */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  People *
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
                    selectedIds={formData.person}
                    onToggle={(id) => handleArrayFieldToggle('person', id)}
                    label=""
                  />
                )}
                {errors.person && (
                  <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {errors.person}
                  </p>
                )}
              </div>

              {/* Shift Type Pattern */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Shift Type Pattern * (click to add shift types)
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
                  <div>
                    {/* Available Shift Types as Buttons */}
                    <div className="mb-4">
                      <div className="flex flex-wrap gap-2">
                        {[...shiftTypeData.items, ...shiftTypeData.groups].map(shiftType => (
                          <button
                            key={shiftType.id}
                            type="button"
                            onClick={() => addToPattern(shiftType.id)}
                            className="px-3 py-1 text-sm bg-gray-100 text-gray-700 border border-gray-300 rounded-md hover:bg-gray-200 transition-colors"
                            title={shiftType.description}
                          >
                            {shiftType.id}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Pattern Order Display */}
                    {formData.pattern.length > 0 && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Pattern Order: (drag to reorder)
                        </label>
                        <div className="flex flex-wrap items-center">
                          {/* Gap before first element */}
                          <div
                            className="w-3 h-8 flex justify-center items-center"
                            onDragOver={(e) => {
                              e.preventDefault();
                              handleDragOverGap(0);
                            }}
                            onDragLeave={handleDragLeave}
                            onDrop={(e) => {
                              e.preventDefault();
                              handleDropOnGap(0);
                            }}
                          >
                            {dragOverGap === 0 && (
                              <div className="w-0.5 h-6 bg-blue-600"></div>
                            )}
                          </div>

                          {formData.pattern.map((shiftTypeId, index) => {
                            const shiftType = [...shiftTypeData.items, ...shiftTypeData.groups]
                              .find(item => item.id === shiftTypeId);
                            return (
                              <div key={`${shiftTypeId}-${index}`} className="flex items-center">
                                <RemovableTag
                                  id={shiftTypeId}
                                  description={shiftType?.description}
                                  onRemove={() => removeFromPattern(index)}
                                  draggable={true}
                                  index={index}
                                  onDragStart={handleDragStart}
                                  onDragOver={(elementIndex, e) => e && handleDragOverElement(elementIndex, e)}
                                  onDragLeave={handleDragLeave}
                                  onDrop={(elementIndex, e) => e && handleDropOnElement(elementIndex, e)}
                                  onDragEnd={handleDragEnd}
                                  isDragging={draggedIndex === index}
                                  isDragOver={false} // Never highlight the element itself
                                />

                                {/* Gap after each element */}
                                <div
                                  className="w-3 h-8 flex justify-center items-center"
                                  onDragOver={(e) => {
                                    e.preventDefault();
                                    handleDragOverGap(index + 1);
                                  }}
                                  onDragLeave={handleDragLeave}
                                  onDrop={(e) => {
                                    e.preventDefault();
                                    handleDropOnGap(index + 1);
                                  }}
                                >
                                  {dragOverGap === index + 1 && (
                                    <div className="w-0.5 h-6 bg-blue-600"></div>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                )}
                {errors.pattern && (
                  <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {errors.pattern}
                  </p>
                )}
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

              {/* Weight */}
              <WeightInput
                value={formData.weight}
                onChange={(value) => setFormData(prev => ({ ...prev, weight: value }))}
                error={errors.weight}
                placeholder="e.g., -1, -10, ∞"
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

      {/* Successions List */}
      <div className="bg-white shadow-md rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-800">Current Successions</h3>
        </div>

        {shiftTypeSuccessions.length === 0 ? (
          <div className="px-6 py-8 text-center text-gray-500">
            No successions defined yet. Click &quot;Add Succession&quot; to get started.
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {shiftTypeSuccessions.map((succession, index) => (
              <div key={index} className="px-6 py-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    {succession.description && (
                      <h4 className="font-medium text-gray-900 mb-3">{succession.description}</h4>
                    )}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-sm text-gray-600">
                      <div className="md:col-span-2 lg:col-span-3">
                        <span className="font-medium">People:</span>{' '}
                        {succession.person.join(', ')}
                      </div>
                      <div className="md:col-span-2 lg:col-span-3">
                        <span className="font-medium">Pattern:</span>{' '}
                        <span className="inline-flex items-center">
                          {succession.pattern.map((shiftTypeId, idx) => {
                            const shiftType = [...shiftTypeData.items, ...shiftTypeData.groups]
                              .find(item => item.id === shiftTypeId);
                            return (
                              <span key={idx} className="flex items-center">
                                <span
                                  className="bg-gray-100 px-2 py-1 rounded text-xs"
                                  title={shiftType?.description}
                                >
                                  {shiftTypeId}
                                </span>
                                {idx < succession.pattern.length - 1 && (
                                  <span className="mx-1 text-gray-400">→</span>
                                )}
                              </span>
                            );
                          })}
                        </span>
                      </div>
                      <div>
                        <span className="font-medium">Weight:</span> {getWeightWithPositivePrefix(succession.weight)}
                      </div>
                      {succession.date && succession.date.length > 0 && (
                        <div className="md:col-span-2 lg:col-span-3">
                          <span className="font-medium">Dates:</span>{' '}
                          {succession.date.join(', ')}
                        </div>
                      )}
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
