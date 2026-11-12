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

import { useI18n } from '@/i18n/I18nProvider';
import { useState } from 'react';
import { FormInput } from '@/components/FormInput';
import { CheckboxList } from '@/components/CheckboxList';
import { Item, Group } from '@/types/scheduling';
import { Mode } from '@/constants/modes';

type SelectionOperation = 'replace' | 'add' | 'remove';

interface AddEditItemGroupFormProps<T extends Item, G extends Group> {
  mode: Mode.ADDING | Mode.EDITING;
  draft: {
    id: string;
    description: string;
    groups: string[];
    members: string[];
    isItem: boolean;
    editingId?: string;
  };
  items: T[];
  groups: G[];
  itemLabel: string;
  itemLabelPlural: string;
  error: string;
  filterItemGroups: (items: T[] | G[]) => T[] | G[];
  renderGroupMemberSelector?: (props: {
    items: T[];
    selectedIds: string[];
    onToggle: (id: string) => void;
  }) => React.ReactNode;
  onIdChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDescriptionChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onMemberToggle: (id: string) => void;
  onApplySelection: (ids: string[]) => void;
  onSave: () => void;
  onCancel: () => void;
}

export function AddEditItemGroupForm<T extends Item, G extends Group>({
  mode,
  draft,
  items,
  groups,
  itemLabel,
  itemLabelPlural,
  error,
  filterItemGroups,
  renderGroupMemberSelector,
  onIdChange,
  onDescriptionChange,
  onMemberToggle,
  onApplySelection,
  onSave,
  onCancel,
}: AddEditItemGroupFormProps<T, G>) {
  const { t } = useI18n();
  const [sourceId, setSourceId] = useState('');
  const [operation, setOperation] = useState<SelectionOperation>('replace');
  // The form opens only after a click, so reading the screen width here cannot mismatch server markup.
  // Phones start with the panel collapsed because it is taller than the fields being edited.
  const [applyFromOpen, setApplyFromOpen] = useState(() => (
    typeof window === 'undefined' || !window.matchMedia?.('(max-width: 639px)').matches
  ));
  const isItem = draft.isItem;
  const title = mode === Mode.ADDING ? t("Add New {label}", { label: isItem ? itemLabel : t("Group") }) : t("Edit {label}", { label: isItem ? itemLabel : t("Group") });
  const placeholder = t("Enter {value0} ID", { value0: isItem ? itemLabel.toLowerCase() : t("group") });
  const filteredItems = filterItemGroups(items) as T[];
  const filteredGroups = filterItemGroups(groups) as G[];
  const sources = (isItem ? filteredItems : filteredGroups)
    .filter(entry => entry.id !== draft.editingId);
  const selectedIds = isItem ? draft.groups : draft.members;
  const availableIds = new Set((isItem ? filteredGroups : filteredItems).map(entry => entry.id));
  const validSourceId = sources.some(entry => entry.id === sourceId) ? sourceId : '';
  const sourceIds = !validSourceId ? [] : isItem
    ? filteredGroups.filter(group => group.members.includes(validSourceId)).map(group => group.id)
    : [...new Set(filteredGroups.find(group => group.id === validSourceId)?.members ?? [])]
      .filter(id => availableIds.has(id));
  const sourceIdSet = new Set(sourceIds);
  const appliedIds = operation === 'replace'
    ? sourceIds
    : operation === 'add'
      ? [...new Set([...selectedIds, ...sourceIds])]
      : selectedIds.filter(id => !sourceIdSet.has(id));
  const visibleSelectedCount = selectedIds.filter(id => availableIds.has(id)).length;
  const visibleAppliedCount = appliedIds.filter(id => availableIds.has(id)).length;
  const sourceLabel = isItem ? itemLabel.toLowerCase() : t('group');
  const applyFrom = sources.length > 0 && (
    <details open={applyFromOpen} onToggle={event => setApplyFromOpen(event.currentTarget.open)} data-membership-apply className="rounded-lg border border-gray-200 bg-gray-50 p-3">
      <summary className="cursor-pointer text-sm font-medium text-blue-700">
        {t("Apply selection from another ")}{sourceLabel}
      </summary>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="flex min-w-40 flex-1 flex-col gap-1 text-sm text-gray-700">
          {t("Source ")}{sourceLabel}
          <select
            value={validSourceId}
            onChange={event => setSourceId(event.target.value)}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
          >
            <option value="">{t("Choose ")}{sourceLabel}</option>
            {sources.map(source => <option key={source.id} value={source.id}>{source.id}</option>)}
          </select>
        </label>
        <label className="flex min-w-36 flex-col gap-1 text-sm text-gray-700">
          {t("Operation")}<select
            value={operation}
            onChange={event => setOperation(event.target.value as SelectionOperation)}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
          >
            <option value="replace">{t("Replace")}</option>
            <option value="add">{t("Add missing")}</option>
            <option value="remove">{t("Remove matching")}</option>
          </select>
        </label>
        <button
          type="button"
          disabled={!validSourceId}
          onClick={() => onApplySelection(appliedIds)}
          className="rounded-md border border-blue-600 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {t("Apply to draft")}</button>
      </div>
      {validSourceId && (
        <p className="mt-2 text-xs text-gray-600">
          {visibleSelectedCount}{t(" selected → ")}{visibleAppliedCount}{t(" after applying. Save to keep the change.")}</p>
      )}
    </details>
  );
  const memberSelector = filteredItems.length === 0 ? (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-gray-700">{t("Members")}</h3>
      <div className="text-sm text-gray-500 italic p-4 text-center border border-gray-200 rounded-lg bg-gray-50">
        {t("No ")}{itemLabelPlural.toLowerCase()}{t(" available. Please set up ")}{itemLabelPlural.toLowerCase()}{t(" first.")}</div>
    </div>
  ) : renderGroupMemberSelector ? renderGroupMemberSelector({
    items: filteredItems,
    selectedIds: draft.members,
    onToggle: onMemberToggle,
  }) : (
    <CheckboxList
      items={filteredItems}
      selectedIds={draft.members}
      onToggle={onMemberToggle}
      label={t("Members")}
    />
  );
  const groupSelector = filteredGroups.length === 0 ? (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-gray-700">{t("Groups")}</h3>
      <div className="text-sm text-gray-500 italic p-4 text-center border border-gray-200 rounded-lg bg-gray-50">
        {t("No groups available.")}</div>
    </div>
  ) : (
    <CheckboxList
      items={filteredGroups}
      selectedIds={draft.groups}
      onToggle={onMemberToggle}
      label={t("Groups")}
    />
  );

  return (
    <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
      <div className="px-6 py-4">
        <h2 className="text-lg font-semibold mb-4 text-gray-800">{title}</h2>
        <FormInput
          itemValue={draft.id}
          itemPlaceholder={placeholder}
          onItemChange={onIdChange}
          descriptionValue={draft.description}
          descriptionPlaceholder={t("Enter {value0} description (optional)", { value0: isItem ? itemLabel.toLowerCase() : t("group") })}
          onDescriptionChange={onDescriptionChange}
          error={error}
          onAction={onSave}
          onCancel={onCancel}
          actionText={mode === Mode.ADDING ? t("Add") : t("Update")}
        >
          {!draft.isItem ? memberSelector : groupSelector}
          {applyFrom}
        </FormInput>
      </div>
    </div>
  );
}
