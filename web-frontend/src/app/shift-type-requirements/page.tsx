// The shift type requirements management page for Tab "4. Shift Type Requirements"
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { FiHelpCircle, FiEdit2, FiTrash2, FiAlertCircle } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { ShiftTypeRequirementsPreference, SHIFT_TYPE_REQUIREMENT } from '@/types/scheduling';
import { CheckboxList } from '@/components/CheckboxList';
import ToggleButton from '@/components/ToggleButton';
import { parseWeightValue, isValidWeightValue, isValidNumberValue, getWeightWithPositivePrefix } from '@/utils/numberParsing';
import { ALL } from '@/utils/keywords';

interface ShiftTypeRequirementForm {
  description: string;
  shift_type: string[];
  required_num_people: number;
  qualified_people: string[];
  preferred_num_people?: number;
  date: string[];
  weight: number | string;
}

export default function ShiftTypeRequirementsPage() {
  const {
    getPreferencesByType,
    updatePreferencesByType,
    shiftTypeData,
    peopleData,
    dateData
  } = useSchedulingData();

  // Get shift type requirements from the flattened preferences
  const shiftTypeRequirements = getPreferencesByType<ShiftTypeRequirementsPreference>(SHIFT_TYPE_REQUIREMENT);
  const updateShiftTypeRequirements = (newPrefs: ShiftTypeRequirementsPreference[]) =>
    updatePreferencesByType(SHIFT_TYPE_REQUIREMENT, newPrefs);

  const [isFormVisible, setIsFormVisible] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [showInstructions, setShowInstructions] = useState(false);
  const [formData, setFormData] = useState<ShiftTypeRequirementForm>({
    description: '',
    shift_type: [],
    required_num_people: 1,
    qualified_people: [],
    preferred_num_people: undefined,
    date: [],
    weight: -1
  });
  const [errors, setErrors] = useState<{[key: string]: string}>({});

  const instructions = [
    "Define requirements for specific shift types (e.g., \"Night shifts need 3 senior nurses\")",
    "Select one or more shift types that this requirement applies to",
    "Set the required number of people for each instance of the shift type",
    "Optionally specify which people or groups are qualified for this requirement (leave empty for all people)",
    "Optionally set a preferred number of people (if different from required)",
    "Optionally specify specific dates this requirement applies to (leave empty for all dates)",
    "Set weight to penalize unmet requirements (-1 is default, lower numbers = higher penalty)",
    "Navigate using the tabs or keyboard shortcuts (1, 2, etc.) to continue setup"
  ];

  const resetForm = () => {
    setFormData({
      description: '',
      shift_type: [],
      required_num_people: 1,
      qualified_people: [],
      preferred_num_people: undefined,
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
    const requirement = shiftTypeRequirements[index];
    setFormData({
      description: requirement.description ?? '',
      shift_type: requirement.shiftType,
      required_num_people: requirement.requiredNumPeople,
      qualified_people: requirement.qualifiedPeople,
      preferred_num_people: requirement.preferredNumPeople,
      date: requirement.date,
      weight: requirement.weight
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

    if (formData.shift_type.length === 0) {
      newErrors.shift_type = 'At least one shift type must be selected';
    }

    if (!isValidNumberValue(formData.required_num_people)) {
      newErrors.required_num_people = 'Required number of people must be a valid number';
    } else if (typeof formData.required_num_people === 'number' && formData.required_num_people < 0) {
      newErrors.required_num_people = 'Required number of people must be at least 0';
    }

    if (formData.preferred_num_people !== undefined) {
      if (!isValidNumberValue(formData.preferred_num_people)) {
        newErrors.preferred_num_people = 'Preferred number of people must be a valid number';
      } else if (typeof formData.preferred_num_people === 'number') {
        if (formData.preferred_num_people < 1) {
          newErrors.preferred_num_people = 'Preferred number of people must be at least 1';
        } else if (typeof formData.required_num_people === 'number' && formData.preferred_num_people < formData.required_num_people) {
          newErrors.preferred_num_people = 'Preferred number of people must be greater than required number of people';
        }
      }
    }

    if (!isValidWeightValue(formData.weight)) {
      newErrors.weight = 'Weight must be a valid number, Infinity, or -Infinity';
    } else if (typeof formData.weight === 'number' && formData.weight > -1) {
      newErrors.weight = 'Weight must be -1 or less (including -Infinity)';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSave = () => {
    if (!validateForm()) return;

    const newRequirement: ShiftTypeRequirementsPreference = {
      type: SHIFT_TYPE_REQUIREMENT,
      description: formData.description,
      shiftType: formData.shift_type,
      requiredNumPeople: formData.required_num_people,
      qualifiedPeople: formData.qualified_people.length > 0 ? formData.qualified_people : [ALL],
      preferredNumPeople: formData.preferred_num_people,
      date: formData.date.length > 0 ? formData.date : [ALL],
      weight: formData.weight as number
    };

    let newRequirements;
    if (editingIndex !== null) {
      // Edit existing requirement
      newRequirements = [...shiftTypeRequirements];
      newRequirements[editingIndex] = newRequirement;
    } else {
      // Add new requirement
      newRequirements = [...shiftTypeRequirements, newRequirement];
    }

    updateShiftTypeRequirements(newRequirements);
    setIsFormVisible(false);
    resetForm();
  };

  const handleDelete = (index: number) => {
    const newRequirements = shiftTypeRequirements.filter((_, i) => i !== index);
    updateShiftTypeRequirements(newRequirements);
  };

  const handleArrayFieldToggle = (field: 'shift_type' | 'qualified_people' | 'date', id: string) => {
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
          <h1 className="text-3xl font-bold text-gray-800">Shift Type Requirements</h1>
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
            label="Add Requirement"
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
              {editingIndex !== null ? 'Edit Requirement' : 'Add New Requirement'}
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
                  placeholder="e.g., Night shifts need senior nurses"
                />
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
                    selectedIds={formData.shift_type}
                    onToggle={(id) => handleArrayFieldToggle('shift_type', id)}
                    label=""
                  />
                )}
                {errors.shift_type && (
                  <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {errors.shift_type}
                  </p>
                )}
              </div>

              {/* Required Number of People and Preferred Number of People */}
              <div className="flex gap-4">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Required Number of People *
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={formData.required_num_people}
                    onChange={(e) => setFormData(prev => ({
                      ...prev,
                      // Note that the isNaN check is necessary, since a simple parseInt(e.target.value) will return 0 if the value is exactly 0.
                      required_num_people: isNaN(parseInt(e.target.value)) ? prev.required_num_people : parseInt(e.target.value)
                    }))}
                    className={`block w-full px-4 py-2 text-sm text-gray-900 bg-white border rounded-lg shadow-sm transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 hover:border-gray-400 ${
                      errors.required_num_people
                        ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
                        : 'border-gray-300 focus:border-blue-500 focus:ring-blue-200'
                    }`}
                  />
                  {errors.required_num_people && (
                    <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
                      <FiAlertCircle className="h-4 w-4" />
                      {errors.required_num_people}
                    </p>
                  )}
                </div>

                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Preferred Number of People (optional)
                  </label>
                  <input
                    type="number"
                    min="1"
                    value={formData.preferred_num_people ?? formData.required_num_people}
                    onChange={(e) => setFormData(prev => ({
                      ...prev,
                      preferred_num_people: isNaN(parseInt(e.target.value))
                        ? prev.preferred_num_people
                        : (parseInt(e.target.value) === prev.required_num_people
                            ? undefined
                            : parseInt(e.target.value))
                    }))}
                    className={`block w-full px-4 py-2 text-sm text-gray-900 bg-white border rounded-lg shadow-sm transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 hover:border-gray-400 ${
                      errors.preferred_num_people
                        ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
                        : 'border-gray-300 focus:border-blue-500 focus:ring-blue-200'
                    }`}
                    placeholder="Leave empty if same as required"
                  />
                  {errors.preferred_num_people && (
                    <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
                      <FiAlertCircle className="h-4 w-4" />
                      {errors.preferred_num_people}
                    </p>
                  )}
                </div>
              </div>

              {/* Qualified People */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Qualified People (optional - leave empty for all people)
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
                    selectedIds={formData.qualified_people}
                    onToggle={(id) => handleArrayFieldToggle('qualified_people', id)}
                    label=""
                  />
                )}
              </div>

              {/* Dates */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Dates (optional - leave empty for all dates)
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

      {/* Requirements List */}
      <div className="bg-white shadow-md rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-800">Current Requirements</h3>
        </div>

        {shiftTypeRequirements.length === 0 ? (
          <div className="px-6 py-8 text-center text-gray-500">
            No requirements defined yet. Click &quot;Add Requirement&quot; to get started.
          </div>
        ) : (
          <div className="divide-y divide-gray-200">
            {shiftTypeRequirements.map((requirement, index) => (
              <div key={index} className="px-6 py-5">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    {requirement.description && (
                      <h4 className="font-medium text-gray-900 mb-3">{requirement.description}</h4>
                    )}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-sm text-gray-600">
                      <div>
                        <span className="font-medium">Shift Types:</span>{' '}
                        {requirement.shiftType.join(', ')}
                      </div>
                      <div>
                        <span className="font-medium">Required:</span> {requirement.requiredNumPeople}
                        {requirement.preferredNumPeople && (
                          <span> (Preferred: {requirement.preferredNumPeople})</span>
                        )}
                      </div>
                      <div>
                        <span className="font-medium">Weight:</span> {getWeightWithPositivePrefix(requirement.weight)}
                      </div>
                      {requirement.qualifiedPeople && (
                        <div className="md:col-span-2 lg:col-span-3">
                          <span className="font-medium">Qualified:</span>{' '}
                          {requirement.qualifiedPeople.length > 0 ? requirement.qualifiedPeople.join(', ') : '(All People)'}
                        </div>
                      )}
                      {requirement.date && (
                        <div className="md:col-span-2 lg:col-span-3">
                          <span className="font-medium">Dates:</span>{' '}
                          {requirement.date.length > 0 ? requirement.date.join(', ') : '(All Dates)'}
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
