// A component for managing a list of items and groups, and the relationships between them.
'use client';

import { useState } from 'react';
import { FiHelpCircle } from 'react-icons/fi';
import { DataTable } from '@/components/DataTable';
import { AddEditItemGroupForm } from '@/components/AddEditItemGroupForm';
import ToggleButton from '@/components/ToggleButton';
import { useItemTableColumns, useGroupTableColumns } from '@/components/TableColumns';
import { ERROR_SHOULD_NOT_HAPPEN } from '@/constants/errors';
import { Mode } from '@/constants/modes';
import { Item, Group } from '@/types/scheduling';

export interface ItemGroupEditorPageData {
  items: Item[];
  groups: Group[];
}

function addItem(
  data: ItemGroupEditorPageData, 
  id: string, 
  groupIds: string[], 
  description?: string
): ItemGroupEditorPageData {
  // Add the item
  const newItem = { id, description: description || '' };
  const newItems = [...data.items, newItem];

  // If groupIds is provided, add the item to those groups
  const updatedGroups = data.groups.map(group => {
    if (!groupIds.includes(group.id)) {
      return group;
    }
    const allMembers = [...group.members, id];
    // Sort members based on updated items order
    const sortedMembers = newItems
      .filter(item => allMembers.includes(item.id))
      .map(item => item.id);
    if (allMembers.length !== sortedMembers.length) {
      console.error(`All members length ${allMembers.length} does not match sorted members length ${sortedMembers.length}. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return group;
    }
    return {
      ...group,
      members: sortedMembers
    };
  });

  return { items: newItems, groups: updatedGroups };
}

function addGroup(
  data: ItemGroupEditorPageData, 
  id: string, 
  memberIds: string[], 
  description?: string
): ItemGroupEditorPageData {
  // Sort members based on items order
  const sortedMembers = data.items
    .filter(item => memberIds.includes(item.id))
    .map(item => item.id);
  
  if (memberIds.length !== sortedMembers.length) {
    console.error(`Member IDs length ${memberIds.length} does not match sorted members length ${sortedMembers.length}. ${ERROR_SHOULD_NOT_HAPPEN}`);
    return data;
  }

  const newGroup = { id, members: sortedMembers, description: description || '' };
  const newGroups = [...data.groups, newGroup];
  
  return { ...data, groups: newGroups };
}

function updateItem(
  data: ItemGroupEditorPageData, 
  oldId: string, 
  newId: string, 
  groupIds?: string[], 
  description?: string
): ItemGroupEditorPageData {
  // First update the item's ID and description
  const updatedItems = data.items.map(item =>
    item.id === oldId
      ? { ...item, id: newId, description: description !== undefined ? description : item.description }
      : item
  );

  // Always update group memberships to reflect the new ID
  const updatedGroups = data.groups.map(group => {
    // Get current members excluding the edited item
    const otherMembers = group.members.filter(id => id !== oldId);

    // Add the item if they should be in this group
    const allMembers = groupIds
      ? (groupIds.includes(group.id) ? [...otherMembers, newId] : otherMembers)
      : (group.members.includes(oldId) ? [...otherMembers, newId] : otherMembers);

    // Sort members based on updated items order
    const sortedMembers = updatedItems
      .filter(item => allMembers.includes(item.id))
      .map(item => item.id);
    
    if (allMembers.length !== sortedMembers.length) {
      console.error(`All members length ${allMembers.length} does not match sorted members length ${sortedMembers.length}. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return group;
    }

    return {
      ...group,
      members: sortedMembers
    };
  });

  return { items: updatedItems, groups: updatedGroups };
}

function updateGroup(
  data: ItemGroupEditorPageData, 
  oldId: string, 
  newId: string, 
  members?: string[], 
  description?: string
): ItemGroupEditorPageData {
  const group = data.groups.find(g => g.id === oldId);
  if (!group) {
    console.error(`Group with ID ${oldId} not found. ${ERROR_SHOULD_NOT_HAPPEN}`);
    return data;
  }

  // Sort members based on items order
  const sortedMembers = members
    ? data.items
        .filter(item => members.includes(item.id))
        .map(item => item.id)
    : group.members;
  
  if (members && members.length !== sortedMembers.length) {
    console.error(`Members length ${members.length} does not match sorted members length ${sortedMembers.length}. ${ERROR_SHOULD_NOT_HAPPEN}`);
    return data;
  }

  const newGroups = data.groups.map(g =>
    g.id === oldId
      ? { ...g, id: newId, members: sortedMembers, description: description !== undefined ? description : g.description }
      : g
  );

  return { ...data, groups: newGroups };
}

function deleteItem(data: ItemGroupEditorPageData, id: string): ItemGroupEditorPageData {
  const newItems = data.items.filter(item => item.id !== id);
  const newGroups = data.groups.map(group => ({
    ...group,
    members: group.members.filter(memberId => memberId !== id)
  }));

  return { items: newItems, groups: newGroups };
}

function deleteGroup(data: ItemGroupEditorPageData, id: string): ItemGroupEditorPageData {
  const newGroups = data.groups.filter(g => g.id !== id);
  return { ...data, groups: newGroups };
}

function removeItemFromGroup(data: ItemGroupEditorPageData, itemId: string, groupId: string): ItemGroupEditorPageData {
  const newGroups = data.groups.map(group =>
    group.id === groupId
      ? { ...group, members: group.members.filter(id => id !== itemId) }
      : group
  );

  return { ...data, groups: newGroups };
}

function reorderItems(data: ItemGroupEditorPageData, reorderedItems: Item[]): ItemGroupEditorPageData {
  // Sort group members based on items order
  const updatedGroups = data.groups.map(group => ({
    ...group,
    members: reorderedItems
      .filter(item => group.members.includes(item.id))
      .map(item => item.id)
  }));

  return { items: reorderedItems, groups: updatedGroups };
}

function updateItems(data: ItemGroupEditorPageData, newItems: Item[]): ItemGroupEditorPageData {
  return { ...data, items: newItems };
}

function updateGroups(data: ItemGroupEditorPageData, newGroups: Group[]): ItemGroupEditorPageData {
  return { ...data, groups: newGroups };
}

interface ItemGroupEditorPageProps<T extends Item, G extends Group> {
  title: string | React.ReactNode;
  instructions: string[];
  data: ItemGroupEditorPageData;
  updateData: (newData: ItemGroupEditorPageData) => void;
  itemLabel: string;
  itemLabelPlural: string;
  mode: Mode;
  setMode: (mode: Mode) => void;
  itemsReadOnly?: boolean;
  groupsReadOnly?: boolean;
  children?: React.ReactNode;
  extraButtons?: React.ReactNode;
}

export default function ItemGroupEditorPage<T extends Item, G extends Group>({
  title,
  instructions,
  data,
  updateData,
  itemLabel,
  itemLabelPlural,
  mode,
  setMode,
  itemsReadOnly = false,
  groupsReadOnly = false,
  children,
  extraButtons,
}: ItemGroupEditorPageProps<T, G>) {
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

    if (isDuplicateId(trimmedId, draft.editingId)) {
      setError(`This ID is already used by another ${itemLabel.toLowerCase()} or group`);
      return;
    }

    if (draft.isItem) {
      if (draft.editingId) {
        updateData(updateItem(data, draft.editingId, trimmedId, draft.groups, trimmedDescription));
      } else {
        updateData(addItem(data, trimmedId, draft.groups, trimmedDescription));
      }
    } else {
      if (draft.editingId) {
        updateData(updateGroup(data, draft.editingId, trimmedId, draft.members, trimmedDescription));
      } else {
        updateData(addGroup(data, trimmedId, draft.members, trimmedDescription));
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
      const group = groups.find(g => g.id === id);
      if (group) {
        setDraft({ id: group.id, description: group.description, groups: [], members: group.members, editingId: id, isItem: false });
      } else {
        console.error(`Group with ID ${id} not found during edit. ${ERROR_SHOULD_NOT_HAPPEN}`);
      }
    }
    setError('');
  };

  const handleDelete = (id: string) => {
    const isItem = items.some(i => i.id === id);
    if (isItem) {
      if (itemsReadOnly) {
        console.error(`Cannot delete ${itemLabel.toLowerCase()} ${id} - items are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
      updateData(deleteItem(data, id));
    } else {
      if (groupsReadOnly) {
        console.error(`Cannot delete group ${id} - groups are read-only. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }
      updateData(deleteGroup(data, id));
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

      if (isDuplicateId(value, id)) {
        setError(`This ID is already used by another ${isItem ? itemLabel.toLowerCase() : "group"}`);
        return;
      }

      if (isItem) {
        updateData(updateItem(data, id, value, undefined, undefined));
      } else {
        updateData(updateGroup(data, id, value, undefined, undefined));
      }
    } else if (field === 'description') {
      if (isItem) {
        updateData(updateItem(data, id, id, undefined, value));
      } else {
        updateData(updateGroup(data, id, id, undefined, value));
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
    removeItemFromGroup: (itemId: string, groupId: string) => updateData(removeItemFromGroup(data, itemId, groupId)),
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
    removeItemFromGroup: (itemId: string, groupId: string) => updateData(removeItemFromGroup(data, itemId, groupId)),
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
          itemLabelPlural={itemLabelPlural}
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
          onReorder={mode === Mode.INLINE_EDITING || itemsReadOnly ? undefined : (items: Item[]) => updateData(reorderItems(data, items as T[]))}
        />

        <DataTable
          title={itemLabelPlural + ' Groups'}
          columns={groupColumns}
          data={groups}
          onReorder={mode === Mode.INLINE_EDITING || groupsReadOnly ? undefined : (groups: Group[]) => updateData(updateGroups(data, groups as G[]))}
        />
      </div>
    </div>
  );
}
