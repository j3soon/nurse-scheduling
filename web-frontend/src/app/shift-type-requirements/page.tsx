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

// The shift type requirements management page for Tab "4. Shift Type Requirements"
'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import { FiHelpCircle, FiAlertCircle } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { Group, Item, ShiftTypeRequirementsPreference, SHIFT_TYPE_REQUIREMENT } from '@/types/scheduling';
import { CheckboxList } from '@/components/CheckboxList';
import { CountShiftTypeCoefficientFields } from '@/components/CountShiftTypeCoefficientFields';
import { DraggableCardList } from '@/components/DraggableCardList';
import NumberInput from '@/components/NumberInput';
import ToggleButton from '@/components/ToggleButton';
import { isValidWeightValue, isValidNumberValue, getWeightWithPositivePrefix } from '@/utils/numberParsing';
import WeightInput from '@/components/WeightInput';
import { saveScrollPosition, restoreScrollPosition } from '@/utils/scrolling';
import { ALL, OFF } from '@/utils/keywords';
import { useTabSwitchWarning } from '@/utils/unsavedEditingState';
import { isImeCompositionKeyEvent } from '@/utils/keyboardEvents';
import {
  DraftShiftCountTypeCoefficient,
  syncCoefficientPairs,
  validateCoefficientPairs,
} from '@/utils/countShiftTypeCoefficients';
import { getOrderedEntries } from '@/utils/entityOrdering';

interface ShiftTypeRequirementForm {
  description: string;
  shift_type: string[];
  shift_type_coefficients: DraftShiftCountTypeCoefficient[];
  required_num_people: number | string;
  qualified_people: string[];
  preferred_num_people?: number | string;
  date: string[];
  weight: number | string;
}

interface ShiftTypeRequirementErrors {
  shift_type?: string;
  shift_type_coefficients?: string;
  shift_type_coefficients_by_id?: Record<string, string>;
  required_num_people?: string;
  qualified_people?: string;
  preferred_num_people?: string;
  date?: string;
  weight?: string;
  [key: string]: string | Record<string, string> | undefined;
}

type NullableShiftTypeRequirementsPreference = Omit<ShiftTypeRequirementsPreference, 'qualifiedPeople'> & {
  // Backend input accepts both null/missing and the reserved ALL selector for
  // all people. The frontend form normalizes the implicit form to [ALL].
  qualifiedPeople?: ShiftTypeRequirementsPreference['qualifiedPeople'] | null;
};

function preferredNumPeopleDiffersFromRequired(formData: ShiftTypeRequirementForm): boolean {
  return formData.preferred_num_people !== undefined
    && formData.preferred_num_people !== ''
    && formData.preferred_num_people !== formData.required_num_people;
}

interface RequirementCoverageWarning {
  undefinedPairsCount: number;
  undefinedShiftTypes: {
    shiftTypeId: string;
    datesLabel: string;
  }[];
  duplicateCells: string[];
}

function areSameIds(leftIds: readonly string[], rightIds: readonly string[]): boolean {
  if (leftIds.length !== rightIds.length) return false;

  const rightIdSet = new Set(rightIds);
  return leftIds.every(id => rightIdSet.has(id));
}

function formatDateCoverage(
  dateIds: string[],
  dateGroups: Group[],
  mapDateIdToExpandedDateIds: Map<string, readonly string[]>,
): string {
  // Prefer a human-readable date group when it exactly represents the missing
  // dates; otherwise list the concrete dates so no undefined cells are hidden.
  const exactGroup = dateGroups.find(group =>
    areSameIds(dateIds, mapDateIdToExpandedDateIds.get(group.id) ?? [])
  );

  return exactGroup?.id ?? dateIds.join(', ');
}

