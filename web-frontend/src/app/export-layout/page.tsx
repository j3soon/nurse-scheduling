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

// The export layout page for Tab "9. Export Layout"
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { FiAlertCircle, FiHelpCircle, FiRefreshCw, FiTrash2 } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import {
  ExportExtraColumn,
  ExportExtraRow,
  ExportFormatting,
  ExportFormattingType,
  ExportRequestShape,
  ShiftCountTypeCoefficient
} from '@/types/scheduling';
import { CheckboxList } from '@/components/CheckboxList';
import { CountShiftTypeCoefficientFields } from '@/components/CountShiftTypeCoefficientFields';
import ToggleButton from '@/components/ToggleButton';
import { DraggableCardList } from '@/components/DraggableCardList';
import WeightInput from '@/components/WeightInput';
import { saveScrollPosition, restoreScrollPosition } from '@/utils/scrolling';
import { isValidWeightValue, parseWeightValue } from '@/utils/numberParsing';
import { useTabSwitchWarning } from '@/utils/unsavedEditingState';
import { isImeCompositionKeyEvent } from '@/utils/keyboardEvents';
import {
  DraftShiftCountTypeCoefficient,
  syncCoefficientPairs,
  validateCoefficientPairs,
} from '@/utils/countShiftTypeCoefficients';

type RuleKind = 'style' | 'extra column' | 'extra row';
type ColorField = 'backgroundColor' | 'bottomBorderColor' | 'rightBorderColor' | 'fontColor';
type DraftArrayField = 'people' | 'dates' | 'shiftTypes' | 'countShiftTypes' | 'countDates' | 'countPeople' | 'requestShape';

interface DraftRule {
  description: string;
  kind: RuleKind;
  type: ExportFormattingType;
  people: string[];
  dates: string[];
  shiftTypes: string[];
  backgroundColor: string;
  bottomBorderColor: string;
  rightBorderColor: string;
  fontColor: string;
  header: string;
  countShiftTypes: string[];
  countShiftTypeCoefficients: DraftShiftCountTypeCoefficient[];
  countDates: string[];
  countPeople: string[];
  requestShape: string[];
  satisfied: '' | 'true' | 'false';
  weightRangeMin: number | string;
  weightRangeMax: number | string;
  appendText: string;
  noteText: string;
}

interface EditingTarget {
  kind: RuleKind;
  index: number;
}

interface ExportLayoutErrors {
  header?: string;
  backgroundColor?: string;
  bottomBorderColor?: string;
  rightBorderColor?: string;
  fontColor?: string;
  people?: string;
  dates?: string;
  shiftTypes?: string;
  countShiftTypes?: string;
  countShiftTypeCoefficients?: string;
  countShiftTypeCoefficientsById?: Record<string, string>;
  countDates?: string;
  countPeople?: string;
  requestShape?: string;
  weightRangeMin?: string;
  weightRangeMax?: string;
  styleFields?: string;
}

type ExportLayoutErrorField = Exclude<keyof ExportLayoutErrors, 'countShiftTypeCoefficientsById'>;

interface SelectOption {
  id: string;
  description: string;
}

const HEX_COLOR_PATTERN = /^#[0-9a-fA-F]{6}$/;
const REQUEST_SHAPE_OPTIONS: SelectOption[] = [
  { id: 'ALL', description: 'All request shapes' },
  { id: 'person-item-to-date-item', description: 'Person item to date item' },
  { id: 'people-group-to-date-item', description: 'People group to date item' },
  { id: 'person-item-to-date-group', description: 'Person item to date group' },
  { id: 'people-group-to-date-group', description: 'People group to date group' },
];

const styleUsesPeople = (type: ExportFormattingType) =>
  type === 'row' || type === 'people header' || type === 'history' || type === 'cell';

const styleUsesDates = (type: ExportFormattingType) =>
  type === 'column' || type === 'date header' || type === 'cell';

const styleUsesShiftTypes = (type: ExportFormattingType) => type === 'cell';

const createEmptyDraft = (): DraftRule => ({
  description: '',
  kind: 'style',
  type: 'cell',
  people: [],
  dates: [],
  shiftTypes: [],
  backgroundColor: '',
  bottomBorderColor: '',
  rightBorderColor: '',
  fontColor: '',
  header: '',
  countShiftTypes: [],
  countShiftTypeCoefficients: [],
  countDates: [],
  countPeople: [],
  requestShape: [],
  satisfied: '',
  weightRangeMin: '',
  weightRangeMax: '',
  appendText: '',
  noteText: '',
});

const getPickerDisplay = (value: string) => {
  const isValidHexColor = HEX_COLOR_PATTERN.test(value);
  const hasColorInput = value.length > 0;
  const pickerValue = isValidHexColor ? value : '#ffffff';
  const pickerText = hasColorInput
    ? (isValidHexColor ? value : '(Invalid)')
    : 'Default';
  const pickerTextColor = (() => {
    if (hasColorInput && !isValidHexColor) return '#b91c1c';
    if (!isValidHexColor) return '#4b5563';
    const hex = value.slice(1);
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.6 ? '#111827' : '#f9fafb';
  })();
  return { pickerValue, pickerText, pickerTextColor };
};

