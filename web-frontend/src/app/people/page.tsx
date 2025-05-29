'use client';

import { useState, useEffect, useRef } from 'react';
import { FiPlus } from 'react-icons/fi';
import { FormInput } from '@/components/FormInput';
import { TableRowActions } from '@/components/TableRowActions';
import { DataTable } from '@/components/DataTable';
import { useIdValidation } from '@/hooks/useIdValidation';
import { usePeople } from '@/contexts/PeopleContext';
import { ERROR_SHOULD_NOT_HAPPEN } from '@/constants/errors';

interface Person {
  id: string;
}

interface PeopleGroup {
  id: string;
  members: string[]; // Array of person IDs
}

enum Mode {
  NORMAL = 'NORMAL',
  ADDING = 'ADDING',
  EDITING = 'EDITING',
  INLINE_EDITING = 'INLINE_EDITING'
}

export default function PeoplePage() {
  const {
    people,
    groups,
    addPerson,
    addGroup,
    updatePerson,
    updateGroup,
    deletePerson,
    deleteGroup,
    removePersonFromGroup,
    updatePeople,
    updateGroups,
  } = usePeople();

  const [mode, setMode] = useState<Mode>(Mode.NORMAL);
  const [draft, setDraft] = useState<{
    id: string;
    groups: string[];
    members: string[];
    editingId?: string;
    isPerson: boolean;
  }>({ 
    id: '',
    groups: [],
    members: [],
    isPerson: true,
  });
  const [error, setError] = useState<string>('');
  const mouseDownCheckboxIdRef = useRef('');
  const mouseEnteredCheckboxIdRef = useRef('');
  const isMultiSelectDragRef = useRef(false);

  const { isDuplicateId } = useIdValidation(people, groups);

  const handleSave = () => {
    const trimmedId = draft.id.trim();
    if (!trimmedId) {
      setError(`${draft.isPerson ? 'Person' : 'Group'} ID cannot be empty`);
      return;
    }
    
    if (isDuplicateId(trimmedId, draft.editingId)) {
      setError(`This ID is already used by another person or group`);
      return;
    }

    if (draft.isPerson) {
      if (draft.editingId) {
        // Update existing person with their groups
        updatePerson(draft.editingId, trimmedId, draft.groups);
      } else {
        // Add new person with their groups
        addPerson(trimmedId, draft.groups);
      }
    } else {
      if (draft.editingId) {
        // Update existing group
        updateGroup(draft.editingId, trimmedId, draft.members);
      } else {
        // Add new group
        addGroup(trimmedId, draft.members);
      }
    }

    setDraft({ id: '', groups: [], members: [], isPerson: true });
    setMode(Mode.NORMAL);
    setError('');
  };

  const handleEdit = (id: string) => {
    const isPerson = people.some(p => p.id === id);
    setMode(Mode.EDITING);
    
    if (isPerson) {
      const person = people.find(p => p.id === id);
      if (person) {
        const peopleGroups = groups
          .filter(g => g.members.includes(person.id))
          .map(g => g.id);
        setDraft({ id: person.id, groups: peopleGroups, members: [], editingId: id, isPerson: true });
      } else {
        console.error(`Person with ID ${id} not found during edit. ${ERROR_SHOULD_NOT_HAPPEN}`);
      }
    } else {
      const group = groups.find(g => g.id === id);
      if (group) {
        setDraft({ id: group.id, groups: [], members: group.members, editingId: id, isPerson: false });
      } else {
        console.error(`Group with ID ${id} not found during edit. ${ERROR_SHOULD_NOT_HAPPEN}`);
      }
    }
    setError('');
  };

  const handleDelete = (id: string) => {
    const isPerson = people.some(p => p.id === id);
    if (isPerson) {
      deletePerson(id);
    } else {
      deleteGroup(id);
    }
  };

  const handleCancel = () => {
    setMode(Mode.NORMAL);
    setDraft({ id: '', groups: [], members: [], isPerson: true });
    setError('');
  };

  const handleDraftIdChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDraft(prev => ({ ...prev, id: e.target.value }));
    setError('');
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
    if (draft.isPerson) {
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

  // Helper function to get groups for a person
  const getPeopleGroups = (personId: string) => {
    return groups.filter(group => group.members.includes(personId));
  };

  const handleInlineEdit = (id: string, isPerson: boolean) => {
    setMode(Mode.INLINE_EDITING);
    setDraft({ id, groups: [], members: [], editingId: id, isPerson });
    setError('');
  };

  const handleInlineSave = () => {
    const trimmedId = draft.id.trim();
    if (!trimmedId) {
      setError(`${draft.isPerson ? 'Person' : 'Group'} ID cannot be empty`);
      return;
    }
    
    if (isDuplicateId(trimmedId, draft.editingId)) {
      setError(`This ID is already used by another person or group`);
      return;
    }

    if (draft.isPerson) {
      updatePerson(draft.editingId!, trimmedId);
    } else {
      updateGroup(draft.editingId!, trimmedId);
    }

    setMode(Mode.NORMAL);
    setDraft({ id: '', groups: [], members: [], isPerson: true });
    setError('');
  };

  const handleInlineCancel = () => {
    setMode(Mode.NORMAL);
    setDraft({ id: '', groups: [], members: [], isPerson: true });
    setError('');
  };

  const handleInlineKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleInlineSave();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      handleInlineCancel();
    }
  };

  const renderForm = () => {
    const isPerson = draft.isPerson;
    const title = `${mode === Mode.ADDING ? 'Add New' : 'Edit'} ${isPerson ? 'Person' : 'Group'}`;
    const placeholder = `Enter ${isPerson ? 'person' : 'group'} ID`;

    return (
      <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
        <div className="px-6 py-4">
          <h2 className="text-lg font-semibold mb-4 text-gray-800">{title}</h2>
          <FormInput
            value={draft.id}
            onChange={handleDraftIdChange}
            onKeyDown={handleKeyDown}
            error={error}
            placeholder={placeholder}
            onPrimary={handleSave}
            onCancel={handleCancel}
            primaryText={mode === Mode.ADDING ? 'Add' : 'Update'}
          >
            <div className="space-y-2">
              <h3 className="text-sm font-medium text-gray-700">
                {isPerson ? 'Groups' : 'Members'}
              </h3>
              <div className="flex flex-wrap gap-2">
                {(isPerson ? groups : people).map(item => (
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
                      checked={isPerson 
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
        <h1 className="text-3xl font-bold text-gray-800">People Management</h1>
        <div className="flex gap-4">
          <button
            onClick={() => {
              setMode(Mode.ADDING);
              setDraft({ id: '', groups: [], members: [], isPerson: true });
            }}
            className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
          >
            <FiPlus className="h-4 w-4" />
            Add Person
          </button>
          <button
            onClick={() => {
              setMode(Mode.ADDING);
              setDraft({ id: '', groups: [], members: [], isPerson: false });
            }}
            className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
          >
            <FiPlus className="h-4 w-4" />
            Add Group
          </button>
        </div>
      </div>

      {(mode === Mode.ADDING || mode === Mode.EDITING) && renderForm()}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <DataTable
          title="People"
          columns={[
            { 
              header: 'ID', 
              accessor: (person: Person) => (
                mode === Mode.INLINE_EDITING && draft.editingId === person.id ? (
                  <input
                    type="text"
                    value={draft.id}
                    onChange={handleDraftIdChange}
                    onKeyDown={handleInlineKeyDown}
                    onBlur={handleInlineSave}
                    className={`px-2 py-1 border rounded ${error ? 'border-red-500' : ''}`}
                    autoFocus
                  />
                ) : (
                  <div 
                    onDoubleClick={() => handleInlineEdit(person.id, true)}
                    className="cursor-pointer"
                  >
                    {person.id}
                  </div>
                )
              )
            },
            { 
              header: 'Groups', 
              accessor: (person: Person) => (
                <div className="flex flex-wrap gap-1">
                  {getPeopleGroups(person.id).map(group => (
                    <span key={group.id} className="inline-flex items-center bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded cursor-default">
                      <button
                        onClick={() => removePersonFromGroup(person.id, group.id)}
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
              accessor: (person: Person) => (
                <TableRowActions
                  onEdit={() => handleEdit(person.id)}
                  onDelete={() => handleDelete(person.id)}
                />
              ),
              align: 'right'
            }
          ]}
          data={people}
          onReorder={updatePeople}
        />

        <DataTable
          title="Groups"
          columns={[
            { 
              header: 'ID', 
              accessor: (group: PeopleGroup) => (
                mode === Mode.INLINE_EDITING && draft.editingId === group.id ? (
                  <input
                    type="text"
                    value={draft.id}
                    onChange={handleDraftIdChange}
                    onKeyDown={handleInlineKeyDown}
                    onBlur={handleInlineSave}
                    className={`px-2 py-1 border rounded ${error ? 'border-red-500' : ''}`}
                    autoFocus
                  />
                ) : (
                  <div 
                    onDoubleClick={() => handleInlineEdit(group.id, false)}
                    className="cursor-pointer"
                  >
                    {group.id}
                  </div>
                )
              )
            },
            {
              header: 'Members',
              accessor: (group: PeopleGroup) => (
                <div className="flex flex-wrap gap-1">
                  {group.members.map(memberId => {
                    const person = people.find(p => p.id === memberId);
                    return person ? (
                      <span key={person.id} className="inline-flex items-center bg-gray-100 text-gray-800 text-xs px-2 py-1 rounded cursor-default">
                        <button
                          onClick={() => removePersonFromGroup(person.id, group.id)}
                          className="mr-1 text-gray-600 hover:text-gray-900"
                        >
                          ×
                        </button>
                        {person.id}
                      </span>
                    ) : null;
                  })}
                </div>
              )
            },
            {
              header: 'Actions',
              accessor: (group: PeopleGroup) => (
                <TableRowActions
                  onEdit={() => handleEdit(group.id)}
                  onDelete={() => handleDelete(group.id)}
                />
              ),
              align: 'right'
            }
          ]}
          data={groups}
          onReorder={updateGroups}
        />
      </div>
    </div>
  );
}
