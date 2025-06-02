// React hook for scheduling data management with localStorage
'use client';

import { useState, useEffect } from 'react';
import { Item, Group, DateRange } from '@/types/scheduling';
import { ItemGroupEditorPageData } from '@/components/ItemGroupEditorPage';

export interface SchedulingState {
  dateRange: DateRange;
  dates: { items: Item[]; groups: Group[] };
  people: { items: Item[]; groups: Group[] };
  shiftTypes: { items: Item[]; groups: Group[] };
}

const STORAGE_KEY = 'nurse-scheduling-state';

// Helper function to generate date items from a date range
function generateDateItems(startDate: string, endDate: string): Item[] {
  const dates: Item[] = [];
  const start = new Date(startDate);
  const end = new Date(endDate);

  // Determine ID format based on date range scope
  const sameYear = start.getFullYear() === end.getFullYear();
  const sameMonth = sameYear && start.getMonth() === end.getMonth();

  for (let date = new Date(start); date <= end; date.setDate(date.getDate() + 1)) {
    const dateStr = date.toISOString().split('T')[0];
    const dayName = date.toLocaleDateString('en-US', { weekday: 'long' });
    const formattedDate = date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });

    // Generate ID based on date range scope
    let id: string;
    if (sameMonth) {
      id = dateStr.slice(-2); // DD
    } else if (sameYear) {
      id = dateStr.slice(5); // MM-DD
    } else {
      id = dateStr; // YYYY-MM-DD
    }

    dates.push({
      id,
      description: `${dayName}, ${formattedDate}`
    });
  }

  return dates;
}

function createDefaultPeople() {
  return {
    items: Array.from({ length: 10 }, (_, index) => ({
      id: `Person ${index + 1}`,
      description: ''
    })),
    groups: [
      { id: 'Group 1', members: ['Person 1', 'Person 2'], description: '' },
      { id: 'Group 2', members: ['Person 2', 'Person 3', 'Person 4'], description: '' },
      { id: 'Group 3', members: ['Person 3', 'Person 4', 'Person 5', 'Person 6'], description: '' },
      { id: 'Group 4', members: ['Person 4', 'Person 5', 'Person 6', 'Person 7', 'Person 8'], description: '' },
      { id: 'Group 5', members: ['Person 5', 'Person 6', 'Person 7', 'Person 8', 'Person 9', 'Person 10'], description: '' },
    ]
  };
}

function createDefaultShiftTypes() {
  return {
    items: [
      { id: 'D', description: 'Day (All Levels)' },
      { id: 'D+', description: 'Day (Senior Only)' },
      { id: 'E', description: 'Evening (All Levels)' },
      { id: 'E+', description: 'Evening (Senior Only)' },
      { id: 'N', description: 'Night (All Levels)' },
      { id: 'N+', description: 'Night (Senior Only)' },
      { id: 'A', description: 'Admin (All Levels)' },
      { id: 'A+', description: 'Admin (Senior Only)' },
      { id: 'A-', description: 'Admin (Assistant Only)' },
    ],
    groups: [
      { id: 'Day', members: ['D', 'D+'], description: 'All day shift types' },
      { id: 'Evening', members: ['E', 'E+'], description: 'All evening shift types' },
      { id: 'Night', members: ['N', 'N+'], description: 'All night shift types' },
      { id: 'Administrative', members: ['A', 'A+', 'A-'], description: 'All administrative shift types' },
    ]
  };
}

function createDefaultState(): SchedulingState {
  return {
    dateRange: { startDate: undefined, endDate: undefined },
    dates: { items: [], groups: [] },
    people: createDefaultPeople(),
    shiftTypes: createDefaultShiftTypes()
  };
}

function loadStateFromStorage(): SchedulingState {
  if (typeof window === 'undefined') return createDefaultState();

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return createDefaultState();

    const parsedState = JSON.parse(stored);

    // Recompute date items if date range exists
    const dateItems = (parsedState.dateRange?.startDate && parsedState.dateRange?.endDate)
      ? generateDateItems(parsedState.dateRange.startDate, parsedState.dateRange.endDate)
      : [];

    return {
      ...parsedState,
      dates: {
        items: dateItems,
        groups: parsedState.dates?.groups || []
      }
    };
  } catch (error) {
    console.error('Failed to load data from localStorage:', error);
    return createDefaultState();
  }
}

function saveStateToStorage(state: SchedulingState): void {
  if (typeof window === 'undefined') return;

  try {
    // Only store what's necessary (exclude computed date items)
    const stateToStore = {
      ...state,
      dates: { groups: state.dates.groups } // Don't store computed items
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stateToStore));
  } catch (error) {
    console.error('Failed to save data to localStorage:', error);
  }
}

// Main hook for external use
export function useSchedulingData() {
  const [state, setState] = useState<SchedulingState>(createDefaultState);

  // Load from localStorage on mount
  useEffect(() => {
    const storedState = loadStateFromStorage();
    setState(storedState);
  }, []);

  // Generic update function that handles both state update and storage
  const updateState = (updater: (prevState: SchedulingState) => SchedulingState) => {
    setState(prevState => {
      const newState = updater(prevState);
      saveStateToStorage(newState);
      return newState;
    });
  };

  const updateDateRange = (dateRange: DateRange) => {
    updateState(prevState => {
      const dateItems = (dateRange.startDate && dateRange.endDate)
        ? generateDateItems(dateRange.startDate, dateRange.endDate)
        : [];

      return {
        ...prevState,
        dateRange,
        dates: {
          ...prevState.dates,
          items: dateItems
        }
      };
    });
  };

  const updatePeopleData = (peopleData: ItemGroupEditorPageData) => {
    updateState(prevState => ({
      ...prevState,
      people: peopleData
    }));
  };

  const updateShiftTypeData = (shiftTypeData: ItemGroupEditorPageData) => {
    updateState(prevState => ({
      ...prevState,
      shiftTypes: shiftTypeData
    }));
  };

  const updateDateData = (dateData: ItemGroupEditorPageData) => {
    updateState(prevState => ({
      ...prevState,
      dates: {
        items: prevState.dates.items, // Keep computed items
        groups: dateData.groups
      }
    }));
  };

  // Reset to defaults
  const createNewState = () => {
    const newState = createDefaultState();
    setState(newState);
    saveStateToStorage(newState);
  };

  return {
    dateRange: state.dateRange,
    updateDateRange,
    dateData: state.dates,
    updateDateData,
    peopleData: state.people,
    updatePeopleData,
    shiftTypeData: state.shiftTypes,
    updateShiftTypeData,
    createNewState,
  };
}
