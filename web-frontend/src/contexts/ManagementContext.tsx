'use client';

import { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import { ERROR_SHOULD_NOT_HAPPEN } from '../constants/errors';

interface Item {
  id: string;
  description: string;
}

interface Group {
  id: string;
  members: string[]; // Array of item IDs
  description: string;
}

interface ManagementContextType<T extends Item, G extends Group> {
  items: T[];
  groups: G[];
  updateItems: (items: T[]) => void;
  updateGroups: (groups: G[]) => void;
  addItem: (id: string, groupIds: string[], description?: string) => void;
  addGroup: (id: string, memberIds: string[], description?: string) => void;
  updateItem: (oldId: string, newId: string, groupIds?: string[], description?: string) => void;
  updateGroup: (oldId: string, newId: string, members?: string[], description?: string) => void;
  deleteItem: (id: string) => void;
  deleteGroup: (id: string) => void;
  removeItemFromGroup: (itemId: string, groupId: string) => void;
  reorderItems: (reorderedItems: T[]) => void;
  createNewState: () => void;
}

interface ManagementContextConfig<T extends Item, G extends Group> {
  storageKey: string;
  createDefaultState: () => { items: T[]; groups: G[] };
}

export function loadFromStorage(storageKey: string) {
  if (typeof window === 'undefined') return null;
  const stored = localStorage.getItem(storageKey);
  if (!stored) return null;
  try {
    return JSON.parse(stored);
  } catch (e) {
    console.error('Failed to parse stored data:', e);
    return null;
  }
}

export function saveToStorage<T extends Item, G extends Group>(storageKey: string, items: T[], groups: G[]) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(storageKey, JSON.stringify({ items, groups }));
  } catch (e) {
    console.error('Failed to save data to storage:', e);
  }
}

export function createManagementContext<T extends Item, G extends Group>(
  config: ManagementContextConfig<T, G>
) {
  const ManagementContext = createContext<ManagementContextType<T, G> | undefined>(undefined);

  function ManagementProvider({ children }: { children: ReactNode }) {
    const [items, setItems] = useState<T[]>([]);
    const [groups, setGroups] = useState<G[]>([]);
    const [isInitialized, setIsInitialized] = useState(false);

    const createNewState = () => {
      const { items: defaultItems, groups: defaultGroups } = config.createDefaultState();
      setItems(defaultItems);
      setGroups(defaultGroups);
    };

    // Initialize state from localStorage after mount
    useEffect(() => {
      const storedData = loadFromStorage(config.storageKey);
      if (storedData) {
        setItems(storedData.items || []);
        setGroups(storedData.groups || []);
      } else {
        createNewState();
      }
      setIsInitialized(true);
    }, []);

    // Save to localStorage whenever state changes
    useEffect(() => {
      if (isInitialized) {
        saveToStorage(config.storageKey, items, groups);
      }
    }, [items, groups, isInitialized]);

    const updateItems = (newItems: T[]) => {
      setItems(newItems);
    };

    const updateGroups = (newGroups: G[]) => {
      setGroups(newGroups);
    };

    const addItem = (id: string, groupIds: string[], description?: string) => {
      // Add the item
      const newItem = { id, description: description || '' } as T;
      const newItems = [...items, newItem];

      // If groupIds is provided, add the item to those groups
      const updatedGroups = groups.map(group => {
        if (groupIds.includes(group.id)) {
          const allMembers = [...group.members, id];
          // Sort members based on updated items order
          const sortedMembers = newItems
            .filter(item => allMembers.includes(item.id))
            .map(item => item.id);
          return {
            ...group,
            members: sortedMembers
          };
        }
        return group;
      });
      updateItems(newItems);
      updateGroups(updatedGroups);
    };

    const addGroup = (id: string, memberIds: string[], description?: string) => {
      // Sort members based on items order
      const sortedMembers = items
        .filter(item => memberIds.includes(item.id))
        .map(item => item.id);

      const newGroup = { id, members: sortedMembers, description: description || '' } as G;
      const newGroups = [...groups, newGroup];
      updateGroups(newGroups);
    };

    const updateItem = (oldId: string, newId: string, groupIds?: string[], description?: string) => {
      // First update the item's ID and description
      const updatedItems = items.map(item => 
        item.id === oldId 
          ? { ...item, id: newId, description: description !== undefined ? description : item.description }
          : item
      );

      // Always update group memberships to reflect the new ID
      const updatedGroups = groups.map(group => {
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

        return {
          ...group,
          members: sortedMembers
        };
      });
      updateItems(updatedItems);
      updateGroups(updatedGroups);
    };

    const updateGroup = (oldId: string, newId: string, members?: string[], description?: string) => {
      const group = groups.find(g => g.id === oldId);
      if (!group) {
        console.error(`Group with ID ${oldId} not found. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }

      // Sort members based on items order
      const sortedMembers = members
        ? items
            .filter(item => members.includes(item.id))
            .map(item => item.id)
        : group.members;

      const newGroups = groups.map(g => 
        g.id === oldId 
          ? { ...g, id: newId, members: sortedMembers, description: description !== undefined ? description : g.description }
          : g
      );
      updateGroups(newGroups);
    };

    const deleteItem = (id: string) => {
      const newItems = items.filter(item => item.id !== id);
      const newGroups = groups.map(group => ({
        ...group,
        members: group.members.filter(memberId => memberId !== id)
      }));
      updateItems(newItems);
      updateGroups(newGroups);
    };

    const deleteGroup = (id: string) => {
      const newGroups = groups.filter(g => g.id !== id);
      updateGroups(newGroups);
    };

    const removeItemFromGroup = (itemId: string, groupId: string) => {
      const newGroups = groups.map(group =>
        group.id === groupId
          ? { ...group, members: group.members.filter(id => id !== itemId) }
          : group
      );
      updateGroups(newGroups);
    };

    const reorderItems = (reorderedItems: T[]) => {
      // Update the items
      updateItems(reorderedItems);

      // Sort group members based on items order
      const updatedGroups = groups.map(group => ({
        ...group,
        members: reorderedItems
          .filter(item => group.members.includes(item.id))
          .map(item => item.id)
      }));

      updateGroups(updatedGroups);
    };

    const value = {
      items,
      groups,
      updateItems,
      updateGroups,
      addItem,
      addGroup,
      updateItem,
      updateGroup,
      deleteItem,
      deleteGroup,
      removeItemFromGroup,
      reorderItems,
      createNewState,
    };

    return (
      <ManagementContext.Provider value={value}>
        {children}
      </ManagementContext.Provider>
    );
  }

  function useManagement() {
    const context = useContext(ManagementContext);
    if (context === undefined) {
      throw new Error('useManagement must be used within a ManagementProvider');
    }
    return context;
  }

  return { ManagementProvider, useManagement };
}
