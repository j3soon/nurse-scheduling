'use client';

import { useState } from 'react';
import { FiPlus } from 'react-icons/fi';
import { FormInput } from '@/components/FormInput';
import { TableRowActions } from '@/components/TableRowActions';
import { DataTable } from '@/components/DataTable';
import { useIdValidation } from '@/hooks/useIdValidation';

interface Person {
  id: string;
}

interface PeopleGroup {
  id: string;
  members: string[]; // Array of person IDs
}

enum Mode {
  NORMAL = 'NORMAL',
  ADDING_PEOPLE = 'ADDING_PEOPLE',
  EDITING_PEOPLE = 'EDITING_PEOPLE',
  ADDING_GROUP = 'ADDING_GROUP',
  EDITING_GROUP = 'EDITING_GROUP'
}

const ERROR_SHOULD_NOT_HAPPEN = 'This indicates a bug in the code logic. Please report this issue so it can be addressed.';

export default function PeoplePage() {
  const [people, setPeople] = useState<Person[]>([
    { id: 'Person 1' },
    { id: 'Person 2' },
  ]);
  const [groups, setGroups] = useState<PeopleGroup[]>([
    { id: 'Group 1', members: ['Person 1', 'Person 2'] },
    { id: 'Group 2', members: ['Person 1'] },
    { id: 'Group 3', members: ['Person 2'] },
  ]);
  const [mode, setMode] = useState<Mode>(Mode.NORMAL);
  const [draft, setDraft] = useState<{
    id: string;
    groups: string[];
    members: string[];
    editingId?: string;
  }>({ 
    id: '',
    groups: [],
    members: []
  });
  const [error, setError] = useState<string>('');

  const { isDuplicateId } = useIdValidation(people, groups);

  const isPersonMode = mode === Mode.ADDING_PEOPLE || mode === Mode.EDITING_PEOPLE;
  const isGroupMode = mode === Mode.ADDING_GROUP || mode === Mode.EDITING_GROUP;

  const handleSave = () => {
    const trimmedId = draft.id.trim();
    if (!trimmedId) {
      setError(`${isPersonMode ? 'Person' : 'Group'} ID cannot be empty`);
      return;
    }
    
    if (isDuplicateId(trimmedId, draft.editingId)) {
      setError(`This ID is already used by another person or group`);
      return;
    }

    if (isPersonMode) {
      // Update people array
      let updatedPeople = people;
      if (draft.editingId) {
        // Update existing person
        updatedPeople = people.map(p => 
          p.id === draft.editingId ? { id: trimmedId } : p
        );
      } else {
        // Add new person
        updatedPeople = [...people, { id: trimmedId }];
      }
      setPeople(updatedPeople);

      // Update group memberships
      const updatedGroups = groups.map(group => {
        // Get current members excluding the edited person (if any)
        const otherMembers = group.members.filter(id => id !== draft.editingId);
        
        // Add the person if they should be in this group
        const allMembers = draft.groups.includes(group.id)
          ? [...otherMembers, trimmedId]
          : otherMembers;

        // Sort members based on people order
        // Note that we cannot use `people` here because calling the set function in React does not change state in the running code.
        const sortedMembers = updatedPeople
          .filter(person => allMembers.includes(person.id))
          .map(person => person.id);

        return {
          ...group,
          members: sortedMembers
        };
      });
      setGroups(updatedGroups);
    } else if (isGroupMode) {
      // Sort members based on people order
      const sortedMembers = people
        .filter(person => draft.members.includes(person.id))
        .map(person => person.id);

      if (draft.editingId) {
        // Update existing group
        setGroups(groups.map(g => 
          g.id === draft.editingId ? { id: trimmedId, members: sortedMembers } : g
        ));
      } else {
        // Add new group
        setGroups([...groups, { id: trimmedId, members: sortedMembers }]);
      }
    } else {
      console.error(`Invalid mode: ${mode}. ${ERROR_SHOULD_NOT_HAPPEN}`);
    }

    setDraft({ id: '', groups: [], members: [] });
    setMode(Mode.NORMAL);
    setError('');
  };

  const handleEdit = (id: string) => {
    const isPerson = people.some(p => p.id === id);
    setMode(isPerson ? Mode.EDITING_PEOPLE : Mode.EDITING_GROUP);
    
    if (isPerson) {
      const person = people.find(p => p.id === id);
      if (person) {
        const peopleGroups = groups
          .filter(g => g.members.includes(person.id))
          .map(g => g.id);
        setDraft({ id: person.id, groups: peopleGroups, members: [], editingId: id });
      } else {
        console.error(`Person with ID ${id} not found during edit. ${ERROR_SHOULD_NOT_HAPPEN}`);
      }
    } else if (isGroupMode) {
      const group = groups.find(g => g.id === id);
      if (group) {
        setDraft({ id: group.id, groups: [], members: group.members, editingId: id });
      } else {
        console.error(`Group with ID ${id} not found during edit. ${ERROR_SHOULD_NOT_HAPPEN}`);
      }
    } else {
      console.error(`Invalid mode: ${mode}. ${ERROR_SHOULD_NOT_HAPPEN}`);
    }
    setError('');
  };

  const handleDelete = (id: string) => {
    const isPerson = people.some(p => p.id === id);
    if (isPerson) {
      setPeople(people.filter(p => p.id !== id));
      // Remove person from all groups while preserving the original member order
      setGroups(groups.map(group => ({
        ...group,
        members: group.members.filter(memberId => memberId !== id)
      })));
    } else if (isGroupMode) {
      // Remove group while preserving the original member order
      setGroups(groups.filter(g => g.id !== id));
    } else {
      console.error(`Invalid mode: ${mode}. ${ERROR_SHOULD_NOT_HAPPEN}`);
    }
  };

  const handleCancel = () => {
    setMode(Mode.NORMAL);
    setDraft({ id: '', groups: [], members: [] });
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
    // The list may not be sorted, so we need to sort it upon saving.
    if (isPersonMode) {
      setDraft(prev => ({
        ...prev,
        groups: prev.groups.includes(id)
          ? prev.groups.filter(groupId => groupId !== id)
          : [...prev.groups, id]
      }));
    } else if (isGroupMode) {
      setDraft(prev => ({
        ...prev,
        members: prev.members.includes(id)
          ? prev.members.filter(memberId => memberId !== id)
          : [...prev.members, id]
      }));
    } else {
      console.error(`Invalid mode: ${mode}. ${ERROR_SHOULD_NOT_HAPPEN}`);
    }
  };

  // Helper function to get groups for a person
  const getPeopleGroups = (personId: string) => {
    return groups.filter(group => group.members.includes(personId));
  };

  const renderForm = () => {
    const isPerson = isPersonMode;
    const title = `${mode === Mode.ADDING_PEOPLE || mode === Mode.ADDING_GROUP ? 'Add New' : 'Edit'} ${isPerson ? 'Person' : 'Group'}`;
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
            primaryText={mode === Mode.ADDING_PEOPLE || mode === Mode.ADDING_GROUP ? 'Add' : 'Update'}
          >
            <div className="space-y-2">
              <h3 className="text-sm font-medium text-gray-700">
                {isPerson ? 'Groups' : 'Members'}
              </h3>
              <div className="flex flex-wrap gap-2">
                {(isPerson ? groups : people).map(item => (
                  <label key={item.id} className="inline-flex items-center">
                    <input
                      type="checkbox"
                      checked={isPerson 
                        ? draft.groups.includes(item.id)
                        : draft.members.includes(item.id)
                      }
                      onChange={() => handleMemberToggle(item.id)}
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
            onClick={() => setMode(Mode.ADDING_PEOPLE)}
            className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
          >
            <FiPlus className="h-4 w-4" />
            Add Person
          </button>
          <button
            onClick={() => setMode(Mode.ADDING_GROUP)}
            className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
          >
            <FiPlus className="h-4 w-4" />
            Add Group
          </button>
        </div>
      </div>

      {(mode === Mode.ADDING_PEOPLE || mode === Mode.EDITING_PEOPLE || 
        mode === Mode.ADDING_GROUP || mode === Mode.EDITING_GROUP) && renderForm()}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <DataTable
          title="People"
          columns={[
            { header: 'ID', accessor: 'id' },
            { 
              header: 'Groups', 
              accessor: (person: Person) => (
                <div>
                  {getPeopleGroups(person.id).map(group => (
                    <span key={group.id} className="inline-block bg-blue-100 text-blue-800 text-xs px-2 py-1 rounded mr-2 mb-1">
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
        />

        <DataTable
          title="Groups"
          columns={[
            { header: 'ID', accessor: 'id' },
            {
              header: 'Members',
              accessor: (group: PeopleGroup) => (
                <div>
                  {group.members.map(memberId => {
                    const person = people.find(p => p.id === memberId);
                    return person ? (
                      <span key={memberId} className="inline-block bg-gray-100 text-gray-800 text-xs px-2 py-1 rounded mr-2 mb-1">
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
        />
      </div>
    </div>
  );
} 