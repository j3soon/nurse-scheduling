// A component for managing a list of items and groups, and the relationships between them.
'use client';

import React, { useState } from 'react';
import { FiHelpCircle } from 'react-icons/fi';
import { DataTable } from '@/components/DataTable';
import { AddEditItemGroupForm } from '@/components/AddEditItemGroupForm';
import ToggleButton from '@/components/ToggleButton';
import { useItemTableColumns, useGroupTableColumns } from '@/components/TableColumns';
import { isReservedKeyword } from '@/utils/keywords';
import { ERROR_SHOULD_NOT_HAPPEN } from '@/constants/errors';
import { Mode } from '@/constants/modes';
import { Item, Group, DataType } from '@/types/scheduling';

const getLabels = (dataType: DataType) => {
  switch (dataType) {
    case DataType.DATES:
      return { itemLabel: 'Date', itemLabelPlural: 'Dates' };
    case DataType.PEOPLE:
      return { itemLabel: 'Person', itemLabelPlural: 'People' };
    case DataType.SHIFT_TYPES:
      return { itemLabel: 'Shift Type', itemLabelPlural: 'Shift Types' };
    default:
      return { itemLabel: 'Item', itemLabelPlural: 'Items' };
  }
};

export interface ItemGroupEditorPageData {
  items: Item[];
  groups: Group[];
  history?: string[];
}

interface ItemGroupEditorPageProps {
  title: string | React.ReactNode;
  instructions: string[];
  data: ItemGroupEditorPageData;
  dataType: DataType;
  mode: Mode;
  setMode: (mode: Mode) => void;
  itemsReadOnly?: boolean;
  groupsReadOnly?: boolean;
  children?: React.ReactNode;
  extraButtons?: React.ReactNode;
  addItem: (dataType: DataType, data: ItemGroupEditorPageData, id: string, groupIds: string[], description?: string) => void;
  addGroup: (dataType: DataType, data: ItemGroupEditorPageData, id: string, memberIds: string[], description?: string) => void;
  updateItem: (dataType: DataType, data: ItemGroupEditorPageData, oldId: string, newId: string, groupIds?: string[], description?: string) => void;
  updateGroup: (dataType: DataType, data: ItemGroupEditorPageData, oldId: string, newId: string, members?: string[], description?: string) => void;
  deleteItem: (dataType: DataType, data: ItemGroupEditorPageData, id: string) => void;
  deleteGroup: (dataType: DataType, data: ItemGroupEditorPageData, id: string) => void;
  removeItemFromGroup: (dataType: DataType, data: ItemGroupEditorPageData, itemId: string, groupId: string) => void;
  reorderItems: (dataType: DataType, data: ItemGroupEditorPageData, reorderedItems: Item[]) => void;
  reorderGroups: (dataType: DataType, data: ItemGroupEditorPageData, newGroups: Group[]) => void;
  filterItemGroups: (items: Item[] | Group[]) => Item[] | Group[];
}

