// The shift counts management page for Tab "7. Shift Counts"
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { FiHelpCircle, FiEdit2, FiTrash2, FiAlertCircle } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { ShiftCountPreference, SHIFT_COUNT, SUPPORTED_EXPRESSIONS, SUPPORTED_SPECIAL_TARGETS } from '@/types/scheduling';
import { CheckboxList } from '@/components/CheckboxList';
import ToggleButton from '@/components/ToggleButton';
import { parseWeightValue, isValidWeightValue, getWeightWithPositivePrefix } from '@/utils/numberParsing';
import { ALL } from '@/utils/keywords';

interface ShiftCountForm {
  description: string;
  person: string[];
  count_dates: string[];
  count_shift_types: string[];
  expression: typeof SUPPORTED_EXPRESSIONS[number];
  target: number | string;
  weight: number | string;
}

export default function ShiftCountsPage() {
  const {
    getPreferencesByType,
    updatePreferencesByType,
    shiftTypeData,
    peopleData,
    dateData
  } = useSchedulingData();

  // Get shift counts from the flattened preferences
  const shiftCounts = getPreferencesByType<ShiftCountPreference>(SHIFT_COUNT);
  const updateShiftCounts = (newPrefs: ShiftCountPreference[]) =>
    updatePreferencesByType(SHIFT_COUNT, newPrefs);

  const [isFormVisible, setIsFormVisible] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [showInstructions, setShowInstructions] = useState(false);
  const [formData, setFormData] = useState<ShiftCountForm>({
    description: '',
    person: [],
    count_dates: [],
    count_shift_types: [],
    expression: 'x >= T',
    target: 0,
    weight: -1
  });
  const [errors, setErrors] = useState<{[key: string]: string}>({});

  const instructions = [
    "Set up shift count rules for people (e.g., \"Working shifts should be close to the average\")",
    "Select one or more people that this constraint applies to",
    "Select which dates to count shifts for (leave empty for all dates)",
    "Select which shift types to count (leave empty for all shift types)",
    "Choose a mathematical expression to evaluate (e.g., 'x >= T' means count should be at least the target)",
    "Set the target value (number) or use special constants like 'floor(AVG_SHIFTS_PER_PERSON)'",
    "Set positive weight to encourage constraint matches and negative weight to discourage them",
    "Navigate using the tabs or keyboard shortcuts (1, 2, etc.) to continue setup"
  ];

  const resetForm = () => {
    setFormData({
      description: '',
      person: [],
      count_dates: [],
      count_shift_types: [],
      expression: 'x >= T',
      target: 0,
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
    const shiftCount = shiftCounts[index];
    setFormData({
      description: shiftCount.description ?? '',
      person: shiftCount.person,
      count_dates: shiftCount.count_dates,
      count_shift_types: shiftCount.count_shift_types,
      expression: shiftCount.expression,
      target: shiftCount.target,
      weight: shiftCount.weight
    });
    setEditingIndex(index);
    setIsFormVisible(true);
    setErrors({});
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

    if (!SUPPORTED_EXPRESSIONS.includes(formData.expression)) {
      newErrors.expression = 'Please select a valid expression';
    }

    if (typeof formData.target === 'string' && !SUPPORTED_SPECIAL_TARGETS.includes(formData.target as typeof SUPPORTED_SPECIAL_TARGETS[number])) {
      newErrors.target = 'Target must be a number or a supported special constant';
    }

    if (!isValidWeightValue(formData.weight)) {
      newErrors.weight = 'Weight must be a valid number, Infinity, or -Infinity';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = () => {
    if (!validateForm()) return;

    const newShiftCount: ShiftCountPreference = {
      type: SHIFT_COUNT,
      description: formData.description,
      person: formData.person,
      count_dates: formData.count_dates.length > 0 ? formData.count_dates : [ALL],
      count_shift_types: formData.count_shift_types.length > 0 ? formData.count_shift_types : [ALL],
      expression: formData.expression,
      target: formData.target as typeof SUPPORTED_SPECIAL_TARGETS[number] | number,
      weight: formData.weight as number
    };

    let newShiftCounts;
    if (editingIndex !== null) {
      // Edit existing shift count
      newShiftCounts = [...shiftCounts];
      newShiftCounts[editingIndex] = newShiftCount;
    } else {
      // Add new shift count
      newShiftCounts = [...shiftCounts, newShiftCount];
    }

    updateShiftCounts(newShiftCounts);
    setIsFormVisible(false);
    resetForm();
  };

  const handleDelete = (index: number) => {
    const newShiftCounts = shiftCounts.filter((_, i) => i !== index);
    updateShiftCounts(newShiftCounts);
  };

  const handleArrayFieldToggle = (field: 'person' | 'count_dates' | 'count_shift_types', id: string) => {
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
          <h1 className="text-3xl font-bold text-gray-800">Shift Counts</h1>
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
            label="Add Shift Count"
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
              {editingIndex !== null ? 'Edit Shift Count' : 'Add New Shift Count'}
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
                  placeholder="e.g., Working shifts should be close to the average"
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

              {/* Count Dates */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Count Dates (optional - leave empty for all dates)
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
                      selectedIds={formData.count_dates}
                      onToggle={(id) => handleArrayFieldToggle('count_dates', id)}
                      label=""
                    />
                  )}
                </div>
              </div>

              {/* Count Shift Types */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Count Shift Types (optional - leave empty for all shift types)
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
                    selectedIds={formData.count_shift_types}
                    onToggle={(id) => handleArrayFieldToggle('count_shift_types', id)}
                    label=""
                  />
                )}
              </div>

              {/* Expression and Target */}
              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Expression *
                  </label>
                  <select
                    value={formData.expression}
                    onChange={(e) => setFormData(prev => ({ ...prev, expression: e.target.value as typeof SUPPORTED_EXPRESSIONS[number] }))}
                    className={`block w-full px-4 py-2 text-sm text-gray-900 bg-white border rounded-lg shadow-sm transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 hover:border-gray-400 ${
                      errors.expression
                        ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
                        : 'border-gray-300 focus:border-blue-500 focus:ring-blue-200'
                    }`}
                  >
                    {SUPPORTED_EXPRESSIONS.map(expr => (
                      <option key={expr} value={expr}>{expr}</option>
                    ))}
                  </select>
                  {errors.expression && (
                    <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
                      <FiAlertCircle className="h-4 w-4" />
                      {errors.expression}
                    </p>
                  )}
                </div>

                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Target Value *
                  </label>
                  <input
                    type="text"
                    value={formData.target}
                    onChange={(e) => {
                      const value = e.target.value;
                      setErrors(prev => ({ ...prev, target: '' }));
                      if (SUPPORTED_SPECIAL_TARGETS.includes(value as typeof SUPPORTED_SPECIAL_TARGETS[number])) {
                        setFormData(prev => ({ ...prev, target: value as typeof SUPPORTED_SPECIAL_TARGETS[number] }));
                      } else {
                        const numValue = parseInt(value);
                        if (!isNaN(numValue)) {
                          setFormData(prev => ({ ...prev, target: numValue }));
                        } else {
                          setFormData(prev => ({ ...prev, target: value.toString() }));
                          setErrors(prev => ({ ...prev, target: 'Target must be a number or a supported special constant' }));
                        }
                      }
                    }}
                    className={`block w-full px-4 py-2 text-sm text-gray-900 bg-white border rounded-lg shadow-sm transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 hover:border-gray-400 ${
                      errors.target
                        ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
                        : 'border-gray-300 focus:border-blue-500 focus:ring-blue-200'
                    }`}
                    placeholder="e.g., 5 or floor(AVG_SHIFTS_PER_PERSON)"
                  />
                  {errors.target && (
                    <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
                      <FiAlertCircle className="h-4 w-4" />
                      {errors.target}
                    </p>
                  )}
                  <p className="mt-1 text-xs text-gray-500">
                    Special constants: {SUPPORTED_SPECIAL_TARGETS.join(', ')}
                  </p>
                </div>
              </div>

              {/* Weight */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Weight (priority)
                </label>
                <input
                  type="text"
                  value={formData.weight}
                  onChange={(e) => setFormData(prev => ({
                    ...prev,
                    weight: parseWeightValue(e.target.value)
                  }))}
                  className={`block w-full px-4 py-2 text-sm text-gray-900 bg-white border rounded-lg shadow-sm transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 hover:border-gray-400 ${
                    errors.weight
                      ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
                      : 'border-gray-300 focus:border-blue-500 focus:ring-blue-200'
                  }`}
                  placeholder="e.g., -1, -10, ∞"
                />
                {errors.weight && (
                  <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {errors.weight}
                  </p>
                )}
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
                  {editingIndex !== null ? 'Update' : 'Add'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Shift Counts List */}
      <div className="bg-white shadow-md rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-800">Current Shift Counts</h3>
        </div>

        {shiftCounts.length === 0 ? (
          <div className="px-6 py-8 text-center text-gray-500">
            No shift counts defined yet. Click &quot;Add Shift Count&quot; to get started.
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {shiftCounts.map((shiftCount, index) => (
              <div key={index} className="px-6 py-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    {shiftCount.description && (
                      <h4 className="font-medium text-gray-900 mb-3">{shiftCount.description}</h4>
                    )}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-sm text-gray-600">
                      <div>
                        <span className="font-medium">People:</span>{' '}
                        {shiftCount.person.join(', ')}
                      </div>
                      <div>
                        <span className="font-medium">Expression:</span> <code className="px-2 py-1 bg-gray-100 rounded text-sm font-mono">{shiftCount.expression.replace('T', shiftCount.target.toString())}</code>
                      </div>
                      <div>
                        <span className="font-medium">Weight:</span> {getWeightWithPositivePrefix(shiftCount.weight)}
                      </div>
                      <div className="md:col-span-2 lg:col-span-3">
                        <span className="font-medium">Count Dates:</span>{' '}
                        {shiftCount.count_dates.length > 0 ? shiftCount.count_dates.join(', ') : '(All Dates)'}
                      </div>
                      <div className="md:col-span-2 lg:col-span-3">
                        <span className="font-medium">Count Shift Types:</span>{' '}
                        {shiftCount.count_shift_types.length > 0 ? shiftCount.count_shift_types.join(', ') : '(All Shift Types)'}
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