function buildRequirementCoverageWarning(
  requirements: ShiftTypeRequirementsPreference[],
  dateItems: Item[],
  dateGroups: Group[],
  shiftTypeItems: Item[],
  shiftTypeGroups: Group[],
): RequirementCoverageWarning {
  // Coverage records which requirement first defines each concrete
  // (date, shift type) pair after frontend groups are expanded. JSON-encoding
  // the tuple avoids collisions between IDs that contain separator characters.
  const coverage = new Map<string, number>();
  const duplicateCells: string[] = [];
  const staffedShiftTypeItems = shiftTypeItems.filter(shiftType => shiftType.id !== OFF);
  const mapDateIdToExpandedDateIds = new Map(
    [
      ...dateItems.map(date => [date.id, [date.id]] as const),
      ...dateGroups.map(group => [group.id, [...new Set(group.members)]] as const),
    ]
  );
  const mapShiftTypeIdToExpandedShiftTypeIds = new Map(
    [
      ...staffedShiftTypeItems.map(shiftType => [shiftType.id, [shiftType.id]] as const),
      ...shiftTypeGroups.map(group => [group.id, [...new Set(group.members)]] as const),
    ]
  );

  // Track coverage by concrete (date, shift type) pair so overlapping groups
  // are detected before users reach the backend solver error.
  requirements.forEach((requirement, requirementIndex) => {
    // Frontend date and shift type groups contain only item IDs, so they expand
    // directly to their members. Special date range strings are core-only.
    const dates = Array.from(new Set((requirement.date ?? []).flatMap(dateId =>
      mapDateIdToExpandedDateIds.get(dateId) ?? []
    )));
    const shiftTypes = Array.from(new Set((requirement.shiftType ?? []).flatMap(shiftTypeId =>
      mapShiftTypeIdToExpandedShiftTypeIds.get(shiftTypeId) ?? []
    )));

    dates.forEach(dateId => {
      shiftTypes.forEach(shiftTypeId => {
        const key = JSON.stringify([dateId, shiftTypeId]);
        const previousRequirementIndex = coverage.get(key);
        if (previousRequirementIndex !== undefined) {
          duplicateCells.push(`${dateId} / ${shiftTypeId} (requirements ${previousRequirementIndex + 1} and ${requirementIndex + 1})`);
        } else {
          coverage.set(key, requirementIndex);
        }
      });
    });
  });

  // Undefined requirements are grouped by shift type to make the warning
  // actionable: users can fix all missing dates for one shift type at a time.
  const undefinedShiftTypes = staffedShiftTypeItems
    .map(shiftTypeItem => ({
      shiftTypeId: shiftTypeItem.id,
      dateIds: dateItems
        .filter(dateItem => !coverage.has(JSON.stringify([dateItem.id, shiftTypeItem.id])))
        .map(dateItem => dateItem.id),
    }))
    .filter(entry => entry.dateIds.length > 0);

  const undefinedPairsCount = undefinedShiftTypes.reduce(
    (sum, entry) => sum + entry.dateIds.length,
    0,
  );

  const undefinedShiftTypeSummaries = undefinedShiftTypes.map(entry => ({
    shiftTypeId: entry.shiftTypeId,
    datesLabel: formatDateCoverage(entry.dateIds, dateGroups, mapDateIdToExpandedDateIds),
  }));

  return {
    undefinedPairsCount,
    undefinedShiftTypes: undefinedShiftTypeSummaries,
    duplicateCells,
  };
}

