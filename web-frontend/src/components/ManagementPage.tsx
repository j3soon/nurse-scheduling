'use client';

import { useState } from 'react';
import { FiPlus } from 'react-icons/fi';
import { DataTable } from '@/components/DataTable';
import { AddEditForm } from '@/components/AddEditForm';
import { useItemTableColumns, useGroupTableColumns } from '@/components/TableColumns';
import { ERROR_SHOULD_NOT_HAPPEN } from '@/constants/errors';
import { Mode } from '@/constants/modes';
import { Item, Group } from '@/types/management';

interface ManagementPageProps<T extends Item, G extends Group> {
  title: string;
  items: T[];
  groups: G[];
  addItem: (id: string, groupIds: string[], description?: string) => void;
  addGroup: (id: string, memberIds: string[], description?: string) => void;
  updateItem: (oldId: string, newId: string, groupIds?: string[], description?: string) => void;
  updateGroup: (oldId: string, newId: string, members?: string[], description?: string) => void;
  deleteItem: (id: string) => void;
  deleteGroup: (id: string) => void;
  removeItemFromGroup: (itemId: string, groupId: string) => void;
  reorderItems: (items: T[]) => void;
  updateGroups: (groups: G[]) => void;
  itemLabel: string;
  itemLabelPlural: string;
  groupLabel: string;
  groupLabelPlural: string;
}

