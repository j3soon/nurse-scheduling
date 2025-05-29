'use client';

import { createContext, useContext, ReactNode } from 'react';
import { createManagementContext } from './ManagementContext';

// People interfaces
export interface Person {
  id: string;
}

export interface PeopleGroup {
  id: string;
  members: string[]; // Array of person IDs
}

// ShiftType interfaces
export interface ShiftType {
  id: string;
}

export interface ShiftTypeGroup {
  id: string;
  members: string[]; // Array of shift type IDs
}

// Create individual management contexts
const { 
  ManagementProvider: PeopleManagementProvider, 
  useManagement: usePeopleManagement 
} = createManagementContext<Person, PeopleGroup>({
  storageKey: 'nurse-scheduling-people',
  createDefaultState: () => {
    const items = Array.from({ length: 10 }, (_, index) => ({
      id: `Person ${index + 1}`
    }));
    const groups = [
      { id: 'Group 1', members: ['Person 1', 'Person 2'] },
      { id: 'Group 2', members: ['Person 2', 'Person 3', 'Person 4'] },
      { id: 'Group 3', members: ['Person 3', 'Person 4', 'Person 5', 'Person 6'] },
      { id: 'Group 4', members: ['Person 4', 'Person 5', 'Person 6', 'Person 7', 'Person 8'] },
      { id: 'Group 5', members: ['Person 5', 'Person 6', 'Person 7', 'Person 8', 'Person 9', 'Person 10'] },
    ];
    return { items, groups };
  }
});

const { 
  ManagementProvider: ShiftTypeManagementProvider, 
  useManagement: useShiftTypeManagement 
} = createManagementContext<ShiftType, ShiftTypeGroup>({
  storageKey: 'nurse-scheduling-shift-types',
  createDefaultState: () => {
    const items = [
      { id: 'Day - All Levels' },
      { id: 'Day - Senior Only' },
      { id: 'Evening - All Levels' }, 
      { id: 'Evening - Senior Only' },
      { id: 'Night - All Levels' },
      { id: 'Night - Senior Only' },
      { id: 'Admin - All Levels' },
      { id: 'Admin - Senior Only' },
      { id: 'Admin - Assistant Only' },
    ];
    const groups = [
      { id: 'Day', members: ['Day - All Levels', 'Day - Senior Only'] },
      { id: 'Evening', members: ['Evening - All Levels', 'Evening - Senior Only'] },
      { id: 'Night', members: ['Night - All Levels', 'Night - Senior Only'] },
      { id: 'Administrative', members: ['Admin - All Levels', 'Admin - Senior Only', 'Admin - Assistant Only'] },
    ];
    return { items, groups };
  }
});

// Combined context type
interface SchedulingContextType {
  // People management
  people: Person[];
  peopleGroups: PeopleGroup[];
  updatePeople: (people: Person[]) => void;
  updatePeopleGroups: (groups: PeopleGroup[]) => void;
  addPerson: (id: string, groupIds: string[]) => void;
  addPeopleGroup: (id: string, memberIds: string[]) => void;
  updatePerson: (oldId: string, newId: string, groupIds?: string[]) => void;
  updatePeopleGroup: (oldId: string, newId: string, members?: string[]) => void;
  deletePerson: (id: string) => void;
  deletePeopleGroup: (id: string) => void;
  removePersonFromGroup: (personId: string, groupId: string) => void;
  
  // Shift type management
  shiftTypes: ShiftType[];
  shiftTypeGroups: ShiftTypeGroup[];
  updateShiftTypes: (shiftTypes: ShiftType[]) => void;
  updateShiftTypeGroups: (groups: ShiftTypeGroup[]) => void;
  addShiftType: (id: string, groupIds: string[]) => void;
  addShiftTypeGroup: (id: string, memberIds: string[]) => void;
  updateShiftType: (oldId: string, newId: string, groupIds?: string[]) => void;
  updateShiftTypeGroup: (oldId: string, newId: string, members?: string[]) => void;
  deleteShiftType: (id: string) => void;
  deleteShiftTypeGroup: (id: string) => void;
  removeShiftTypeFromGroup: (shiftTypeId: string, groupId: string) => void;
  
  // Global operations
  createNewState: () => void;
  createNewPeopleState: () => void;
  createNewShiftTypeState: () => void;
}

const SchedulingContext = createContext<SchedulingContextType | undefined>(undefined);

export function SchedulingProvider({ children }: { children: ReactNode }) {
  return (
    <PeopleManagementProvider>
      <ShiftTypeManagementProvider>
        <SchedulingInnerProvider>
          {children}
        </SchedulingInnerProvider>
      </ShiftTypeManagementProvider>
    </PeopleManagementProvider>
  );
}

function SchedulingInnerProvider({ children }: { children: ReactNode }) {
  const peopleContext = usePeopleManagement();
  const shiftTypeContext = useShiftTypeManagement();

  const value: SchedulingContextType = {
    // People management - delegate to people context
    people: peopleContext.items,
    peopleGroups: peopleContext.groups,
    updatePeople: peopleContext.updateItems,
    updatePeopleGroups: peopleContext.updateGroups,
    addPerson: peopleContext.addItem,
    addPeopleGroup: peopleContext.addGroup,
    updatePerson: peopleContext.updateItem,
    updatePeopleGroup: peopleContext.updateGroup,
    deletePerson: peopleContext.deleteItem,
    deletePeopleGroup: peopleContext.deleteGroup,
    removePersonFromGroup: peopleContext.removeItemFromGroup,
    
    // Shift type management - delegate to shift type context
    shiftTypes: shiftTypeContext.items,
    shiftTypeGroups: shiftTypeContext.groups,
    updateShiftTypes: shiftTypeContext.updateItems,
    updateShiftTypeGroups: shiftTypeContext.updateGroups,
    addShiftType: shiftTypeContext.addItem,
    addShiftTypeGroup: shiftTypeContext.addGroup,
    updateShiftType: shiftTypeContext.updateItem,
    updateShiftTypeGroup: shiftTypeContext.updateGroup,
    deleteShiftType: shiftTypeContext.deleteItem,
    deleteShiftTypeGroup: shiftTypeContext.deleteGroup,
    removeShiftTypeFromGroup: shiftTypeContext.removeItemFromGroup,
    
    // Global operations
    createNewState: () => {
      peopleContext.createNewState();
      shiftTypeContext.createNewState();
    },
    createNewPeopleState: peopleContext.createNewState,
    createNewShiftTypeState: shiftTypeContext.createNewState
  };

  return (
    <SchedulingContext.Provider value={value}>
      {children}
    </SchedulingContext.Provider>
  );
}

export function useScheduling() {
  const context = useContext(SchedulingContext);
  if (context === undefined) {
    throw new Error('useScheduling must be used within a SchedulingProvider');
  }
  return context;
}