export default function ShiftTypeRequirementsPage() {
  const {
    getPreferencesByType,
    updatePreferencesByType,
    duplicatePreferenceByType,
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
    shift_type_coefficients: [],
    required_num_people: 1,
    qualified_people: [],
    preferred_num_people: undefined,
    date: [],
    weight: -1
  });
  const [errors, setErrors] = useState<ShiftTypeRequirementErrors>({});
  useTabSwitchWarning(isFormVisible);

  const instructions = [
    "Define requirements for specific shift types (e.g., \"Night shifts need 3 senior nurses\")",
    "Select one shift type or group that this requirement applies to",
    "Set the required number of people for each instance of the shift type",
    "Optionally specify which people or groups are qualified for this requirement",
    "Optionally set a preferred number of people when extra staffing is useful",
    "Optionally specify specific dates this requirement applies to",
    "Set weight only when the preferred number of people differs from the required number",
    "Navigate using the tabs or keyboard shortcuts (1, 2, etc.) to continue setup"
  ];

  const resetForm = () => {
    setFormData({
      description: '',
      shift_type: [],
      shift_type_coefficients: [],
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
    const requirement = shiftTypeRequirements[index] as NullableShiftTypeRequirementsPreference;
    setFormData({
      description: requirement.description ?? '',
      shift_type: requirement.shiftType,
      shift_type_coefficients: syncCoefficientPairs(
        requirement.shiftType,
        requirement.shiftTypeCoefficients ?? [],
        shiftTypeData
      ),
      required_num_people: requirement.requiredNumPeople,
      // Normalize the backend's implicit all-people representation for the UI.
      // Saving [ALL] back is intentional because the backend interprets null as [ALL].
      qualified_people: requirement.qualifiedPeople === null || requirement.qualifiedPeople === undefined
        ? [ALL]
        : requirement.qualifiedPeople,
      preferred_num_people: requirement.preferredNumPeople,
      date: requirement.date,
      weight: requirement.weight
    });
    setEditingIndex(index);
    setIsFormVisible(true);
    setErrors({});
    // Save current scroll position and scroll to top
    saveScrollPosition();
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  function handleCancel() {
    const wasEditing = editingIndex !== null;
    setIsFormVisible(false);
    resetForm();
    // Restore scroll position if we were editing
    if (wasEditing) {
      restoreScrollPosition();
    }
  }

  const validateForm = (): boolean => {
    const newErrors: ShiftTypeRequirementErrors = {};

    if (formData.shift_type.length === 0) {
      newErrors.shift_type = 'At least one shift type must be selected';
    }

    const coefficientValidation = validateCoefficientPairs(
      formData.shift_type,
      formData.shift_type_coefficients,
      shiftTypeData
    );
    if (Object.keys(coefficientValidation.errorsById).length > 0) {
      newErrors.shift_type_coefficients = Object.values(coefficientValidation.errorsById).join('\n');
      newErrors.shift_type_coefficients_by_id = coefficientValidation.errorsById;
    } else if (coefficientValidation.overlapError) {
      newErrors.shift_type_coefficients = coefficientValidation.overlapError;
      newErrors.shift_type_coefficients_by_id = {};
    } else if (formData.shift_type.length > 1) {
      newErrors.shift_type = 'Select exactly one shift type or group';
      newErrors.shift_type_coefficients_by_id = {};
    }

    if (formData.qualified_people.length === 0) {
      newErrors.qualified_people = 'At least one person must be selected';
    }

    if (formData.date.length === 0) {
      newErrors.date = 'At least one date must be selected';
    }

    if (formData.required_num_people === '') {
      newErrors.required_num_people = 'Required number of people must be a valid number';
    } else if (!isValidNumberValue(formData.required_num_people)) {
      newErrors.required_num_people = 'Required number of people must be a valid number';
    } else if (typeof formData.required_num_people === 'number' && formData.required_num_people < 0) {
      newErrors.required_num_people = 'Required number of people must be at least 0';
    }

    if (formData.preferred_num_people !== undefined && formData.preferred_num_people !== '') {
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

    if (preferredNumPeopleDiffersFromRequired(formData)) {
      if (!isValidWeightValue(formData.weight)) {
        newErrors.weight = 'Weight must be a valid number, Infinity, or -Infinity';
      } else if (typeof formData.weight === 'number' && formData.weight > 0) {
        newErrors.weight = 'Weight must be 0 or less (including -Infinity)';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const buildRequirementFromForm = (): ShiftTypeRequirementsPreference => {
    const usesWeight = preferredNumPeopleDiffersFromRequired(formData);
    const { coefficients: shiftTypeCoefficients } = validateCoefficientPairs(
      formData.shift_type,
      formData.shift_type_coefficients,
      shiftTypeData
    );
    return {
      type: SHIFT_TYPE_REQUIREMENT,
      description: formData.description,
      shiftType: formData.shift_type,
      ...(shiftTypeCoefficients.length > 0 ? { shiftTypeCoefficients } : {}),
      requiredNumPeople: formData.required_num_people as number,
      qualifiedPeople: formData.qualified_people,
      preferredNumPeople: usesWeight ? formData.preferred_num_people as number : undefined,
      date: formData.date,
      weight: usesWeight ? formData.weight as number : -1
    };
  };

  function saveDraft() {
    if (!validateForm()) return;

    const newRequirement = buildRequirementFromForm();

    const wasEditing = editingIndex !== null;
    if (wasEditing) {
      // Edit existing requirement
      const newRequirements = [...shiftTypeRequirements];
      newRequirements[editingIndex] = newRequirement;
      updateShiftTypeRequirements(newRequirements);
    } else {
      // Add new requirement
      updateShiftTypeRequirements([...shiftTypeRequirements, newRequirement]);
    }

    setIsFormVisible(false);
    resetForm();
    // Restore scroll position if we were editing
    if (wasEditing) {
      restoreScrollPosition();
    }
  }

  function handleSave() {
    saveDraft();
  }

  // Handle global keydown for Enter/Escape when form is visible
  useEffect(() => {
    if (!isFormVisible) return;

    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && !isImeCompositionKeyEvent(e)) {
        e.preventDefault();
        handleSave();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        handleCancel();
      }
    };

    document.addEventListener('keydown', handleGlobalKeyDown);
    return () => {
      document.removeEventListener('keydown', handleGlobalKeyDown);
    };
  });

  const dismissEditingDraft = () => {
    if (isFormVisible) {
      handleCancel();
    }
  };

  const handleDuplicate = (index: number) => {
    dismissEditingDraft();
    duplicatePreferenceByType(SHIFT_TYPE_REQUIREMENT, index);
  };

  const handleDelete = (index: number) => {
    dismissEditingDraft();
    const newRequirements = shiftTypeRequirements.filter((_, i) => i !== index);
    updateShiftTypeRequirements(newRequirements);
  };

  const handleReorder = (newRequirements: ShiftTypeRequirementsPreference[]) => {
    dismissEditingDraft();
    updateShiftTypeRequirements(newRequirements);
  };

  const handleArrayFieldToggle = (field: 'shift_type' | 'qualified_people' | 'date', id: string) => {
    setErrors(prev => ({ ...prev, [field]: '', ...(field === 'shift_type' ? { shift_type_coefficients: '', shift_type_coefficients_by_id: {} } : {}) }));
    setFormData(prev => ({
      ...prev,
      [field]: field === 'shift_type'
        ? [id]
        : (prev[field].includes(id)
            ? prev[field].filter(v => v !== id)
            : [...prev[field], id]),
      ...(field === 'shift_type'
        ? { shift_type_coefficients: syncCoefficientPairs([id], prev.shift_type_coefficients, shiftTypeData) }
        : {}),
    }));
  };

  const shiftTypeRequirementOptions = [
    ...shiftTypeData.items
      .filter(shiftType => shiftType.id !== OFF)
      .map(shiftType => ({
        id: shiftType.id,
        description: shiftType.description
      })),
    ...shiftTypeData.groups
      .filter(group => !group.members.includes(OFF))
      .map(group => ({
        id: group.id,
        description: group.description
      }))
  ];
  const shiftTypeEntries = getOrderedEntries(shiftTypeData);
  const usesWeight = preferredNumPeopleDiffersFromRequired(formData);
  const coverageWarning = useMemo(
    () => buildRequirementCoverageWarning(
      shiftTypeRequirements,
      dateData.items,
      dateData.groups,
      shiftTypeData.items,
      shiftTypeData.groups,
    ),
    [dateData.groups, dateData.items, shiftTypeData.groups, shiftTypeData.items, shiftTypeRequirements],
  );
  const warningExamplesLimit = 5;

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

      {(coverageWarning.undefinedShiftTypes.length > 0 || coverageWarning.duplicateCells.length > 0) && (
        <div className="mb-6 bg-amber-50 border border-amber-300 rounded-lg p-4 text-sm text-amber-900">
          <div className="flex items-center gap-2 font-semibold text-amber-950">
            <FiAlertCircle className="h-5 w-5" />
            Requirement coverage warnings
          </div>
          {coverageWarning.undefinedShiftTypes.length > 0 && (
            <div className="mt-2">
              <p>
                Undefined staffing requirements: {coverageWarning.undefinedPairsCount} date/shift type pairs have no requirement, so the solver may assign an arbitrary number of people.
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {coverageWarning.undefinedShiftTypes.map(entry => (
                  <li key={entry.shiftTypeId}>
                    <span className="font-medium">{entry.shiftTypeId}</span>: {entry.datesLabel}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {coverageWarning.duplicateCells.length > 0 && (
            <div className="mt-2">
              <p>
                Duplicate staffing requirements: {coverageWarning.duplicateCells.length} date/shift type pairs are covered by more than one requirement. The solver will apply all matching requirements.
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {coverageWarning.duplicateCells.slice(0, warningExamplesLimit).map(cell => (
                  <li key={cell}>{cell}</li>
                ))}
                {coverageWarning.duplicateCells.length > warningExamplesLimit && (
                  <li>...</li>
                )}
              </ul>
            </div>
          )}
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
                {shiftTypeRequirementOptions.length === 0 ? (
                  <div className="text-sm text-gray-500 italic p-4 text-center border border-gray-200 rounded-lg bg-gray-50">
                    No shift types available. Please set up shift types in the{' '}
                    <Link href="/shift-types" className="text-blue-600 hover:text-blue-800 underline">
                      Shift Types
                    </Link>{' '}
                    tab first.
                  </div>
                ) : (
                  <CheckboxList
                    items={shiftTypeRequirementOptions}
                    selectedIds={formData.shift_type}
                    onToggle={(id) => handleArrayFieldToggle('shift_type', id)}
                    label=""
                    inputType="radio"
                    inputName="shift-type-requirement-shift-type"
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
                  <NumberInput
                    min="0"
                    value={formData.required_num_people}
                    onChange={(e) => setFormData(prev => {
                      setErrors(currentErrors => ({ ...currentErrors, required_num_people: '' }));
                      if (e.target.value === '') {
                        return {
                          ...prev,
                          required_num_people: '',
                        };
                      }
                      // Note that the isNaN check is necessary, since a simple parseInt(e.target.value) will return 0 if the value is exactly 0.
                      const newRequiredValue = isNaN(parseInt(e.target.value)) ? prev.required_num_people : parseInt(e.target.value);
                      return {
                        ...prev,
                        required_num_people: newRequiredValue,
                        // If required_num_people has been parsed correctly and changed to same as preferred_num_people, also change preferred_num_people to undefined
                        preferred_num_people: !isNaN(parseInt(e.target.value)) && newRequiredValue === prev.preferred_num_people
                          || prev.preferred_num_people === ''
                          ? undefined
                          : prev.preferred_num_people,
                      };
                    })}
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
                  <NumberInput
                    min="1"
                    value={formData.preferred_num_people ?? formData.required_num_people}
                    onChange={(e) => {
                      setErrors(currentErrors => ({ ...currentErrors, preferred_num_people: '' }));
                      setFormData(prev => ({
                        ...prev,
                        preferred_num_people: e.target.value === ''
                          ? ''
                          : (isNaN(parseInt(e.target.value))
                              ? prev.preferred_num_people
                              : (parseInt(e.target.value) === prev.required_num_people
                                  ? undefined
                                  : parseInt(e.target.value)))
                      }));
                    }}
                    className={`block w-full px-4 py-2 text-sm text-gray-900 bg-white border rounded-lg shadow-sm transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 hover:border-gray-400 ${
                      errors.preferred_num_people
                        ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
                        : 'border-gray-300 focus:border-blue-500 focus:ring-blue-200'
                    }`}
                    placeholder="Will automatically be set to required number of people if left empty"
                  />
                  {errors.preferred_num_people && (
                    <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
                      <FiAlertCircle className="h-4 w-4" />
                      {errors.preferred_num_people}
                    </p>
                  )}
                </div>
              </div>

              {/* Shift Type Coefficients */}
              <div>
                <CountShiftTypeCoefficientFields
                  selectedShiftTypeIds={formData.shift_type}
                  coefficients={formData.shift_type_coefficients}
                  shiftTypeEntries={shiftTypeEntries}
                  shiftTypeData={shiftTypeData}
                  errorsById={errors.shift_type_coefficients_by_id}
                  label="Shift Type"
                  onChange={(coefficients, changedShiftTypeId) => {
                    setFormData(prev => ({
                      ...prev,
                      shift_type_coefficients: coefficients,
                    }));
                    setErrors(prev => {
                      const nextCoefficientErrors = { ...prev.shift_type_coefficients_by_id };
                      delete nextCoefficientErrors[changedShiftTypeId];
                      return {
                        ...prev,
                        shift_type_coefficients: Object.values(nextCoefficientErrors).join('\n'),
                        shift_type_coefficients_by_id: nextCoefficientErrors,
                      };
                    });
                  }}
                />
                {errors.shift_type_coefficients && (
                  <div className="mt-2 space-y-1">
                    {errors.shift_type_coefficients.split('\n').map(error => (
                      <p key={error} className="text-sm text-red-600 flex items-center gap-1">
                        <FiAlertCircle className="h-4 w-4" />
                        {error}
                      </p>
                    ))}
                  </div>
                )}
              </div>

              {/* Qualified People */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Qualified People *
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
                {errors.qualified_people && (
                  <p className="mt-1 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {errors.qualified_people}
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
              {usesWeight ? (
                <WeightInput
                  value={formData.weight}
                  onChange={(value) => {
                    setErrors(prev => ({ ...prev, weight: '' }));
                    setFormData(prev => ({ ...prev, weight: value }));
                  }}
                  error={errors.weight}
                  placeholder="e.g., -1, -10, ∞"
                />
              ) : (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Weight (priority)
                  </label>
                  <div className="text-sm text-gray-500 italic">
                    Weight is not needed when the preferred number of people equals the required number.
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex flex-col gap-3 pt-4 sm:flex-row sm:items-center sm:justify-between">
                <div />
                <div className="flex flex-wrap justify-end gap-3">
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
        </div>
      )}

      {/* Requirements List */}
      <DraggableCardList
        title="Current Requirements"
        items={shiftTypeRequirements}
        emptyMessage='No requirements defined yet. Click "Add Requirement" to get started.'
        onEdit={handleStartEdit}
        onDuplicate={handleDuplicate}
        onDelete={handleDelete}
        onReorder={handleReorder}
        renderContent={(requirement) => (
          <>
            {requirement.description && (
              <h4 className="font-medium text-gray-900 mb-3">{requirement.description}</h4>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-sm text-gray-600">
              <div>
                <span className="font-medium">Shift Types:</span>{' '}
                {requirement.shiftType.join(', ')}
              </div>
              {requirement.shiftTypeCoefficients && (
                <div>
                  <span className="font-medium">Coefficients:</span>{' '}
                  {requirement.shiftTypeCoefficients.map(([id, coefficient]) => `[${id}, ${coefficient}]`).join(', ')}
                </div>
              )}
              <div>
                <span className="font-medium">Required:</span> {requirement.requiredNumPeople}
                {requirement.preferredNumPeople && (
                  <span> (Preferred: {requirement.preferredNumPeople})</span>
                )}
              </div>
              {requirement.preferredNumPeople !== undefined && requirement.preferredNumPeople !== requirement.requiredNumPeople && (
                <div>
                  <span className="font-medium">Weight:</span> {getWeightWithPositivePrefix(requirement.weight)}
                </div>
              )}
              {requirement.qualifiedPeople && (
                <div className="md:col-span-2 lg:col-span-3">
                  <span className="font-medium">Qualified:</span>{' '}
                  {requirement.qualifiedPeople.join(', ')}
                </div>
              )}
              {requirement.date && (
                <div className="md:col-span-2 lg:col-span-3">
                  <span className="font-medium">Dates:</span>{' '}
                  {requirement.date.join(', ')}
                </div>
              )}
            </div>
          </>
        )}
      />
    </div>
  );
}