export default function ManagementPage<T extends Item, G extends Group>({
  title,
  items,
  groups,
  addItem,
  addGroup,
  updateItem,
  updateGroup,
  deleteItem,
  deleteGroup,
  removeItemFromGroup,
  reorderItems,
  updateGroups,
  itemLabel,
  itemLabelPlural,
  groupLabel,
  groupLabelPlural,
}: ManagementPageProps<T, G>) {
  const [mode, setMode] = useState<Mode>(Mode.NORMAL);
  const [draft, setDraft] = useState<{
    id: string;
    description: string;
    groups: string[];
    members: string[];
    editingId?: string;
    isItem: boolean;
  }>({
    id: '',
    description: '',
    groups: [],
    members: [],
    isItem: true,
  });
  const [error, setError] = useState<string>('');
  const [inlineEditingId, setInlineEditingId] = useState<string>('');
  const [inlineEditingField, setInlineEditingField] = useState<'id' | 'description'>('id');

  const isDuplicateId = (id: string, currentId?: string) => {
    return items.some(item => item.id === id && item.id !== currentId) ||
           groups.some(group => group.id === id && group.id !== currentId);
  };

  const handleSave = () => {
    const trimmedId = draft.id.trim();
    const trimmedDescription = draft.description.trim();
    if (!trimmedId) {
      setError(`${draft.isItem ? itemLabel : groupLabel} ID cannot be empty`);
      return;
    }

    if (isDuplicateId(trimmedId, draft.editingId)) {
      setError(`This ID is already used by another ${draft.isItem ? itemLabel.toLowerCase() : groupLabel.toLowerCase()}`);
      return;
    }

    if (draft.isItem) {
      if (draft.editingId) {
        updateItem(draft.editingId, trimmedId, draft.groups, trimmedDescription);
      } else {
        addItem(trimmedId, draft.groups, trimmedDescription);
      }
    } else {
      if (draft.editingId) {
        updateGroup(draft.editingId, trimmedId, draft.members, trimmedDescription);
      } else {
        addGroup(trimmedId, draft.members, trimmedDescription);
      }
    }

    setDraft({ id: '', description: '', groups: [], members: [], isItem: true });
    setMode(Mode.NORMAL);
    setError('');
  };

  const handleEdit = (id: string) => {
    const isItem = items.some(i => i.id === id);
    setMode(Mode.EDITING);

    if (isItem) {
      const item = items.find(i => i.id === id);
      if (item) {
        const itemGroups = groups
          .filter(g => g.members.includes(item.id))
          .map(g => g.id);
        setDraft({ id: item.id, description: item.description, groups: itemGroups, members: [], editingId: id, isItem: true });
      } else {
        console.error(`${itemLabel} with ID ${id} not found during edit. ${ERROR_SHOULD_NOT_HAPPEN}`);
      }
    } else {
      const group = groups.find(g => g.id === id);
      if (group) {
        setDraft({ id: group.id, description: group.description, groups: [], members: group.members, editingId: id, isItem: false });
      } else {
        console.error(`${groupLabel} with ID ${id} not found during edit. ${ERROR_SHOULD_NOT_HAPPEN}`);
      }
    }
    setError('');
  };

  const handleDelete = (id: string) => {
    const isItem = items.some(i => i.id === id);
    if (isItem) {
      deleteItem(id);
    } else {
      deleteGroup(id);
    }
  };

  const handleCancel = () => {
    setMode(Mode.NORMAL);
    setDraft({ id: '', description: '', groups: [], members: [], isItem: true });
    setError('');
  };

  const handleDraftIdChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDraft(prev => ({ ...prev, id: e.target.value }));
    setError('');
  };

  const handleDraftDescriptionChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDraft(prev => ({ ...prev, description: e.target.value }));
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSave();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      handleCancel();
    }
  };

  const handleMemberToggle = (id: string) => {
    // Using a state updater function that takes the previous state as an argument is required for handling quick multi-select drag.
    // Since React state updates are asynchronous, directly setting the new state based on the previous state
    // could miss intermediate updates. The updater function ensures we always work with the latest state.
    if (draft.isItem) {
      setDraft(prev => ({
        ...prev,
        groups: prev.groups.includes(id)
          ? prev.groups.filter(groupId => groupId !== id)
          : [...prev.groups, id]
      }));
    } else {
      setDraft(prev => ({
        ...prev,
        members: prev.members.includes(id)
          ? prev.members.filter(memberId => memberId !== id)
          : [...prev.members, id]
      }));
    }
  };

  const handleInlineEdit = (id: string, isItem: boolean, field: 'id' | 'description' = 'id') => {
    setMode(Mode.INLINE_EDITING);
    setInlineEditingId(id);
    setInlineEditingField(field);
    setError('');
  };

  const handleInlineSave = (id: string, field: 'id' | 'description', isItem: boolean, value: string) => {
    if (field === 'id') {
      if (!value) {
        setError(`${isItem ? itemLabel : groupLabel} ID cannot be empty`);
        return;
      }

      if (isDuplicateId(value, id)) {
        setError(`This ID is already used by another ${isItem ? itemLabel.toLowerCase() : groupLabel.toLowerCase()}`);
        return;
      }

      if (isItem) {
        updateItem(id, value);
      } else {
        updateGroup(id, value);
      }
    } else if (field === 'description') {
      if (isItem) {
        updateItem(id, id, undefined, value);
      } else {
        updateGroup(id, id, undefined, value);
      }
    }

    setMode(Mode.NORMAL);
    setInlineEditingId('');
    setError('');
  };

  const handleInlineCancel = () => {
    setMode(Mode.NORMAL);
    setInlineEditingId('');
    setError('');
  };

  const handleStartAdding = (isItem: boolean) => {
    setMode(Mode.ADDING);
    setDraft({ id: '', description: '', groups: [], members: [], isItem });
    setError('');
  };

  // Table columns using the separate functions
  const itemColumns = useItemTableColumns({
    mode,
    inlineEditingId,
    inlineEditingField,
    error,
    groups,
    groupLabel,
    groupLabelPlural,
    onInlineSave: handleInlineSave,
    onInlineCancel: handleInlineCancel,
    onInlineEdit: handleInlineEdit,
    onEdit: handleEdit,
    onDelete: handleDelete,
    removeItemFromGroup,
  });

  const groupColumns = useGroupTableColumns({
    mode,
    inlineEditingId,
    inlineEditingField,
    error,
    items,
    onInlineSave: handleInlineSave,
    onInlineCancel: handleInlineCancel,
    onInlineEdit: handleInlineEdit,
    onEdit: handleEdit,
    onDelete: handleDelete,
    removeItemFromGroup,
  });

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <h1 className="text-3xl font-bold text-gray-800">{title}</h1>
        <div className="flex gap-4">
          <button
            onClick={() => handleStartAdding(true)}
            className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
          >
            <FiPlus className="h-4 w-4" />
            Add {itemLabel}
          </button>
          <button
            onClick={() => handleStartAdding(false)}
            className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
          >
            <FiPlus className="h-4 w-4" />
            Add {groupLabel}
          </button>
        </div>
      </div>

      {(mode === Mode.ADDING || mode === Mode.EDITING) && (
        <AddEditForm
          mode={mode}
          draft={draft}
          items={items}
          groups={groups}
          itemLabel={itemLabel}
          itemLabelPlural={itemLabelPlural}
          groupLabel={groupLabel}
          groupLabelPlural={groupLabelPlural}
          error={error}
          onIdChange={handleDraftIdChange}
          onDescriptionChange={handleDraftDescriptionChange}
          onKeyDown={handleKeyDown}
          onMemberToggle={handleMemberToggle}
          onSave={handleSave}
          onCancel={handleCancel}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <DataTable
          title={itemLabelPlural}
          columns={itemColumns}
          data={items}
          onReorder={mode === Mode.INLINE_EDITING ? undefined : reorderItems}
        />

        <DataTable
          title={itemLabelPlural + ' ' + groupLabelPlural}
          columns={groupColumns}
          data={groups}
          onReorder={mode === Mode.INLINE_EDITING ? undefined : updateGroups}
        />
      </div>
    </div>
  );
}
