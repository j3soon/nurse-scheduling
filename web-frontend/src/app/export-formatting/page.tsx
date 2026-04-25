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

// The export formatting page for Tab "10. Export Formatting"
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { FiAlertCircle, FiHelpCircle } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { ExportFormatting, ExportFormattingType } from '@/types/scheduling';
import { CheckboxList } from '@/components/CheckboxList';
import ToggleButton from '@/components/ToggleButton';
import { DraggableCardList } from '@/components/DraggableCardList';
import { saveScrollPosition, restoreScrollPosition } from '@/utils/scrolling';
import { ALL } from '@/utils/keywords';

interface DraftRule {
  type: ExportFormattingType;
  targetIds: string[];
  backgroundColor: string;
  bottomBorderColor: string;
  rightBorderColor: string;
}

const HEX_COLOR_PATTERN = /^#[0-9a-fA-F]{6}$/;
type ColorField = 'backgroundColor' | 'bottomBorderColor' | 'rightBorderColor';

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
  const { exportData, updateExportFormatting, peopleData, dateData, shiftTypeData } = useSchedulingData();
  const [showInstructions, setShowInstructions] = useState(false);
  const [isFormVisible, setIsFormVisible] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState<DraftRule>({
    type: 'cell',
    targetIds: [],
    backgroundColor: '',
    bottomBorderColor: '',
    rightBorderColor: '',
  });

  const formattingRules = exportData.formatting || [];
  const getTargetConfig = () => {
    if (draft.type === 'row' || draft.type === 'row header') {
      return {
        emptyText: 'No people available. Please set up people in the',
        href: '/people',
        hrefLabel: 'People',
        options: [
          ...peopleData.items.map(person => ({ id: person.id, description: person.description })),
          ...peopleData.groups.map(group => ({ id: group.id, description: group.description })),
        ]
      };
    }

    if (draft.type === 'column' || draft.type === 'column header') {
      return {
        emptyText: 'No dates available. Please set up dates in the',
        href: '/dates',
        hrefLabel: 'Dates',
        options: [
          ...dateData.items.map(date => ({ id: date.id, description: date.description })),
          ...dateData.groups.map(group => ({ id: group.id, description: group.description })),
        ]
      };
    }

    if (draft.type === 'history column') {
      return {
        emptyText: 'History columns are available when people have history entries. Add history in the',
        href: '/shift-requests',
        hrefLabel: 'Shift Requests',
        options: [
          { id: ALL, description: 'All history columns' },
        ]
      };
    }

    return {
      emptyText: 'No shift types available. Please set up shift types in the',
      href: '/shift-types',
      hrefLabel: 'Shift Types',
      options: [
        ...shiftTypeData.items.map(shiftType => ({ id: shiftType.id, description: shiftType.description })),
        ...shiftTypeData.groups.map(group => ({ id: group.id, description: group.description })),
      ]
    };
  };

  const targetConfig = getTargetConfig();
  const targetOptions = targetConfig.options;

  const instructions = [
    'Define global export formatting rules applied during export',
    'Select one or more targets based on rule type: rows=people, columns=dates, cells=shift types, history columns=histories',
    'Use #RRGGBB for color values',
    'Rules are evaluated in order',
    'Drag and drop cards to reorder rule priority',
    'Navigate using the tabs or keyboard shortcuts (1, 2, etc.) to continue setup'
  ];

  const validateColor = (value: string, fieldLabel: string): string | null => {
    if (!value) return null;
    if (!HEX_COLOR_PATTERN.test(value)) {
      return `${fieldLabel} must be a valid hex color in #RRGGBB format`;
    }
    return null;
  };

  const resetForm = () => {
    setDraft({
      type: 'cell',
      targetIds: [],
      backgroundColor: '',
      bottomBorderColor: '',
      rightBorderColor: '',
    });
    setError('');
    setEditingIndex(null);
  };

  const handleStartAdd = () => {
    resetForm();
    setIsFormVisible(true);
  };

  const handleStartEdit = (index: number) => {
    const rule = formattingRules[index];
    setDraft({
      type: rule.type,
      targetIds: rule.targets,
      backgroundColor: rule.backgroundColor || '',
      bottomBorderColor: rule.bottomBorderColor || '',
      rightBorderColor: rule.rightBorderColor || '',
    });
    setEditingIndex(index);
    setIsFormVisible(true);
    setError('');
    saveScrollPosition();
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  const handleCancel = () => {
    const wasEditing = editingIndex !== null;
    setIsFormVisible(false);
    resetForm();
    if (wasEditing) {
      restoreScrollPosition();
    }
  };

  const handleSave = () => {
    const backgroundColor = draft.backgroundColor.trim().toLowerCase();
    const bottomBorderColor = draft.bottomBorderColor.trim().toLowerCase();
    const rightBorderColor = draft.rightBorderColor.trim().toLowerCase();

    if (draft.targetIds.length === 0) {
      setError('Select at least one target');
      return;
    }

    const validTargetIds = new Set(targetOptions.map(option => option.id));
    if (draft.targetIds.some(id => !validTargetIds.has(id))) {
      setError('Selected targets are invalid for this rule type');
      return;
    }

    const backgroundColorError = validateColor(backgroundColor, 'Background Color');
    if (backgroundColorError) {
      setError(backgroundColorError);
      return;
    }
    const bottomBorderColorError = validateColor(bottomBorderColor, 'Bottom Border Color');
    if (bottomBorderColorError) {
      setError(bottomBorderColorError);
      return;
    }
    const rightBorderColorError = validateColor(rightBorderColor, 'Right Border Color');
    if (rightBorderColorError) {
      setError(rightBorderColorError);
      return;
    }
    if (!backgroundColor && !bottomBorderColor && !rightBorderColor) {
      setError('At least one style field is required');
      return;
    }

    const newRule: ExportFormatting = {
      type: draft.type,
      targets: draft.targetIds
    };
    if (backgroundColor) newRule.backgroundColor = backgroundColor;
    if (bottomBorderColor) newRule.bottomBorderColor = bottomBorderColor;
    if (rightBorderColor) newRule.rightBorderColor = rightBorderColor;

    const wasEditing = editingIndex !== null;
    if (wasEditing) {
      const next = [...formattingRules];
      next[editingIndex] = newRule;
      updateExportFormatting(next);
    } else {
      updateExportFormatting([...formattingRules, newRule]);
    }

    setIsFormVisible(false);
    resetForm();
    if (wasEditing) {
      restoreScrollPosition();
    }
  };

  useEffect(() => {
    if (!isFormVisible) return;

    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
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

  const handleDeleteRule = (index: number) => {
    const next = formattingRules.filter((_, i) => i !== index);
    updateExportFormatting(next);
  };

  const renderColorField = (field: ColorField, label: string) => {
    const value = draft[field];
    const { pickerValue, pickerText, pickerTextColor } = getPickerDisplay(value);
    return (
      <div className="space-y-1">
        <label className="block text-sm font-medium text-gray-700">{label}</label>
        <div className="flex items-center gap-3">
          <div className="relative h-9 w-28">
            <input
              type="color"
              value={pickerValue}
              onChange={(e) => setDraft(prev => ({ ...prev, [field]: e.target.value }))}
              className="h-9 w-28 rounded border border-gray-300 bg-white cursor-pointer"
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
            onChange={(e) => setDraft(prev => ({ ...prev, [field]: e.target.value }))}
            placeholder="#RRGGBB"
            className="w-28 px-2 py-1.5 text-sm border border-gray-300 rounded-md font-mono"
            title={`Enter ${label.toLowerCase()} in hex`}
          />
        </div>
      </div>
    );
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-800">Export Formatting</h1>
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
            label="Add Formatting Rule"
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

      {isFormVisible && (
        <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
          <div className="px-6 py-4">
            <h2 className="text-lg font-semibold mb-4 text-gray-800">
              {editingIndex !== null ? 'Edit Formatting Rule' : 'Add New Formatting Rule'}
            </h2>
            <div className="space-y-6">
              <div className="flex flex-wrap items-start gap-4">
                <div className="min-w-[180px]">
                  <label className="block text-sm font-medium text-gray-700 mb-2">Type</label>
                  <select
                    value={draft.type}
                    onChange={(e) => setDraft(prev => ({
                      ...prev,
                      type: e.target.value as ExportFormattingType,
                      targetIds: []
                    }))}
                    className="px-3 py-2 border border-gray-300 rounded-md w-full"
                  >
                    <option value="row header">row header</option>
                    <option value="row">row</option>
                    <option value="column header">column header</option>
                    <option value="column">column</option>
                    <option value="history column">history column</option>
                    <option value="cell">cell</option>
                  </select>
                  <p className="mt-1 text-xs text-gray-500">
                    {draft.type === 'row' || draft.type === 'row header'
                      ? 'This type targets people.'
                      : draft.type === 'column' || draft.type === 'column header'
                        ? 'This type targets dates.'
                        : draft.type === 'history column'
                          ? 'This type targets people histories.'
                          : 'This type targets shift types.'}
                  </p>
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
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Targets *
                </label>
                {targetOptions.length === 0 ? (
                  <div className="text-sm text-gray-500 italic p-4 text-center border border-gray-200 rounded-lg bg-gray-50">
                    {targetConfig.emptyText}{' '}
                    <Link href={targetConfig.href} className="text-blue-600 hover:text-blue-800 underline">
                      {targetConfig.hrefLabel}
                    </Link>{' '}
                    tab first.
                  </div>
                ) : (
                  <CheckboxList
                    items={targetOptions}
                    selectedIds={draft.targetIds}
                    onToggle={(id) => {
                      setDraft(prev => ({
                        ...prev,
                        targetIds: prev.targetIds.includes(id)
                          ? prev.targetIds.filter(targetId => targetId !== id)
                          : [...prev.targetIds, id]
                      }));
                    }}
                    label=""
                  />
                )}
              </div>

              {error && (
                <p className="text-sm text-red-600 flex items-center gap-1">
                  <FiAlertCircle className="h-4 w-4" />
                  {error}
                </p>
              )}

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

      <DraggableCardList
        title="Formatting Rules"
        items={formattingRules}
        emptyMessage='No formatting rules defined yet. Click "Add Formatting Rule" to get started.'
        onEdit={handleStartEdit}
        onDelete={handleDeleteRule}
        onReorder={(newItems) => updateExportFormatting(newItems)}
        renderContent={(rule) => (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-sm text-gray-600">
            <div>
              <span className="font-medium">Type:</span> {rule.type}
            </div>
            <div>
              <span className="font-medium">Targets:</span> {rule.targets.join(', ')}
            </div>
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
          </div>
        )}
      />
    </div>
  );
}
