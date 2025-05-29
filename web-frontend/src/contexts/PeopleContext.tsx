'use client';

import { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import { ERROR_SHOULD_NOT_HAPPEN } from '../constants/errors';

interface Person {
  id: string;
}

interface PeopleGroup {
  id: string;
  members: string[]; // Array of person IDs
}

interface PeopleContextType {
  people: Person[];
  groups: PeopleGroup[];
  updatePeople: (people: Person[]) => void;
  updateGroups: (groups: PeopleGroup[]) => void;
  addPerson: (id: string, groupIds: string[]) => void;
  addGroup: (id: string, memberIds: string[]) => void;
  updatePerson: (oldId: string, newId: string, groupIds?: string[]) => void;
  updateGroup: (oldId: string, newId: string, members?: string[]) => void;
  deletePerson: (id: string) => void;
  deleteGroup: (id: string) => void;
  removePersonFromGroup: (personId: string, groupId: string) => void;
  createNewState: () => void;
}

const PeopleContext = createContext<PeopleContextType | undefined>(undefined);

const STORAGE_KEY = 'nurse-scheduling-data';

function loadFromStorage() {
  if (typeof window === 'undefined') return null;
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) return null;
  try {
    return JSON.parse(stored);
  } catch (e) {
    console.error('Failed to parse stored data:', e);
    return null;
  }
}

function saveToStorage(people: Person[], groups: PeopleGroup[]) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ people, groups }));
  } catch (e) {
    console.error('Failed to save data to storage:', e);
  }
}

export function PeopleProvider({ children }: { children: ReactNode }) {
  const [people, setPeople] = useState<Person[]>([]);
  const [groups, setGroups] = useState<PeopleGroup[]>([]);
  const [isInitialized, setIsInitialized] = useState(false);

  const createNewState = () => {
    const defaultPeople = Array.from({ length: 10 }, (_, index) => ({
      id: `Person ${index + 1}`
    }));
    const defaultGroups = [
      { id: 'Group 1', members: ['Person 1', 'Person 2'] },
      { id: 'Group 2', members: ['Person 2', 'Person 3', 'Person 4'] },
      { id: 'Group 3', members: ['Person 3', 'Person 4', 'Person 5', 'Person 6'] },
      { id: 'Group 4', members: ['Person 4', 'Person 5', 'Person 6', 'Person 7', 'Person 8'] },
      { id: 'Group 5', members: ['Person 5', 'Person 6', 'Person 7', 'Person 8', 'Person 9', 'Person 10'] },
    ];
    setPeople(defaultPeople);
    setGroups(defaultGroups);
  };

  // Initialize state from localStorage after mount
  useEffect(() => {
    const storedData = loadFromStorage();
    if (storedData) {
      setPeople(storedData.people);
      setGroups(storedData.groups);
    } else {
      createNewState();
    }
    setIsInitialized(true);
  }, []);

  // Save to localStorage whenever state changes
  useEffect(() => {
    if (isInitialized) {
      saveToStorage(people, groups);
    }
  }, [people, groups, isInitialized]);

  const updatePeople = (newPeople: Person[]) => {
    setPeople(newPeople);
  };

  const updateGroups = (newGroups: PeopleGroup[]) => {
    setGroups(newGroups);
  };

  const addPerson = (id: string, groupIds: string[]) => {
    // Add the person
    const newPeople = [...people, { id }];

    // If groupIds is provided, add the person to those groups
    const updatedGroups = groups.map(group => {
      if (groupIds.includes(group.id)) {
        const allMembers = [...group.members, id];
        // Sort members based on updated people order
        const sortedMembers = newPeople
          .filter(person => allMembers.includes(person.id))
          .map(person => person.id);
        return {
          ...group,
          members: sortedMembers
        };
      }
      return group;
    });
    updatePeople(newPeople);
    updateGroups(updatedGroups);
  };

  const addGroup = (id: string, memberIds: string[]) => {
    // Sort members based on people order
    const sortedMembers = people
      .filter(person => memberIds.includes(person.id))
      .map(person => person.id);

    const newGroups = [...groups, { id, members: sortedMembers }];
    updateGroups(newGroups);
  };

  const updatePerson = (oldId: string, newId: string, groupIds?: string[]) => {
    // First update the person's ID
    const updatedPeople = people.map(p => p.id === oldId ? { id: newId } : p);

    // Always update group memberships to reflect the new ID
    const updatedGroups = groups.map(group => {
      // Get current members excluding the edited person
      const otherMembers = group.members.filter(id => id !== oldId);

      // Add the person if they should be in this group
      const allMembers = groupIds
        ? (groupIds.includes(group.id) ? [...otherMembers, newId] : otherMembers)
        : (group.members.includes(oldId) ? [...otherMembers, newId] : otherMembers);

      // Sort members based on updated people order
      const sortedMembers = updatedPeople
        .filter(person => allMembers.includes(person.id))
        .map(person => person.id);

      return {
        ...group,
        members: sortedMembers
      };
    });
    updatePeople(updatedPeople);
    updateGroups(updatedGroups);
  };

  const updateGroup = (oldId: string, newId: string, members?: string[]) => {
    const group = groups.find(g => g.id === oldId);
    if (!group) {
      console.error(`Group with ID ${oldId} not found. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }

    // Sort members based on people order
    const sortedMembers = members
      ? people
          .filter(person => members.includes(person.id))
          .map(person => person.id)
      : group.members;

    const newGroups = groups.map(g => g.id === oldId ? { id: newId, members: sortedMembers } : g);
    updateGroups(newGroups);
  };

  const deletePerson = (id: string) => {
    const newPeople = people.filter(p => p.id !== id);
    const newGroups = groups.map(group => ({
      ...group,
      members: group.members.filter(memberId => memberId !== id)
    }));
    updatePeople(newPeople);
    updateGroups(newGroups);
  };

  const deleteGroup = (id: string) => {
    const newGroups = groups.filter(g => g.id !== id);
    updateGroups(newGroups);
  };

  const removePersonFromGroup = (personId: string, groupId: string) => {
    const newGroups = groups.map(group =>
      group.id === groupId
        ? { ...group, members: group.members.filter(id => id !== personId) }
        : group
    );
    updateGroups(newGroups);
  };

  const value = {
    people,
    groups,
    updatePeople,
    updateGroups,
    addPerson,
    addGroup,
    updatePerson,
    updateGroup,
    deletePerson,
    deleteGroup,
    removePersonFromGroup,
    createNewState,
  };

  return (
    <PeopleContext.Provider value={value}>
      {children}
    </PeopleContext.Provider>
  );
}

export function usePeople() {
  const context = useContext(PeopleContext);
  if (context === undefined) {
    throw new Error('usePeople must be used within a PeopleProvider');
  }
  return context;
}