export default function ItemGroupEditorPage({
  title,
  instructions,
  data,
  dataType,
  mode,
  setMode,
  itemsReadOnly = false,
  groupsReadOnly = false,
  children,
  extraButtons,
  addItem,
  addGroup,
  updateItem,
  updateGroup,
  deleteItem,
  deleteGroup,
  removeItemFromGroup,
  reorderItems,
  reorderGroups,
  filterItemGroups,
}: ItemGroupEditorPageProps) {

  const { itemLabel, itemLabelPlural } = getLabels(dataType);

  const [draft, setDraft] = useState<{
    id: string;
    description: string;
    groups: string[];
    members: string[];
    editingId?: string;
    isItem: boolean;  // Whether the draft is for an item or a group
  }>({
    id: '',
    description: '',
    groups: [],
    members: [],
    isItem: true,
  });
  const [error, setError] = useState<string>('');
  const [inlineEditingId, setInlineEditingId] = useState<string>('');
  // The field being edited in inline editing mode
  const [inlineEditingField, setInlineEditingField] = useState<'id' | 'description'>('id');
  // Help functionality from PageTitleHelp
  const [showInstructions, setShowInstructions] = useState(false);

  const { items, groups } = data;

  const isDuplicateId = (id: string, currentId?: string) => {
    return items.some(item => item.id === id && item.id !== currentId) ||
           groups.some(group => group.id === id && group.id !== currentId);
  };

  const handleSave = () => {
    const trimmedId = draft.id.trim();
    const trimmedDescription = draft.description.trim();
    if (!trimmedId) {
      setError(`${draft.isItem ? itemLabel : "Group"} ID cannot be empty`);
      return;
    }

    if (isReservedKeyword(dataType, trimmedId)) {
      setError(`"${trimmedId}" is a reserved keyword and cannot be used as an ID`);
      return;
    }

    if (isDuplicateId(trimmedId, draft.editingId)) {
      setError(`This ID is already used by another ${itemLabel.toLowerCase()} or group`);
      return;
    }

    if (draft.isItem) {
      if (draft.editingId) {
        updateItem(dataType, data, draft.editingId, trimmedId, draft.groups, trimmedDescription);
      } else {
        addItem(dataType, data, trimmedId, draft.groups, trimmedDescription);
      }
    } else {
      if (draft.editingId) {
        updateGroup(dataType, data, draft.editingId, trimmedId, draft.members, trimmedDescription);
      } else {
        addGroup(dataType, data, trimmedId, draft.members, trimmedDescription);
      }
    }

    setDraft({ id: '', description: '', groups: [], members: [], isItem: true });
    setMode(Mode.NORMAL);
    setError('');
  };

  const handleStartEditing = (id: string) => {
    const isItem = items.some(i => i.id === id);
    setMode(Mode.EDITING);

    if (isItem) {
      if (itemsReadOnly) {
        console.error(`Cannot edit ${itemLabel.toLowerCase()} ${id} - items are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
      const item = items.find(i => i.id === id);
      if (item && item.isAutoGenerated) {
        console.error(`Cannot edit auto-generated ${itemLabel.toLowerCase()} ${id}. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
      if (item) {
        const itemGroups = groups
          .filter(g => g.members.includes(item.id))
          .map(g => g.id);
        setDraft({ id: item.id, description: item.description, groups: itemGroups, members: [], editingId: id, isItem: true });
      } else {
        console.error(`${itemLabel} with ID ${id} not found during edit. ${ERROR_SHOULD_NOT_HAPPEN}`);
      }
    } else {
      if (groupsReadOnly) {
        console.error(`Cannot edit group ${id} - groups are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
      const targetGroup = groups.find(g => g.id === id);
      if (targetGroup && targetGroup.isAutoGenerated) {
        console.error(`Cannot edit auto-generated group ${id}. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
      const group = groups.find(g => g.id === id);
      if (group) {
        setDraft({ id: group.id, description: group.description, groups: [], members: group.members, editingId: id, isItem: false });
      } else {
        console.error(`Group with ID ${id} not found during edit. ${ERROR_SHOULD_NOT_HAPPEN}`);
      }
    }
    setError('');
    // Scroll to top of the page
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  const handleDelete = (id: string) => {
    const isItem = items.some(i => i.id === id);
    if (isItem) {
      if (itemsReadOnly) {
        console.error(`Cannot delete ${itemLabel.toLowerCase()} ${id} - items are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
      const item = items.find(i => i.id === id);
      if (item && item.isAutoGenerated) {
        console.error(`Cannot delete auto-generated ${itemLabel.toLowerCase()} ${id}. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
      deleteItem(dataType, data, id);
    } else {
      if (groupsReadOnly) {
        console.error(`Cannot delete group ${id} - groups are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
      const targetGroup = groups.find(g => g.id === id);
      if (targetGroup && targetGroup.isAutoGenerated) {
        console.error(`Cannot delete auto-generated group ${id}. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
      deleteGroup(dataType, data, id);
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

  const handleStartInlineEditing = (id: string, isItem: boolean, field: 'id' | 'description' = 'id') => {
    if (isItem && itemsReadOnly) {
      console.error(`Cannot edit ${itemLabel.toLowerCase()} ${id} - items are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }
    if (!isItem && groupsReadOnly) {
      console.error(`Cannot edit group ${id} - groups are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }
    if (isItem) {
      const targetItem = items.find(i => i.id === id);
      if (targetItem && targetItem.isAutoGenerated) {
        console.error(`Cannot edit auto-generated ${itemLabel.toLowerCase()} ${id}. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
    }
    if (!isItem) {
      const targetGroup = groups.find(g => g.id === id);
      if (targetGroup && targetGroup.isAutoGenerated) {
        console.error(`Cannot edit auto-generated group ${id}. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
    }
    setMode(Mode.INLINE_EDITING);
    setInlineEditingId(id);
    setInlineEditingField(field);
    setError('');
  };

  const handleInlineSave = (id: string, field: 'id' | 'description', isItem: boolean, value: string) => {
    if (isItem && itemsReadOnly) {
      console.error(`${itemLabel} ${field} cannot be edited - items are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }
    if (!isItem && groupsReadOnly) {
      console.error(`Group ${field} cannot be edited - groups are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }

    if (field === 'id') {
      if (!value) {
        setError(`${isItem ? itemLabel : "Group"} ID cannot be empty`);
        return;
      }

      if (isReservedKeyword(dataType, value)) {
        setError(`"${value}" is a reserved keyword and cannot be used as an ID`);
        return;
      }

      if (isDuplicateId(value, id)) {
        setError(`This ID is already used by another ${isItem ? itemLabel.toLowerCase() : "group"}`);
        return;
      }

      if (isItem) {
        updateItem(dataType, data, id, value, undefined, undefined);
      } else {
        updateGroup(dataType, data, id, value, undefined, undefined);
      }
    } else if (field === 'description') {
      if (isItem) {
        updateItem(dataType, data, id, id, undefined, value);
      } else {
        updateGroup(dataType, data, id, id, undefined, value);
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
    if (isItem && itemsReadOnly) {
      console.error(`Cannot add ${itemLabel.toLowerCase()} - items are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }
    if (!isItem && groupsReadOnly) {
      console.error(`Cannot add group - groups are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }

    // Toggle form visibility: if already adding the same type, cancel; otherwise start adding
    if (mode === Mode.ADDING && draft.isItem === isItem) {
      handleCancel();
    } else {
      setMode(Mode.ADDING);
      setDraft({ id: '', description: '', groups: [], members: [], isItem });
      setError('');
    }
  };

  // Table columns using the separate functions
  const itemColumns = useItemTableColumns({
    mode,
    inlineEditingId,
    inlineEditingField,
    error,
    groups,
    onInlineSave: handleInlineSave,
    onInlineCancel: handleInlineCancel,
    onInlineEdit: handleStartInlineEditing,
    onEdit: handleStartEditing,
    onDelete: handleDelete,
    removeItemFromGroup: (itemId: string, groupId: string) => removeItemFromGroup(dataType, data, itemId, groupId),
    itemsReadOnly,
  });

  const groupColumns = useGroupTableColumns({
    mode,
    inlineEditingId,
    inlineEditingField,
    error,
    items,
    onInlineSave: handleInlineSave,
    onInlineCancel: handleInlineCancel,
    onInlineEdit: handleStartInlineEditing,
    onEdit: handleStartEditing,
    onDelete: handleDelete,
    removeItemFromGroup: (itemId: string, groupId: string) => removeItemFromGroup(dataType, data, itemId, groupId),
    groupsReadOnly,
  });

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-800">{title}</h1>
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
          {extraButtons}
          {!itemsReadOnly && (
            <ToggleButton
              label={`Add ${itemLabel}`}
              isToggled={mode === Mode.ADDING && draft.isItem}
              onToggle={() => handleStartAdding(true)}
            />
          )}
          {!groupsReadOnly && (
            <ToggleButton
              label={`Add Group`}
              isToggled={mode === Mode.ADDING && !draft.isItem}
              onToggle={() => handleStartAdding(false)}
            />
          )}
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

      {children}

      {(mode === Mode.ADDING || mode === Mode.EDITING) && (
        <AddEditItemGroupForm
          mode={mode}
          draft={draft}
          items={items}
          groups={groups}
          itemLabel={itemLabel}
          error={error}
          filterItemGroups={filterItemGroups}
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
          onReorder={mode === Mode.INLINE_EDITING || itemsReadOnly ? undefined : (items: Item[]) => reorderItems(dataType, data, items)}
          getRowClassName={(item) => item.isAutoGenerated ? 'bg-blue-50 border-blue-200 non-draggable' : ''}
        />

        <DataTable
          title={itemLabelPlural + ' Groups'}
          columns={groupColumns}
          data={groups}
          onReorder={mode === Mode.INLINE_EDITING || groupsReadOnly ? undefined : (groups: Group[]) => reorderGroups(dataType, data, groups)}
          getRowClassName={(group) => group.isAutoGenerated ? 'bg-blue-50 border-blue-200 non-draggable' : ''}
        />
      </div>
    </div>
  );
}
