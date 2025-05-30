'use client';

import { createContext, useContext, ReactNode } from 'react';
import { createManagementContext } from './ManagementContext';
import { Item, Group } from '@/types/management';

// People interfaces extending base types
export interface Person extends Item {}

export interface PeopleGroup extends Group {}

// ShiftType interfaces extending base types  
export interface ShiftType extends Item {}

export interface ShiftTypeGroup extends Group {}

// Create individual management contexts
const { 
  ManagementProvider: PeopleManagementProvider, 
  useManagement: usePeopleManagement 
} = createManagementContext<Person, PeopleGroup>({
  storageKey: 'nurse-scheduling-people',
  createDefaultState: () => {
    const items = Array.from({ length: 10 }, (_, index) => ({
      id: `Person ${index + 1}`,
      description: `Staff member #${index + 1}`
    }));
    const groups = [
      { id: 'Group 1', members: ['Person 1', 'Person 2'], description: '' },
      { id: 'Group 2', members: ['Person 2', 'Person 3', 'Person 4'], description: '' },
      { id: 'Group 3', members: ['Person 3', 'Person 4', 'Person 5', 'Person 6'], description: '' },
      { id: 'Group 4', members: ['Person 4', 'Person 5', 'Person 6', 'Person 7', 'Person 8'], description: '' },
      { id: 'Group 5', members: ['Person 5', 'Person 6', 'Person 7', 'Person 8', 'Person 9', 'Person 10'], description: '' },
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
      { id: 'Day (All Levels)', description: 'Day shift for all skill levels' },
      { id: 'Day (Senior Only)', description: 'Day shift requiring senior staff expertise' },
      { id: 'Evening (All Levels)', description: 'Evening shift for all skill levels' }, 
      { id: 'Evening (Senior Only)', description: 'Evening shift requiring senior staff expertise' },
      { id: 'Night (All Levels)', description: 'Night shift for all skill levels' },
      { id: 'Night (Senior Only)', description: 'Night shift requiring senior staff expertise' },
      { id: 'Admin (All Levels)', description: 'Administrative tasks for all levels' },
      { id: 'Admin (Senior Only)', description: 'Administrative tasks requiring senior expertise' },
      { id: 'Admin (Assistant Only)', description: 'Administrative tasks suitable for assistants' },
    ];
    const groups = [
      { id: 'Day', members: ['Day (All Levels)', 'Day (Senior Only)'], description: 'All day shift types' },
      { id: 'Evening', members: ['Evening (All Levels)', 'Evening (Senior Only)'], description: 'All evening shift types' },
      { id: 'Night', members: ['Night (All Levels)', 'Night (Senior Only)'], description: 'All night shift types' },
      { id: 'Administrative', members: ['Admin (All Levels)', 'Admin (Senior Only)', 'Admin (Assistant Only)'], description: 'All administrative shift types' },
    ];
    return { items, groups };
  }
});

// Combined context type
interface SchedulingContextType {
  // People management
  people: Person[];
  peopleGroups: PeopleGroup[];
  reorderPeople: (people: Person[]) => void;
  updatePeopleGroups: (groups: PeopleGroup[]) => void;
  addPerson: (id: string, groupIds: string[], description?: string) => void;
  addPeopleGroup: (id: string, memberIds: string[], description?: string) => void;
  updatePerson: (oldId: string, newId: string, groupIds?: string[], description?: string) => void;
  updatePeopleGroup: (oldId: string, newId: string, members?: string[], description?: string) => void;
  deletePerson: (id: string) => void;
  deletePeopleGroup: (id: string) => void;
  removePersonFromGroup: (personId: string, groupId: string) => void;
  
  // Shift type management
  shiftTypes: ShiftType[];
  shiftTypeGroups: ShiftTypeGroup[];
  reorderShiftTypes: (shiftTypes: ShiftType[]) => void;
  updateShiftTypeGroups: (groups: ShiftTypeGroup[]) => void;
  addShiftType: (id: string, groupIds: string[], description?: string) => void;
  addShiftTypeGroup: (id: string, memberIds: string[], description?: string) => void;
  updateShiftType: (oldId: string, newId: string, groupIds?: string[], description?: string) => void;
  updateShiftTypeGroup: (oldId: string, newId: string, members?: string[], description?: string) => void;
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
    reorderPeople: peopleContext.reorderItems,
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
    reorderShiftTypes: shiftTypeContext.reorderItems,
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
