'use client';

import { useState } from 'react';
import { FiEdit2, FiTrash2, FiPlus, FiX, FiAlertCircle } from 'react-icons/fi';

interface Person {
  id: string;
}

enum Mode {
  NORMAL = 'NORMAL',
  ADDING = 'ADDING',
  EDITING = 'EDITING'
}

export default function PeoplePage() {
  const [people, setPeople] = useState<Person[]>([
    { id: 'Nurse 1' },
    { id: 'Nurse 2' },
  ]);
  const [mode, setMode] = useState<Mode>(Mode.NORMAL);
  const [personDraft, setPersonDraft] = useState<{ id: string }>({ id: '' });
  const [editingPersonId, setEditingPersonId] = useState<string>('');
  const [error, setError] = useState<string>('');

  const isDuplicateId = (id: string, currentId?: string) => {
    return people.some(person => person.id === id && person.id !== currentId);
  };

  const handleAdd = () => {
    const trimmedId = personDraft.id.trim();
    if (!trimmedId) {
      setError('ID cannot be empty');
      return;
    }
    
    if (isDuplicateId(trimmedId)) {
      setError('This ID already exists');
      return;
    }

    setPeople([...people, { id: trimmedId }]);
    setPersonDraft({ id: '' });
    setMode(Mode.NORMAL);
    setError('');
  };

  const handleEdit = (id: string) => {
    setMode(Mode.EDITING);
    const person = people.find(p => p.id === id);
    if (person) {
      setPersonDraft({ id: person.id });
      setEditingPersonId(id);
    }
    setError('');
  };

  const handleUpdate = () => {
    const trimmedId = personDraft.id.trim();
    if (!trimmedId) {
      setError('ID cannot be empty');
      return;
    }

    if (isDuplicateId(trimmedId, editingPersonId)) {
      setError('This ID already exists');
      return;
    }

    setPeople(people.map(p => 
      p.id === editingPersonId ? { id: trimmedId } : p
    ));
    setPersonDraft({ id: '' });
    setEditingPersonId('');
    setMode(Mode.NORMAL);
    setError('');
  };

  const handleDelete = (id: string) => {
    setPeople(people.filter(p => p.id !== id));
  };

  const handleCancel = () => {
    setMode(Mode.NORMAL);
    setPersonDraft({ id: '' });
    setEditingPersonId('');
    setError('');
  };

  const handleDraftIdChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPersonDraft({ id: e.target.value });
    setError('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (mode === Mode.ADDING) {
        handleAdd();
      } else if (mode === Mode.EDITING) {
        handleUpdate();
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      handleCancel();
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold text-gray-800">People Management</h1>
        <button
          onClick={() => setMode(Mode.ADDING)}
          className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
        >
          <FiPlus className="h-4 w-4" />
          Add Person
        </button>
      </div>

      {(mode === Mode.ADDING || mode === Mode.EDITING) && (
        <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
          <div className="px-6 py-4">
            <h2 className="text-lg font-semibold mb-4 text-gray-800">
              {mode === Mode.ADDING ? 'Add New Person' : 'Edit Person'}
            </h2>
            <div className="space-y-4">
              <div>
                <input
                  type="text"
                  value={personDraft.id}
                  onChange={handleDraftIdChange}
                  onKeyDown={handleKeyDown}
                  autoFocus
                  placeholder="Enter person ID"
                  className={`block w-full px-4 py-2 text-sm text-gray-900 bg-white border rounded-lg shadow-sm transition-colors duration-200 ease-in-out
                    ${error 
                      ? 'border-red-300 focus:border-red-500 focus:ring-red-200' 
                      : 'border-gray-300 focus:border-blue-500 focus:ring-blue-200'
                    }
                    placeholder-gray-400
                    focus:outline-none focus:ring-2
                    hover:border-gray-400`}
                />
                {error && (
                  <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {error}
                  </p>
                )}
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={mode === Mode.ADDING ? handleAdd : handleUpdate}
                  className="text-sm text-blue-600 hover:text-blue-900 flex items-center gap-1"
                >
                  <FiPlus className="h-4 w-4" />
                  {mode === Mode.ADDING ? 'Add' : 'Update'}
                </button>
                <button
                  onClick={handleCancel}
                  className="text-sm text-gray-600 hover:text-gray-900 flex items-center gap-1"
                >
                  <FiX className="h-4 w-4" />
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white shadow-md rounded-lg overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                ID
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {people.map((person) => (
              <tr key={person.id}>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {person.id}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <div className="flex justify-end space-x-2">
                    <button
                      onClick={() => handleEdit(person.id)}
                      className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
                    >
                      <FiEdit2 className="h-4 w-4" />
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(person.id)}
                      className="text-red-600 hover:text-red-900 flex items-center gap-1"
                    >
                      <FiTrash2 className="h-4 w-4" />
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
} 