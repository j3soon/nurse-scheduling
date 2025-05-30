'use client';

import { useState, useEffect, useRef } from 'react';
import { FiPlus } from 'react-icons/fi';
import { FormInput } from '@/components/FormInput';
import { TableRowActions } from '@/components/TableRowActions';
import { DataTable } from '@/components/DataTable';
import { InlineEdit } from '@/components/InlineEdit';
import { useIdValidation } from '@/hooks/useIdValidation';
import { ERROR_SHOULD_NOT_HAPPEN } from '@/constants/errors';

interface Item {
  id: string;
  description: string;
}

interface Group {
  id: string;
  members: string[]; // Array of item IDs
  description: string;
}

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
  groupLabel: string;
}

enum Mode {
  NORMAL = 'NORMAL',
  ADDING = 'ADDING',
  EDITING = 'EDITING',
  INLINE_EDITING = 'INLINE_EDITING'
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
  groupLabel,
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
  const mouseDownCheckboxIdRef = useRef('');
  const mouseEnteredCheckboxIdRef = useRef('');
  const isMultiSelectDragRef = useRef(false);

  const { isDuplicateId } = useIdValidation(items, groups);

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
        // Update existing item with their groups
        updateItem(draft.editingId, trimmedId, draft.groups, trimmedDescription);
      } else {
        // Add new item with their groups
        addItem(trimmedId, draft.groups, trimmedDescription);
      }
    } else {
      if (draft.editingId) {
        // Update existing group
        updateGroup(draft.editingId, trimmedId, draft.members, trimmedDescription);
      } else {
        // Add new group
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

  const handleCheckboxMouseEnter = (id: string) => {
    mouseEnteredCheckboxIdRef.current = id;
    if (isMultiSelectDragRef.current) {
      handleMemberToggle(id);
    }
  };

  const handleCheckboxMouseDown = (id: string) => {
    if (id === mouseEnteredCheckboxIdRef.current && !isMultiSelectDragRef.current) {
      mouseDownCheckboxIdRef.current = id;
      document.body.style.userSelect = 'none';
    }
  };

  const handleCheckboxMouseLeave = (id: string) => {
    if (mouseDownCheckboxIdRef.current && mouseEnteredCheckboxIdRef.current === mouseDownCheckboxIdRef.current) {
      // Start multi-select drag
      isMultiSelectDragRef.current = true;
      // Toggle the initial checkbox when leaving it
      handleMemberToggle(mouseDownCheckboxIdRef.current);
      mouseDownCheckboxIdRef.current = '';
    }
    mouseEnteredCheckboxIdRef.current = '';
  };

  const handleCheckboxMouseUp = (id: string) => {
    if (!isMultiSelectDragRef.current) {
      // Normal checkbox click behavior
      handleMemberToggle(id);
    }
    // End multi-select drag
    isMultiSelectDragRef.current = false;
    mouseDownCheckboxIdRef.current = '';
    document.body.style.userSelect = '';
  };

  // Add event listener for mouse up outside the component
  useEffect(() => {
    const handleGlobalMouseUp = () => {
      // End multi-select drag
      isMultiSelectDragRef.current = false;
      mouseDownCheckboxIdRef.current = '';
      document.body.style.userSelect = '';
    };

    window.addEventListener('mouseup', handleGlobalMouseUp);
    // Cleanup event listener
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp);
      document.body.style.userSelect = '';
    };
  }, []);

  // Helper function to get groups for an item
  const getItemGroups = (itemId: string) => {
    return groups.filter(group => group.members.includes(itemId));
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

  const renderForm = () => {
    const isItem = draft.isItem;
    const title = `${mode === Mode.ADDING ? 'Add New' : 'Edit'} ${isItem ? itemLabel : groupLabel}`;
    const placeholder = `Enter ${isItem ? itemLabel.toLowerCase() : groupLabel.toLowerCase()} ID`;

    return (
      <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
        <div className="px-6 py-4">
          <h2 className="text-lg font-semibold mb-4 text-gray-800">{title}</h2>
          <FormInput
            itemValue={draft.id}
            itemPlaceholder={placeholder}
            onItemChange={handleDraftIdChange}
            descriptionValue={draft.description}
            descriptionPlaceholder={`Enter ${isItem ? itemLabel.toLowerCase() : groupLabel.toLowerCase()} description (optional)`}
            onDescriptionChange={handleDraftDescriptionChange}
            onKeyDown={handleKeyDown}
            error={error}
            onAction={handleSave}
            onCancel={handleCancel}
            actionText={mode === Mode.ADDING ? 'Add' : 'Update'}
          >
            <div className="space-y-2">
              <h3 className="text-sm font-medium text-gray-700">
                {isItem ? groupLabel + 's' : 'Members'}
              </h3>
              <div className="flex flex-wrap gap-2">
                {(isItem ? groups : items).map(item => (
                  <label
                    key={item.id}
                    className="inline-flex items-center"
                    onMouseEnter={() => handleCheckboxMouseEnter(item.id)}
                    onMouseDown={() => handleCheckboxMouseDown(item.id)}
                    onMouseLeave={() => handleCheckboxMouseLeave(item.id)}
                    onMouseUp={() => handleCheckboxMouseUp(item.id)}
                  >
                    <input
                      type="checkbox"
                      checked={isItem
                        ? draft.groups.includes(item.id)
                        : draft.members.includes(item.id)
                      }
                      onChange={() => {}} // Prevent default onChange to handle it in mouseUp
                      className="form-checkbox h-4 w-4 text-blue-600"
                    />
                    <span className="ml-2 text-sm text-gray-700">{item.id}</span>
                  </label>
                ))}
              </div>
            </div>
          </FormInput>
        </div>
      </div>
    );
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <h1 className="text-3xl font-bold text-gray-800">{title}</h1>
        <div className="flex gap-4">
          <button
            onClick={() => {
              setMode(Mode.ADDING);
              setDraft({ id: '', description: '', groups: [], members: [], isItem: true });
              setError('');
            }}
            className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
          >
            <FiPlus className="h-4 w-4" />
            Add {itemLabel}
          </button>
          <button
            onClick={() => {
              setMode(Mode.ADDING);
              setDraft({ id: '', description: '', groups: [], members: [], isItem: false });
              setError('');
            }}
            className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
          >
            <FiPlus className="h-4 w-4" />
            Add {groupLabel}
          </button>
        </div>
      </div>

      {(mode === Mode.ADDING || mode === Mode.EDITING) && renderForm()}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <DataTable
          title={itemLabel + 's'}
          columns={[
            {
              header: 'ID',
              accessor: (item: T) => (
                <div>
                  <InlineEdit
                    value={item.id}
                    isEditing={mode === Mode.INLINE_EDITING && inlineEditingId === item.id && inlineEditingField === 'id'}
                    onSave={(value) => handleInlineSave(item.id, 'id', true, value)}
                    onCancel={handleInlineCancel}
                    onDoubleClick={() => handleInlineEdit(item.id, true, 'id')}
                    error={error}
                  />
                  <InlineEdit
                    value={item.description}
                    isEditing={mode === Mode.INLINE_EDITING && inlineEditingId === item.id && inlineEditingField === 'description'}
                    onSave={(value) => handleInlineSave(item.id, 'description', true, value)}
                    onCancel={handleInlineCancel}
                    onDoubleClick={() => handleInlineEdit(item.id, true, 'description')}
                    className="text-xs text-gray-400 mt-1"
                    editClassName="text-xs mt-1 w-full"
                    emptyText="Add description..."
                    placeholder="Enter description..."
                  />
                </div>
              )
            },
            {
              header: groupLabel + 's',
              accessor: (item: T) => (
                <div className="flex flex-wrap gap-1">
                  {getItemGroups(item.id).map(group => (
                    <span key={group.id} className="inline-flex items-center bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded cursor-default">
                      <button
                        onClick={() => removeItemFromGroup(item.id, group.id)}
                        className="mr-1 text-blue-600 hover:text-blue-900"
                      >
                        ×
                      </button>
                      {group.id}
                    </span>
                  ))}
                </div>
              )
            },
            {
              header: 'Actions',
              accessor: (item: T) => (
                <TableRowActions
                  onEdit={() => handleEdit(item.id)}
                  onDelete={() => handleDelete(item.id)}
                />
              ),
              align: 'right'
            }
          ]}
          data={items}
          onReorder={mode === Mode.INLINE_EDITING ? undefined : reorderItems}
        />

        <DataTable
          title={groupLabel + 's'}
          columns={[
            {
              header: 'ID',
              accessor: (group: G) => (
                <div>
                  <InlineEdit
                    value={group.id}
                    isEditing={mode === Mode.INLINE_EDITING && inlineEditingId === group.id && inlineEditingField === 'id'}
                    onSave={(value) => handleInlineSave(group.id, 'id', false, value)}
                    onCancel={handleInlineCancel}
                    onDoubleClick={() => handleInlineEdit(group.id, false, 'id')}
                    error={error}
                  />
                  <InlineEdit
                    value={group.description}
                    isEditing={mode === Mode.INLINE_EDITING && inlineEditingId === group.id && inlineEditingField === 'description'}
                    onSave={(value) => handleInlineSave(group.id, 'description', false, value)}
                    onCancel={handleInlineCancel}
                    onDoubleClick={() => handleInlineEdit(group.id, false, 'description')}
                    className="text-xs text-gray-400 mt-1"
                    editClassName="text-xs mt-1 w-full"
                    emptyText="Add description..."
                    placeholder="Enter description..."
                  />
                </div>
              )
            },
            {
              header: 'Members',
              accessor: (group: G) => (
                <div className="flex flex-wrap gap-1">
                  {group.members.map(memberId => {
                    const item = items.find(i => i.id === memberId);
                    return item ? (
                      <span key={item.id} className="inline-flex items-center bg-gray-100 text-gray-800 text-xs px-2 py-1 rounded cursor-default">
                        <button
                          onClick={() => removeItemFromGroup(item.id, group.id)}
                          className="mr-1 text-gray-600 hover:text-gray-900"
                        >
                          ×
                        </button>
                        {item.id}
                      </span>
                    ) : null;
                  })}
                </div>
              )
            },
            {
              header: 'Actions',
              accessor: (group: G) => (
                <TableRowActions
                  onEdit={() => handleEdit(group.id)}
                  onDelete={() => handleDelete(group.id)}
                />
              ),
              align: 'right'
            }
          ]}
          data={groups}
          onReorder={mode === Mode.INLINE_EDITING ? undefined : updateGroups}
        />
      </div>
    </div>
  );
}
