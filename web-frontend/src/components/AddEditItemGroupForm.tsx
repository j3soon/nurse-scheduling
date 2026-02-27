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

// A form component for adding and editing a single item or group and managing its relationships.
'use client';

import { FormInput } from '@/components/FormInput';
import { CheckboxList } from '@/components/CheckboxList';
import { Item, Group } from '@/types/scheduling';
import { Mode } from '@/constants/modes';
import { FiAlertCircle } from 'react-icons/fi';

interface AddEditItemGroupFormProps<T extends Item, G extends Group> {
  mode: Mode.ADDING | Mode.EDITING;
  draft: {
    id: string;
    description: string;
    groups: string[];
    members: string[];
    backgroundColor: string;
    isItem: boolean;
  };
  items: T[];
  groups: G[];
  itemLabel: string;
  error: string;
  filterItemGroups: (items: T[] | G[]) => T[] | G[];
  onIdChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDescriptionChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onMemberToggle: (id: string) => void;
  onBackgroundColorChange?: (color: string) => void;
  onBackgroundColorReset?: () => void;
  showExportStyleEditor?: boolean;
  onSave: () => void;
  onCancel: () => void;
}

export function AddEditItemGroupForm<T extends Item, G extends Group>({
  mode,
  draft,
  items,
  groups,
  itemLabel,
  error,
  filterItemGroups,
  onIdChange,
  onDescriptionChange,
  onMemberToggle,
  onBackgroundColorChange,
  onBackgroundColorReset,
  showExportStyleEditor = false,
  onSave,
  onCancel,
}: AddEditItemGroupFormProps<T, G>) {
  const isItem = draft.isItem;
  const title = `${mode === Mode.ADDING ? 'Add New' : 'Edit'} ${isItem ? itemLabel : "Group"}`;
  const placeholder = `Enter ${isItem ? itemLabel.toLowerCase() : "group"} ID`;
  const isValidHexColor = /^#[0-9a-fA-F]{6}$/.test(draft.backgroundColor);
  const hasColorInput = draft.backgroundColor.length > 0;
  const pickerValue = isValidHexColor ? draft.backgroundColor : '#ffffff';
  const pickerText = hasColorInput
    ? (isValidHexColor ? draft.backgroundColor : '(Invalid)')
    : 'Default';
  const pickerTextColor = (() => {
    if (hasColorInput && !isValidHexColor) return '#b91c1c';
    if (!isValidHexColor) return '#4b5563';
    const hex = draft.backgroundColor.slice(1);
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.6 ? '#111827' : '#f9fafb';
  })();
  const isColorError = showExportStyleEditor && error.toLowerCase().includes('background color');
  const formError = isColorError ? '' : error;

  return (
    <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
      <div className="px-6 py-4">
        <h2 className="text-lg font-semibold mb-4 text-gray-800">{title}</h2>
        <FormInput
          itemValue={draft.id}
          itemPlaceholder={placeholder}
          onItemChange={onIdChange}
          descriptionValue={draft.description}
          descriptionPlaceholder={`Enter ${isItem ? itemLabel.toLowerCase() : "group"} description (optional)`}
          onDescriptionChange={onDescriptionChange}
          error={formError}
          onAction={onSave}
          onCancel={onCancel}
          actionText={mode === Mode.ADDING ? 'Add' : 'Update'}
        >
          <CheckboxList
            items={draft.isItem ? filterItemGroups(groups) as G[] : filterItemGroups(items) as T[]}
            selectedIds={draft.isItem ? draft.groups : draft.members}
            onToggle={onMemberToggle}
            label={draft.isItem ? "Groups" : 'Members'}
          />
          {showExportStyleEditor && (
            <div className="space-y-2 border-t border-gray-200 pt-4">
              <h3 className="text-sm font-semibold text-gray-800">Export Styles</h3>
              <label className="block text-sm font-medium text-gray-700">Export Background Color</label>
              <div className="flex items-center gap-3">
                <div className="relative h-9 w-28">
                  <input
                    type="color"
                    value={pickerValue}
                    onChange={(e) => onBackgroundColorChange?.(e.target.value)}
                    className="h-9 w-28 rounded border border-gray-300 bg-white cursor-pointer"
                    title="Choose background color"
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
                  value={draft.backgroundColor}
                  onChange={(e) => onBackgroundColorChange?.(e.target.value)}
                  placeholder="#RRGGBB"
                  className="w-28 px-2 py-1.5 text-sm border border-gray-300 rounded-md font-mono"
                  title="Enter export background color in hex"
                />
                <button
                  type="button"
                  onClick={onBackgroundColorReset}
                  className="px-3 py-1 text-sm text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
                >
                  Reset
                </button>
              </div>
              {isColorError && (
                <p className="text-sm text-red-600 flex items-center gap-1">
                  <FiAlertCircle className="h-4 w-4" />
                  {error}
                </p>
              )}
            </div>
          )}
        </FormInput>
      </div>
    </div>
  );
}
