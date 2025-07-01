// React hook for scheduling data management with localStorage
'use client';

import { useState, useEffect } from 'react';
import { Item, Group, DateRange, ShiftTypeRequirementsPreference } from '@/types/scheduling';
import { ItemGroupEditorPageData } from '@/components/ItemGroupEditorPage';

export interface SchedulingState {
  dateRange: DateRange;
  dates: { items: Item[]; groups: Group[] };
  people: { items: Item[]; groups: Group[] };
  shiftTypes: { items: Item[]; groups: Group[] };
  shiftTypeRequirements: ShiftTypeRequirementsPreference[];
}

interface HistoryState {
  state: SchedulingState;
  history: SchedulingState[];
  currentHistoryIndex: number;
}

const STORAGE_KEY = 'nurse-scheduling-data';
const MAX_HISTORY_SIZE = 50;

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
    shiftTypes: createDefaultShiftTypes(),
    shiftTypeRequirements: []
  };
}

function createDefaultHistoryState(): HistoryState {
  const defaultState = createDefaultState();
  return {
    state: defaultState,
    history: [defaultState],
    currentHistoryIndex: 0
  };
}

function loadStateFromStorage(): HistoryState {
  if (typeof window === 'undefined') return createDefaultHistoryState();

  try {
    const stored = localStorage.getItem(STORAGE_KEY);

    if (!stored) return createDefaultHistoryState();

    const parsedHistoryState = JSON.parse(stored) as HistoryState;

    // Recompute date items for current state if date range exists
    const dateItems = (parsedHistoryState.state.dateRange?.startDate && parsedHistoryState.state.dateRange?.endDate)
      ? generateDateItems(parsedHistoryState.state.dateRange.startDate, parsedHistoryState.state.dateRange.endDate)
      : [];

    const currentState = {
      ...parsedHistoryState.state,
      dates: {
        items: dateItems,
        groups: parsedHistoryState.state.dates?.groups || []
      }
    };

    return {
      state: currentState,
      history: parsedHistoryState.history,
      currentHistoryIndex: Math.min(parsedHistoryState.currentHistoryIndex || 0, parsedHistoryState.history.length - 1)
    };
  } catch (error) {
    console.error('Failed to load data from localStorage:', error);
    return createDefaultHistoryState();
  }
}

function saveStateToStorage(historyState: HistoryState): void {
  if (typeof window === 'undefined') return;

  try {
    // Store the complete history state, but exclude computed date items
    const historyStateToStore = {
      state: {
        ...historyState.state,
        dates: { groups: historyState.state.dates.groups } // Don't store computed items
      },
      history: historyState.history.map(state => ({
        ...state,
        dates: { groups: state.dates.groups } // Don't store computed items in history
      })),
      currentHistoryIndex: historyState.currentHistoryIndex
    };

    localStorage.setItem(STORAGE_KEY, JSON.stringify(historyStateToStore));
  } catch (error) {
    console.error('Failed to save data to localStorage:', error);
  }
}

function addToHistory(currentHistoryState: HistoryState, newState: SchedulingState): HistoryState {
  // Remove any future history if we're not at the end
  const trimmedHistory = currentHistoryState.history.slice(0, currentHistoryState.currentHistoryIndex + 1);

  // Add new state
  const newHistory = [...trimmedHistory, newState];

  // Limit history size
  const limitedHistory = newHistory.length > MAX_HISTORY_SIZE
    ? newHistory.slice(-MAX_HISTORY_SIZE)
    : newHistory;

  const newIndex = limitedHistory.length - 1;

  return {
    state: newState,
    history: limitedHistory,
    currentHistoryIndex: newIndex
  };
}

// Main hook for external use
export function useSchedulingData() {
  const [historyState, setHistoryState] = useState<HistoryState>(createDefaultHistoryState);

  // Load from localStorage on mount
  useEffect(() => {
    const storedHistoryState = loadStateFromStorage();
    setHistoryState(storedHistoryState);
  }, []);

  // Global keyboard shortcuts for undo/redo
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Check if Ctrl (or Cmd on Mac) is pressed
      const isCtrlOrCmd = event.ctrlKey || event.metaKey;

      if (!isCtrlOrCmd || event.altKey || event.shiftKey) return;

      // Undo: Ctrl+Z
      if (event.key === 'z') {
        event.preventDefault();
        undo();
        return;
      }

      // Redo: Ctrl+Y
      if (event.key === 'y') {
        event.preventDefault();
        redo();
        return;
      }
    };

    // Add event listener to document
    document.addEventListener('keydown', handleKeyDown);

    // Cleanup function to remove event listener
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []); // Empty dependency array since undo/redo functions are stable

  // Generic update function that handles both state update and storage
  const updateState = (updater: (prevState: SchedulingState) => SchedulingState) => {
    setHistoryState(prevHistoryState => {
      const newState = updater(prevHistoryState.state);
      const newHistoryState = addToHistory(prevHistoryState, newState);
      saveStateToStorage(newHistoryState);
      return newHistoryState;
    });
  };

  // Base function to navigate to a specific history index
  const moveHistoryIndex = (delta: number) => {
    setHistoryState(prevHistoryState => {
      const targetIndex = prevHistoryState.currentHistoryIndex + delta;

      // Validate target index bounds
      if (targetIndex < 0 || targetIndex >= prevHistoryState.history.length || targetIndex === prevHistoryState.currentHistoryIndex) {
        return prevHistoryState;
      }

      const targetState = prevHistoryState.history[targetIndex];

      // Recompute date items for the target state
      const dateItems = (targetState.dateRange?.startDate && targetState.dateRange?.endDate)
        ? generateDateItems(targetState.dateRange.startDate, targetState.dateRange.endDate)
        : [];

      const restoredState = {
        ...targetState,
        dates: {
          ...targetState.dates,
          items: dateItems
        }
      };

      const newHistoryState = {
        ...prevHistoryState,
        state: restoredState,
        currentHistoryIndex: targetIndex
      };

      saveStateToStorage(newHistoryState);
      return newHistoryState;
    });
  };

  // Undo function
  const undo = () => {
    moveHistoryIndex(-1);
  };

  // Redo function
  const redo = () => {
    moveHistoryIndex(1);
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

  const updateShiftTypeRequirements = (shiftTypeRequirements: ShiftTypeRequirementsPreference[]) => {
    updateState(prevState => ({
      ...prevState,
      shiftTypeRequirements
    }));
  };

  // Reset to defaults
  const createNewState = () => {
    const newState = createDefaultState();
    const newHistoryState = {
      state: newState,
      history: [newState],
      currentHistoryIndex: 0
    };
    setHistoryState(newHistoryState);
    saveStateToStorage(newHistoryState);
  };

  return {
    dateRange: historyState.state.dateRange,
    updateDateRange,
    dateData: historyState.state.dates,
    updateDateData,
    peopleData: historyState.state.people,
    updatePeopleData,
    shiftTypeData: historyState.state.shiftTypes,
    updateShiftTypeData,
    shiftTypeRequirements: historyState.state.shiftTypeRequirements,
    updateShiftTypeRequirements,
    createNewState,
    undo,
    redo,
  };
}