export default function ExportFormattingPage() {
  const {
    effectiveExportData,
    updateExportFormatting,
    updateExportExtraColumns,
    updateExportExtraRows,
    updateExportConfig,
    duplicateExportFormatting,
    duplicateExportExtraColumn,
    duplicateExportExtraRow,
    peopleData,
    dateData,
    shiftTypeData
  } = useSchedulingData();
  const [showInstructions, setShowInstructions] = useState(false);
  const [isFormVisible, setIsFormVisible] = useState(false);
  const [editingTarget, setEditingTarget] = useState<EditingTarget | null>(null);
  const [errors, setErrors] = useState<ExportLayoutErrors>({});
  const [draft, setDraft] = useState<DraftRule>(createEmptyDraft);
  useTabSwitchWarning(isFormVisible);

  const formattingRules = effectiveExportData.formatting || [];
  const extraColumns = effectiveExportData.extraColumns || [];
  const extraRows = effectiveExportData.extraRows || [];

  const clearAllExportLayoutEntries = () => {
    if (confirm('Are you sure you want to clear ALL export layout entries?')) {
      updateExportConfig({
        formatting: [],
        extraColumns: [],
        extraRows: []
      });
    }
  };

  const clearAllAndRegenerateExportLayoutEntries = () => {
    if (confirm('Are you sure you want to clear ALL export layout entries and regenerate them?')) {
      updateExportConfig(undefined);
    }
  };

  const clearStyleRules = () => {
    if (confirm('Are you sure you want to clear all export style rules?')) {
      updateExportFormatting([]);
    }
  };

  const clearExtraColumns = () => {
    if (confirm('Are you sure you want to clear all export extra columns?')) {
      updateExportExtraColumns([]);
    }
  };

  const clearExtraRows = () => {
    if (confirm('Are you sure you want to clear all export extra rows?')) {
      updateExportExtraRows([]);
    }
  };

  const dismissEditingDraft = () => {
    if (isFormVisible) {
      handleCancel();
    }
  };

  const deleteStyleRule = (index: number) => {
    dismissEditingDraft();
    updateExportFormatting(formattingRules.filter((_, i) => i !== index));
  };

  const deleteExtraColumn = (index: number) => {
    dismissEditingDraft();
    updateExportExtraColumns(extraColumns.filter((_, i) => i !== index));
  };

  const deleteExtraRow = (index: number) => {
    dismissEditingDraft();
    updateExportExtraRows(extraRows.filter((_, i) => i !== index));
  };

  const handleDuplicateStyleRule = (index: number) => {
    dismissEditingDraft();
    duplicateExportFormatting(index);
  };

  const handleDuplicateExtraColumn = (index: number) => {
    dismissEditingDraft();
    duplicateExportExtraColumn(index);
  };

  const handleDuplicateExtraRow = (index: number) => {
    dismissEditingDraft();
    duplicateExportExtraRow(index);
  };

  const handleReorderStyleRules = (newItems: typeof formattingRules) => {
    dismissEditingDraft();
    updateExportFormatting(newItems);
  };

  const handleReorderExtraColumns = (newItems: typeof extraColumns) => {
    dismissEditingDraft();
    updateExportExtraColumns(newItems);
  };

  const handleReorderExtraRows = (newItems: typeof extraRows) => {
    dismissEditingDraft();
    updateExportExtraRows(newItems);
  };

  const peopleOptions = [
    ...peopleData.items.map(person => ({ id: person.id, description: person.description })),
    ...peopleData.groups.map(group => ({ id: group.id, description: group.description })),
  ];
  const dateOptions = [
    ...dateData.items.map(date => ({ id: date.id, description: date.description })),
    ...dateData.groups.map(group => ({ id: group.id, description: group.description })),
  ];
  const shiftTypeOptions = [
    // OFF is already included as autogenerated item, so no need to include it again here.
    ...shiftTypeData.items.map(shiftType => ({ id: shiftType.id, description: shiftType.description })),
    ...shiftTypeData.groups.map(group => ({ id: group.id, description: group.description })),
  ];

  const instructions = [
    'Create export style rules and extra count columns or rows for prettified XLSX output',
    'Style rules change cell appearance; extra columns add per-person count summaries',
    'Extra rows add per-date count summaries',
    'Extra columns count selected shift types over selected dates',
    'Use #RRGGBB for color values',
    'Rules are evaluated in order within each section'
  ];

  const validateColor = (value: string, fieldLabel: string): string | null => {
    if (!value) return null;
    if (!HEX_COLOR_PATTERN.test(value)) {
      return `${fieldLabel} must be a valid hex color in #RRGGBB format`;
    }
    return null;
  };

  const renderErrorMessages = (error?: string, className = 'mt-2') => {
    if (!error) return null;

    return (
      <div className={`${className} space-y-1`}>
        {error.split('\n').map(message => (
          <p key={message} className="text-sm text-red-600 flex items-center gap-1">
            <FiAlertCircle className="h-4 w-4" />
            {message}
          </p>
        ))}
      </div>
    );
  };

  const inputClassName = (hasError?: boolean) =>
    `px-3 py-2 border rounded-md w-full ${
      hasError
        ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
        : 'border-gray-300'
    }`;

  const clearError = (field: ExportLayoutErrorField) => {
    setErrors(prev => ({ ...prev, [field]: '' }));
  };

  const resetForm = () => {
    setDraft(createEmptyDraft());
    setErrors({});
    setEditingTarget(null);
  };

  const handleStartAdd = () => {
    resetForm();
    setIsFormVisible(true);
  };

  const handleStartEditStyle = (index: number) => {
    const rule = formattingRules[index];
    const weightRange = 'when' in rule ? rule.when?.preference.weightRange : undefined;
    const hasValidWeightRange = Array.isArray(weightRange) && weightRange.length === 2;
    setDraft({
      ...createEmptyDraft(),
      description: rule.description || '',
      kind: 'style',
      type: rule.type,
      people: 'people' in rule ? rule.people : [],
      dates: 'dates' in rule ? rule.dates : [],
      shiftTypes: 'shiftTypes' in rule ? rule.shiftTypes : [],
      backgroundColor: rule.backgroundColor || '',
      bottomBorderColor: rule.bottomBorderColor || '',
      rightBorderColor: rule.rightBorderColor || '',
      fontColor: rule.fontColor || '',
      requestShape: 'when' in rule && rule.when?.preference.requestShape ? rule.when.preference.requestShape : [],
      satisfied: 'when' in rule && rule.when?.preference.satisfied !== undefined
        ? String(rule.when.preference.satisfied) as 'true' | 'false'
        : '',
      weightRangeMin: hasValidWeightRange ? weightRange[0] ?? '' : '',
      weightRangeMax: hasValidWeightRange ? weightRange[1] ?? '' : '',
      appendText: 'appendText' in rule ? rule.appendText || '' : '',
      noteText: 'note' in rule ? rule.note?.text || '' : '',
    });
    setErrors(weightRange !== undefined && !hasValidWeightRange
      ? { weightRangeMin: 'Weight Range must contain exactly two values' }
      : {});
    setEditingTarget({ kind: 'style', index });
    setIsFormVisible(true);
    saveScrollPosition();
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  const handleStartEditExtraColumn = (index: number) => {
    const rule = extraColumns[index];
    setDraft({
      ...createEmptyDraft(),
      description: rule.description || '',
      kind: 'extra column',
      header: rule.header,
      countShiftTypes: rule.countShiftTypes,
      countShiftTypeCoefficients: syncCoefficientPairs(
        rule.countShiftTypes,
        rule.countShiftTypeCoefficients ?? [],
        shiftTypeData
      ),
      countDates: rule.countDates,
      rightBorderColor: rule.rightBorderColor || '',
    });
    setEditingTarget({ kind: 'extra column', index });
    setIsFormVisible(true);
    setErrors({});
    saveScrollPosition();
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  const handleStartEditExtraRow = (index: number) => {
    const rule = extraRows[index];
    setDraft({
      ...createEmptyDraft(),
      description: rule.description || '',
      kind: 'extra row',
      header: rule.header,
      countShiftTypes: rule.countShiftTypes,
      countPeople: rule.countPeople,
      bottomBorderColor: rule.bottomBorderColor || '',
    });
    setEditingTarget({ kind: 'extra row', index });
    setIsFormVisible(true);
    setErrors({});
    saveScrollPosition();
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  const handleCancel = () => {
    const wasEditing = editingTarget !== null;
    setIsFormVisible(false);
    resetForm();
    if (wasEditing) {
      restoreScrollPosition();
    }
  };

  const hasErrors = (nextErrors: ExportLayoutErrors) =>
    Object.values(nextErrors).some(value => {
      if (typeof value === 'string') return value.length > 0;
      if (value && typeof value === 'object') return Object.keys(value).length > 0;
      return false;
    });

  const getSelectedOptionsError = (
    label: string,
    selectedIds: string[],
    options: SelectOption[],
    invalidMessage = `Selected ${label.toLowerCase()} are invalid for this rule type`
  ) => {
    if (selectedIds.length === 0) {
      return `Select at least one ${label.toLowerCase()}`;
    }

    const validIds = new Set(options.map(option => option.id));
    if (selectedIds.some(id => !validIds.has(id))) {
      return invalidMessage;
    }

    return undefined;
  };

  const addStyleTargetErrors = (nextErrors: ExportLayoutErrors) => {
    if (styleUsesPeople(draft.type)) {
      const error = getSelectedOptionsError('people', draft.people, peopleOptions);
      if (error) nextErrors.people = error;
    }
    if (styleUsesDates(draft.type)) {
      const error = getSelectedOptionsError('dates', draft.dates, dateOptions);
      if (error) nextErrors.dates = error;
    }
    if (styleUsesShiftTypes(draft.type)) {
      const error = getSelectedOptionsError('shift types', draft.shiftTypes, shiftTypeOptions);
      if (error) nextErrors.shiftTypes = error;
    }
  };

  const parseOptionalWeightRange = (nextErrors: ExportLayoutErrors): [number, number] | undefined | null => {
    const minInput = String(draft.weightRangeMin).trim();
    const maxInput = String(draft.weightRangeMax).trim();
    if (!minInput && !maxInput) {
      return undefined;
    }
    if (!minInput || !maxInput) {
      if (!minInput) nextErrors.weightRangeMin = 'Weight Range minimum is required when maximum is set';
      if (!maxInput) nextErrors.weightRangeMax = 'Weight Range maximum is required when minimum is set';
      return null;
    }
    const minWeight = parseWeightValue(minInput);
    const maxWeight = parseWeightValue(maxInput);
    if (!isValidWeightValue(minWeight) || !isValidWeightValue(maxWeight)) {
      if (!isValidWeightValue(minWeight)) {
        nextErrors.weightRangeMin = 'Minimum Weight must be a valid number, Infinity, or -Infinity';
      }
      if (!isValidWeightValue(maxWeight)) {
        nextErrors.weightRangeMax = 'Maximum Weight must be a valid number, Infinity, or -Infinity';
      }
      return null;
    }
    if (minWeight > maxWeight) {
      nextErrors.weightRangeMin = 'Weight Range minimum must be less than or equal to maximum';
      nextErrors.weightRangeMax = 'Weight Range minimum must be less than or equal to maximum';
      return null;
    }
    return [minWeight as number, maxWeight as number];
  };

  const saveStyleRule = () => {
    const description = draft.description.trim();
    const backgroundColor = draft.backgroundColor.trim().toLowerCase();
    const bottomBorderColor = draft.bottomBorderColor.trim().toLowerCase();
    const rightBorderColor = draft.rightBorderColor.trim().toLowerCase();
    const fontColor = draft.fontColor.trim().toLowerCase();
    const appendText = draft.appendText;
    const noteText = draft.noteText.trim();
    const hasCondition = draft.requestShape.length > 0 || draft.satisfied !== '' || Boolean(String(draft.weightRangeMin).trim() || String(draft.weightRangeMax).trim());
    const nextErrors: ExportLayoutErrors = {};

    addStyleTargetErrors(nextErrors);
    const weightRange = parseOptionalWeightRange(nextErrors);

    const backgroundColorError = validateColor(backgroundColor, 'Background Color');
    if (backgroundColorError) {
      nextErrors.backgroundColor = backgroundColorError;
    }
    const bottomBorderColorError = validateColor(bottomBorderColor, 'Bottom Border Color');
    if (bottomBorderColorError) {
      nextErrors.bottomBorderColor = bottomBorderColorError;
    }
    const rightBorderColorError = validateColor(rightBorderColor, 'Right Border Color');
    if (rightBorderColorError) {
      nextErrors.rightBorderColor = rightBorderColorError;
    }
    const fontColorError = validateColor(fontColor, 'Font Color');
    if (fontColorError) {
      nextErrors.fontColor = fontColorError;
    }
    if (!backgroundColor && !bottomBorderColor && !rightBorderColor && !fontColor && !appendText && !noteText) {
      nextErrors.styleFields = 'At least one style or annotation field is required';
    }

    if (weightRange === null || hasErrors(nextErrors)) {
      setErrors(nextErrors);
      return false;
    }

    const styleFields = {
      ...(description ? { description } : {}),
      ...(backgroundColor ? { backgroundColor } : {}),
      ...(bottomBorderColor ? { bottomBorderColor } : {}),
      ...(rightBorderColor ? { rightBorderColor } : {}),
      ...(fontColor ? { fontColor } : {}),
    };
    let newRule: ExportFormatting;
    if (draft.type === 'cell') {
      newRule = {
        ...styleFields,
        type: draft.type,
        ...(appendText ? { appendText } : {}),
        ...(noteText ? { note: { text: noteText } } : {}),
        people: draft.people,
        dates: draft.dates,
        shiftTypes: draft.shiftTypes,
        ...(hasCondition ? {
          when: {
            preference: {
              types: ['shift request'],
              ...(draft.requestShape.length > 0 ? { requestShape: draft.requestShape as ExportRequestShape[] } : {}),
              ...(draft.satisfied ? { satisfied: draft.satisfied === 'true' } : {}),
              ...(weightRange ? { weightRange } : {})
            }
          }
        } : {}),
      };
    } else if (draft.type === 'column' || draft.type === 'date header') {
      newRule = {
        ...styleFields,
        type: draft.type,
        dates: draft.dates
      };
    } else if (draft.type === 'history header') {
      newRule = {
        ...styleFields,
        type: draft.type
      };
    } else {
      newRule = {
        ...styleFields,
        type: draft.type,
        people: draft.people
      };
    }

    const nextFormatting = [...formattingRules];
    const nextExtraColumns = [...extraColumns];
    const nextExtraRows = [...extraRows];
    if (editingTarget?.kind === 'style') {
      nextFormatting[editingTarget.index] = newRule;
    } else {
      if (editingTarget?.kind === 'extra column') {
        nextExtraColumns.splice(editingTarget.index, 1);
      } else if (editingTarget?.kind === 'extra row') {
        nextExtraRows.splice(editingTarget.index, 1);
      }
      nextFormatting.push(newRule);
    }
    updateExportConfig({
      ...effectiveExportData,
      formatting: nextFormatting,
      extraColumns: nextExtraColumns,
      extraRows: nextExtraRows,
    });
    return true;
  };

  const saveExtraColumn = () => {
    const header = draft.header.trim();
    const description = draft.description.trim();
    const rightBorderColor = draft.rightBorderColor.trim().toLowerCase();
    const nextErrors: ExportLayoutErrors = {};
    if (!header) {
      nextErrors.header = 'Column header is required';
    }
    const rightBorderColorError = validateColor(rightBorderColor, 'Right Border Color');
    if (rightBorderColorError) {
      nextErrors.rightBorderColor = rightBorderColorError;
    }
    if (draft.countShiftTypes.length === 0) {
      nextErrors.countShiftTypes = 'Select at least one shift type to count';
    } else {
      const countShiftTypeError = getSelectedOptionsError(
        'shift type',
        draft.countShiftTypes,
        shiftTypeOptions,
        'Selected shift types are invalid for this extra column'
      );
      if (countShiftTypeError) nextErrors.countShiftTypes = countShiftTypeError;
    }
    if (draft.countDates.length === 0) {
      nextErrors.countDates = 'Select at least one date target to count over';
    } else {
      const countDatesError = getSelectedOptionsError(
        'date target',
        draft.countDates,
        dateOptions,
        'Selected dates are invalid for this extra column'
      );
      if (countDatesError) nextErrors.countDates = countDatesError;
    }

    let countShiftTypeCoefficients: ShiftCountTypeCoefficient[] = [];
    if (!nextErrors.countShiftTypes) {
      const coefficientValidation = validateCoefficientPairs(
        draft.countShiftTypes,
        draft.countShiftTypeCoefficients,
        shiftTypeData
      );
      countShiftTypeCoefficients = coefficientValidation.coefficients;
      if (Object.keys(coefficientValidation.errorsById).length > 0) {
        nextErrors.countShiftTypeCoefficients = Object.values(coefficientValidation.errorsById).join('\n');
        nextErrors.countShiftTypeCoefficientsById = coefficientValidation.errorsById;
      } else if (coefficientValidation.overlapError) {
        nextErrors.countShiftTypeCoefficients = coefficientValidation.overlapError;
        nextErrors.countShiftTypeCoefficientsById = {};
      }
    }

    if (hasErrors(nextErrors)) {
      setErrors(nextErrors);
      return false;
    }

    const newRule: ExportExtraColumn = {
      description,
      type: 'count',
      header,
      countShiftTypes: draft.countShiftTypes,
      ...(countShiftTypeCoefficients.length > 0 ? { countShiftTypeCoefficients } : {}),
      countDates: draft.countDates,
      ...(rightBorderColor ? { rightBorderColor } : {})
    };

    const nextFormatting = [...formattingRules];
    const nextExtraColumns = [...extraColumns];
    const nextExtraRows = [...extraRows];
    if (editingTarget?.kind === 'extra column') {
      nextExtraColumns[editingTarget.index] = newRule;
    } else {
      if (editingTarget?.kind === 'style') {
        nextFormatting.splice(editingTarget.index, 1);
      } else if (editingTarget?.kind === 'extra row') {
        nextExtraRows.splice(editingTarget.index, 1);
      }
      nextExtraColumns.push(newRule);
    }
    updateExportConfig({
      ...effectiveExportData,
      formatting: nextFormatting,
      extraColumns: nextExtraColumns,
      extraRows: nextExtraRows,
    });
    return true;
  };

  const saveExtraRow = () => {
    const header = draft.header.trim();
    const description = draft.description.trim();
    const bottomBorderColor = draft.bottomBorderColor.trim().toLowerCase();
    const nextErrors: ExportLayoutErrors = {};
    if (!header) {
      nextErrors.header = 'Row header is required';
    }
    const bottomBorderColorError = validateColor(bottomBorderColor, 'Bottom Border Color');
    if (bottomBorderColorError) {
      nextErrors.bottomBorderColor = bottomBorderColorError;
    }
    if (draft.countShiftTypes.length === 0) {
      nextErrors.countShiftTypes = 'Select at least one shift type to count';
    } else {
      const countShiftTypeError = getSelectedOptionsError(
        'shift type',
        draft.countShiftTypes,
        shiftTypeOptions,
        'Selected shift types are invalid for this extra row'
      );
      if (countShiftTypeError) nextErrors.countShiftTypes = countShiftTypeError;
    }
    if (draft.countPeople.length === 0) {
      nextErrors.countPeople = 'Select at least one people target to count over';
    } else {
      const countPeopleError = getSelectedOptionsError(
        'people target',
        draft.countPeople,
        peopleOptions,
        'Selected people are invalid for this extra row'
      );
      if (countPeopleError) nextErrors.countPeople = countPeopleError;
    }

    if (hasErrors(nextErrors)) {
      setErrors(nextErrors);
      return false;
    }

    const newRule: ExportExtraRow = {
      description,
      type: 'count',
      header,
      countShiftTypes: draft.countShiftTypes,
      countPeople: draft.countPeople,
      ...(bottomBorderColor ? { bottomBorderColor } : {})
    };

    const nextFormatting = [...formattingRules];
    const nextExtraColumns = [...extraColumns];
    const nextExtraRows = [...extraRows];
    if (editingTarget?.kind === 'extra row') {
      nextExtraRows[editingTarget.index] = newRule;
    } else {
      if (editingTarget?.kind === 'style') {
        nextFormatting.splice(editingTarget.index, 1);
      } else if (editingTarget?.kind === 'extra column') {
        nextExtraColumns.splice(editingTarget.index, 1);
      }
      nextExtraRows.push(newRule);
    }
    updateExportConfig({
      ...effectiveExportData,
      formatting: nextFormatting,
      extraColumns: nextExtraColumns,
      extraRows: nextExtraRows,
    });
    return true;
  };

  const handleSave = () => {
    const wasEditing = editingTarget !== null;
    const didSave = draft.kind === 'style'
      ? saveStyleRule()
      : draft.kind === 'extra column'
        ? saveExtraColumn()
        : saveExtraRow();
    if (!didSave) return;

    setIsFormVisible(false);
    resetForm();
    if (wasEditing) {
      restoreScrollPosition();
    }
  };

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

  const renderColorField = (field: ColorField, label: string) => {
    const value = draft[field];
    const error = errors[field];
    const { pickerValue, pickerText, pickerTextColor } = getPickerDisplay(value);
    return (
      <div className="space-y-1">
        <label className="block text-sm font-medium text-gray-700">{label}</label>
        <div className="flex items-center gap-3">
          <div className="relative h-9 w-28">
            <input
              type="color"
              value={pickerValue}
              onChange={(e) => {
                clearError(field);
                clearError('styleFields');
                setDraft(prev => ({ ...prev, [field]: e.target.value }));
              }}
              className={`h-9 w-28 rounded border bg-white cursor-pointer ${
                error ? 'border-red-300' : 'border-gray-300'
              }`}
              title={`Choose ${label.toLowerCase()}`}
            />
            <span
              className="pointer-events-none absolute inset-0 flex items-center justify-center font-mono text-[11px]"
              style={{ color: pickerTextColor }}
            >
              {pickerText}
            </span>
          </div>
          <input
            type="text"
            value={value}
            onChange={(e) => {
              clearError(field);
              clearError('styleFields');
              setDraft(prev => ({ ...prev, [field]: e.target.value }));
            }}
            placeholder="#RRGGBB"
            className={`w-28 px-2 py-1.5 text-sm border rounded-md font-mono ${
              error ? 'border-red-300 focus:border-red-500 focus:ring-red-200' : 'border-gray-300'
            }`}
            title={`Enter ${label.toLowerCase()} in hex`}
          />
        </div>
        {renderErrorMessages(error)}
      </div>
    );
  };

  const renderCheckboxes = (
    label: string,
    options: SelectOption[],
    selectedIds: string[],
    onToggle: (id: string) => void,
    emptyText: string,
    href: string,
    hrefLabel: string,
    scrollable = false,
    error?: string
  ) => {
    const content = options.length === 0 ? (
        <div className="text-sm text-gray-500 italic p-4 text-center border border-gray-200 rounded-lg bg-gray-50">
          {emptyText}{' '}
          <Link href={href} className="text-blue-600 hover:text-blue-800 underline">
            {hrefLabel}
          </Link>{' '}
          tab first.
        </div>
      ) : (
        <CheckboxList
          items={options}
          selectedIds={selectedIds}
          onToggle={onToggle}
          label=""
        />
      );

    return (
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">{label}</label>
        {scrollable && options.length > 0 ? (
          <div className="max-h-32 overflow-y-auto">{content}</div>
        ) : content}
        {renderErrorMessages(error, 'mt-1')}
      </div>
    );
  };

  const toggleDraftArrayField = (field: DraftArrayField, id: string) => {
    clearError(field);
    if (field === 'countShiftTypes') {
      setErrors(prev => ({
        ...prev,
        countShiftTypeCoefficients: '',
        countShiftTypeCoefficientsById: {},
      }));
    }
    setDraft(prev => ({
      ...prev,
      [field]: prev[field].includes(id)
        ? prev[field].filter(targetId => targetId !== id)
        : [...prev[field], id],
      ...(field === 'countShiftTypes' ? {
        countShiftTypeCoefficients: syncCoefficientPairs(
          prev.countShiftTypes.includes(id)
            ? prev.countShiftTypes.filter(targetId => targetId !== id)
            : [...prev.countShiftTypes, id],
          prev.countShiftTypeCoefficients,
          shiftTypeData
        )
      } : {})
    }));
  };

  const setCoefficientPairs = (coefficients: DraftShiftCountTypeCoefficient[]) => {
    setDraft(prev => ({ ...prev, countShiftTypeCoefficients: coefficients }));
  };

  const clearCoefficientError = (shiftTypeId: string) => {
    setErrors(prev => {
      const nextCoefficientErrors = { ...prev.countShiftTypeCoefficientsById };
      delete nextCoefficientErrors[shiftTypeId];

      return {
        ...prev,
        countShiftTypeCoefficients: Object.values(nextCoefficientErrors).join('\n'),
        countShiftTypeCoefficientsById: nextCoefficientErrors,
      };
    });
  };

  const renderExtraColumnCoefficientFields = () => {
    if (draft.kind !== 'extra column') {
      return null;
    }

    return (
      <CountShiftTypeCoefficientFields
        selectedShiftTypeIds={draft.countShiftTypes}
        coefficients={draft.countShiftTypeCoefficients}
        shiftTypeEntries={[...shiftTypeData.items, ...shiftTypeData.groups]}
        shiftTypeData={shiftTypeData}
        errorsById={errors.countShiftTypeCoefficientsById}
        onChange={(coefficients, changedShiftTypeId) => {
          clearCoefficientError(changedShiftTypeId);
          setCoefficientPairs(coefficients);
        }}
      />
    );
  };

  const renderStyleTargetRows = () => (
    <div className="space-y-6">
      {styleUsesPeople(draft.type) && renderCheckboxes(
        'People *',
        peopleOptions,
        draft.people,
        (id) => toggleDraftArrayField('people', id),
        'No people available. Please set up people in the',
        '/people',
        'People',
        false,
        errors.people
      )}

      {styleUsesDates(draft.type) && renderCheckboxes(
        'Dates *',
        dateOptions,
        draft.dates,
        (id) => toggleDraftArrayField('dates', id),
        'No dates available. Please set up dates in the',
        '/dates',
        'Dates',
        true,
        errors.dates
      )}

      {styleUsesShiftTypes(draft.type) && renderCheckboxes(
        'Shift Types *',
        shiftTypeOptions,
        draft.shiftTypes,
        (id) => toggleDraftArrayField('shiftTypes', id),
        'No shift types available. Please set up shift types in the',
        '/shift-types',
        'Shift Types',
        false,
        errors.shiftTypes
      )}
    </div>
  );

  const renderCellAnnotationActionFields = () => {
    if (draft.kind !== 'style' || draft.type !== 'cell') {
      return null;
    }

    return (
      <div className="space-y-4 pt-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Append Text</label>
          <input
            type="text"
            value={draft.appendText}
            onChange={(e) => {
              clearError('styleFields');
              setDraft(prev => ({ ...prev, appendText: e.target.value }));
            }}
            placeholder=" [{shiftType}]"
            className="px-3 py-2 border border-gray-300 rounded-md w-full"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Note Text</label>
          <input
            type="text"
            value={draft.noteText}
            onChange={(e) => {
              clearError('styleFields');
              setDraft(prev => ({ ...prev, noteText: e.target.value }));
            }}
            placeholder="Weight of unmet single-style request: {totalAbsWeight}"
            className="px-3 py-2 border border-gray-300 rounded-md w-full"
          />
        </div>
      </div>
    );
  };

  const renderCellWhenFields = () => {
    if (draft.kind !== 'style' || draft.type !== 'cell') {
      return null;
    }

    return (
      <div className="space-y-4 border-t border-gray-200 pt-6">
        <div>
          <h3 className="text-sm font-medium text-gray-700">When (optional)</h3>
          <p className="text-xs text-gray-500 mt-1">
            Limits this cell rule to matching shift request preferences. Leave empty to match all selected cells.
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Satisfied</label>
          <select
            value={draft.satisfied}
            onChange={(e) => setDraft(prev => ({ ...prev, satisfied: e.target.value as DraftRule['satisfied'] }))}
            className="px-3 py-2 border border-gray-300 rounded-md w-full"
          >
            <option value="">Any</option>
            <option value="true">true</option>
            <option value="false">false</option>
          </select>
        </div>

        {renderCheckboxes(
          'Request Shape',
          REQUEST_SHAPE_OPTIONS,
          draft.requestShape,
          (id) => toggleDraftArrayField('requestShape', id),
          'No request shape options available.',
          '/shift-requests',
          'Shift Requests',
          false,
          errors.requestShape
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <WeightInput
            value={draft.weightRangeMin}
            onChange={(value) => {
              clearError('weightRangeMin');
              setDraft(prev => ({ ...prev, weightRangeMin: value }));
            }}
            error={errors.weightRangeMin}
            label="Minimum Weight (inclusive)"
            placeholder="-Infinity"
          />
          <WeightInput
            value={draft.weightRangeMax}
            onChange={(value) => {
              clearError('weightRangeMax');
              setDraft(prev => ({ ...prev, weightRangeMax: value }));
            }}
            error={errors.weightRangeMax}
            label="Maximum Weight (inclusive)"
            placeholder="Infinity"
          />
        </div>
      </div>
    );
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-800">Export Layout</h1>
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
        <ToggleButton
          label="Add Export Rule"
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

      <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
        <div className="flex items-start gap-2">
          <FiAlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
          <p>
            This page is experimental. Only modify export layout entries if you know exactly what you&apos;re doing.
          </p>
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

      <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200">
          <h3 className="text-lg font-semibold text-gray-800">Clear Data</h3>
          <p className="text-sm text-gray-600 mt-1">Remove or regenerate export layout entries with targeted operations</p>
        </div>
        <div className="px-4 py-3">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <button
              onClick={clearAllExportLayoutEntries}
              className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors flex items-center gap-2"
              title="Clear all export layout entries completely"
            >
              <FiTrash2 className="h-4 w-4" />
              Clear All
            </button>

            <button
              onClick={clearAllAndRegenerateExportLayoutEntries}
              className="px-4 py-2 text-sm font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-md transition-colors flex items-center gap-2"
              title="Clear all export layout entries and regenerate count entries from current shift types"
            >
              <FiRefreshCw className="h-4 w-4" />
              Clear All and Regenerate
            </button>

            <button
              onClick={clearStyleRules}
              className="px-4 py-2 text-sm font-medium text-rose-700 bg-rose-50 hover:bg-rose-100 rounded-md transition-colors flex items-center gap-2"
              title="Clear all export style rules"
            >
              <FiTrash2 className="h-4 w-4" />
              Clear Style Rules
            </button>

            <button
              onClick={clearExtraColumns}
              className="px-4 py-2 text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-md transition-colors flex items-center gap-2"
              title="Clear all export extra columns"
            >
              <FiTrash2 className="h-4 w-4" />
              Clear Extra Columns
            </button>

            <button
              onClick={clearExtraRows}
              className="px-4 py-2 text-sm font-medium text-purple-700 bg-purple-50 hover:bg-purple-100 rounded-md transition-colors flex items-center gap-2"
              title="Clear all export extra rows"
            >
              <FiTrash2 className="h-4 w-4" />
              Clear Extra Rows
            </button>
          </div>
        </div>
      </div>

      {isFormVisible && (
        <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
          <div className="px-6 py-4">
            <h2 className="text-lg font-semibold mb-4 text-gray-800">
              {editingTarget !== null ? 'Edit Export Rule' : 'Add Export Rule'}
            </h2>
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Description</label>
                <input
                  type="text"
                  value={draft.description}
                  onChange={(e) => setDraft(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Optional note for this export rule"
                  className="px-3 py-2 border border-gray-300 rounded-md w-full"
                />
              </div>

              <div className="flex flex-wrap items-start gap-4">
                <div className="min-w-[180px]">
                  <label className="block text-sm font-medium text-gray-700 mb-2">Rule Kind</label>
                  <select
                    value={draft.kind}
                    onChange={(e) => {
                      setErrors({});
                      setDraft(prev => ({
                        ...prev,
                        kind: e.target.value as RuleKind,
                        people: [],
                        dates: [],
                        shiftTypes: [],
                        countShiftTypes: [],
                        countShiftTypeCoefficients: [],
                        countDates: [],
                        countPeople: []
                      }));
                    }}
                    className="px-3 py-2 border border-gray-300 rounded-md w-full"
                  >
                    <option value="style">Style</option>
                    <option value="extra column">Extra Column</option>
                    <option value="extra row">Extra Row</option>
                  </select>
                </div>

                {draft.kind === 'style' ? (
                  <>
                    <div className="min-w-[180px]">
                      <label className="block text-sm font-medium text-gray-700 mb-2">Type</label>
                      <select
                        value={draft.type}
                        onChange={(e) => {
                          setErrors({});
                          setDraft(prev => ({
                            ...prev,
                            type: e.target.value as ExportFormattingType,
                            people: [],
                            dates: [],
                            shiftTypes: []
                          }));
                        }}
                        className="px-3 py-2 border border-gray-300 rounded-md w-full"
                      >
                        <option value="people header">people header</option>
                        <option value="row">row</option>
                        <option value="date header">date header</option>
                        <option value="column">column</option>
                        <option value="history header">history header</option>
                        <option value="history">history</option>
                        <option value="cell">cell</option>
                      </select>
                    </div>
                    <div className="min-w-[260px]">
                      {renderColorField('backgroundColor', 'Background Color')}
                    </div>
                    <div className="min-w-[260px]">
                      {renderColorField('bottomBorderColor', 'Bottom Border Color')}
                    </div>
                    <div className="min-w-[260px]">
                      {renderColorField('rightBorderColor', 'Right Border Color')}
                    </div>
                    <div className="min-w-[260px]">
                      {renderColorField('fontColor', 'Font Color')}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="min-w-[280px]">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        {draft.kind === 'extra column' ? 'Column Header' : 'Row Header'}
                      </label>
                      <input
                        type="text"
                        value={draft.header}
                        onChange={(e) => {
                          clearError('header');
                          setDraft(prev => ({ ...prev, header: e.target.value }));
                        }}
                        placeholder={draft.kind === 'extra column' ? 'OFF (Weekend)' : 'Day Count'}
                        className={inputClassName(Boolean(errors.header))}
                      />
                      {renderErrorMessages(errors.header)}
                    </div>
                    <div className="min-w-[260px]">
                      {draft.kind === 'extra column'
                        ? renderColorField('rightBorderColor', 'Right Border Color')
                        : renderColorField('bottomBorderColor', 'Bottom Border Color')}
                    </div>
                  </>
                )}
              </div>
              {draft.kind === 'style' && renderErrorMessages(errors.styleFields)}

              {draft.kind === 'style' ? (
                <>
                  {renderCellAnnotationActionFields()}
                  {renderStyleTargetRows()}
                  {renderCellWhenFields()}
                </>
              ) : (
                <div className="space-y-6">
                  {renderCheckboxes(
                    'Count Shift Types *',
                    shiftTypeOptions,
                    draft.countShiftTypes,
                    (id) => toggleDraftArrayField('countShiftTypes', id),
                    'No shift types available. Please set up shift types in the',
                    '/shift-types',
                    'Shift Types',
                    false,
                    errors.countShiftTypes
                  )}
                  {renderExtraColumnCoefficientFields()}
                  {draft.kind === 'extra column' && errors.countShiftTypeCoefficients && (
                    <div className="mt-2 space-y-1">
                      {errors.countShiftTypeCoefficients.split('\n').map(error => (
                        <p key={error} className="text-sm text-red-600 flex items-center gap-1">
                          <FiAlertCircle className="h-4 w-4" />
                          {error}
                        </p>
                      ))}
                    </div>
                  )}
                  {draft.kind === 'extra column'
                    ? renderCheckboxes(
                        'Count Dates *',
                        dateOptions,
                        draft.countDates,
                        (id) => toggleDraftArrayField('countDates', id),
                        'No dates available. Please set up dates in the',
                        '/dates',
                        'Dates',
                        false,
                        errors.countDates
                      )
                    : renderCheckboxes(
                        'Count People *',
                        peopleOptions,
                        draft.countPeople,
                        (id) => toggleDraftArrayField('countPeople', id),
                        'No people available. Please set up people in the',
                        '/people',
                        'People',
                        false,
                        errors.countPeople
                      )}
                </div>
              )}

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
                    {editingTarget !== null ? 'Update' : 'Add'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-6">
        <DraggableCardList
          title="Style Rules"
          items={formattingRules}
          emptyMessage='No style rules defined yet. Click "Add Export Rule" to get started.'
          onEdit={handleStartEditStyle}
          onDuplicate={handleDuplicateStyleRule}
          onDelete={deleteStyleRule}
          onReorder={handleReorderStyleRules}
          renderContent={(rule) => (
            <>
              {rule.description && (
                <h4 className="font-medium text-gray-900 mb-3">{rule.description}</h4>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-sm text-gray-600">
                <div>
                  <span className="font-medium">Type:</span> {rule.type}
                </div>
                {'people' in rule && rule.people.length > 0 && (
                  <div>
                    <span className="font-medium">People:</span> {rule.people.join(', ')}
                  </div>
                )}
                {'dates' in rule && rule.dates.length > 0 && (
                  <div>
                    <span className="font-medium">Dates:</span> {rule.dates.join(', ')}
                  </div>
                )}
                {'shiftTypes' in rule && rule.shiftTypes.length > 0 && (
                  <div>
                    <span className="font-medium">Shift Types:</span> {rule.shiftTypes.join(', ')}
                  </div>
                )}
                {rule.backgroundColor && (
                  <div>
                    <span className="font-medium">Background:</span> {rule.backgroundColor}
                  </div>
                )}
                {rule.bottomBorderColor && (
                  <div>
                    <span className="font-medium">Bottom Border:</span> {rule.bottomBorderColor}
                  </div>
                )}
                {rule.rightBorderColor && (
                  <div>
                    <span className="font-medium">Right Border:</span> {rule.rightBorderColor}
                  </div>
                )}
                {rule.fontColor && (
                  <div>
                    <span className="font-medium">Font:</span> {rule.fontColor}
                  </div>
                )}
                {'appendText' in rule && rule.appendText && (
                  <div>
                    <span className="font-medium">Append Text:</span> {rule.appendText}
                  </div>
                )}
                {'note' in rule && rule.note && (
                  <div>
                    <span className="font-medium">Note:</span> {rule.note.text}
                  </div>
                )}
                {'when' in rule && rule.when && (
                  <div className="md:col-span-2 mt-2 rounded-md bg-gray-50 border-l-2 border-blue-200 px-3 py-2">
                    <div className="font-bold text-gray-800 mb-1">When:</div>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
                      <div>
                        <span className="font-medium">Preference:</span> shift request
                      </div>
                      {rule.when.preference.requestShape && (
                        <div>
                          <span className="font-medium">Request Shape:</span>{' '}
                          {rule.when.preference.requestShape.join(', ')}
                        </div>
                      )}
                      {rule.when.preference.satisfied !== undefined && (
                        <div>
                          <span className="font-medium">Satisfied:</span>{' '}
                          {String(rule.when.preference.satisfied)}
                        </div>
                      )}
                      {rule.when.preference.weightRange && (
                        <div>
                          <span className="font-medium">Weight Range (inclusive):</span>{' '}
                          {rule.when.preference.weightRange.join(' to ')}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        />

        <DraggableCardList
          title="Extra Columns"
          items={extraColumns}
          emptyMessage='No extra columns defined yet. Click "Add Export Rule" to get started.'
          onEdit={handleStartEditExtraColumn}
          onDuplicate={handleDuplicateExtraColumn}
          onDelete={deleteExtraColumn}
          onReorder={handleReorderExtraColumns}
          renderContent={(rule) => (
            <>
              {rule.description && (
                <h4 className="font-medium text-gray-900 mb-3">{rule.description}</h4>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-sm text-gray-600">
                <div>
                  <span className="font-medium">Header:</span> {rule.header}
                </div>
                <div>
                  <span className="font-medium">Type:</span> {rule.type}
                </div>
                <div>
                  <span className="font-medium">Count Shift Types:</span> {rule.countShiftTypes.join(', ')}
                </div>
                {rule.countShiftTypeCoefficients && (
                  <div>
                    <span className="font-medium">Coefficients:</span>{' '}
                    {rule.countShiftTypeCoefficients.map(([id, coefficient]) => `[${id}, ${coefficient}]`).join(', ')}
                  </div>
                )}
                <div>
                  <span className="font-medium">Count Dates:</span> {rule.countDates.join(', ')}
                </div>
                {rule.rightBorderColor && (
                  <div>
                    <span className="font-medium">Right Border:</span> {rule.rightBorderColor}
                  </div>
                )}
              </div>
            </>
          )}
        />

        <DraggableCardList
          title="Extra Rows"
          items={extraRows}
          emptyMessage='No extra rows defined yet. Click "Add Export Rule" to get started.'
          onEdit={handleStartEditExtraRow}
          onDuplicate={handleDuplicateExtraRow}
          onDelete={deleteExtraRow}
          onReorder={handleReorderExtraRows}
          renderContent={(rule) => (
            <>
              {rule.description && (
                <h4 className="font-medium text-gray-900 mb-3">{rule.description}</h4>
              )}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-sm text-gray-600">
                <div>
                  <span className="font-medium">Header:</span> {rule.header}
                </div>
                <div>
                  <span className="font-medium">Type:</span> {rule.type}
                </div>
                <div>
                  <span className="font-medium">Count Shift Types:</span> {rule.countShiftTypes.join(', ')}
                </div>
                <div>
                  <span className="font-medium">Count People:</span> {rule.countPeople.join(', ')}
                </div>
                {rule.bottomBorderColor && (
                  <div>
                    <span className="font-medium">Bottom Border:</span> {rule.bottomBorderColor}
                  </div>
                )}
              </div>
            </>
          )}
        />
      </div>
    </div>
  );
}
