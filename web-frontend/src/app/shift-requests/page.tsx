/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2025 Johnson Sun
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

// The shift requests management page for Tab "5. Shift Requests"
'use client';

import { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { FiHelpCircle, FiEdit2, FiAlertCircle, FiUpload, FiTrash2 } from 'react-icons/fi';
import UploadButton from '@/components/UploadButton';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { ShiftRequestPreference, SHIFT_REQUEST, Item } from '@/types/scheduling';
import ShiftPreferenceEditor from '@/components/ShiftPreferenceEditor';
import ToggleButton from '@/components/ToggleButton';
import { CheckboxList } from '@/components/CheckboxList';
import { getWeightDisplayLabel, isValidWeightValue, parseWeightValue } from '@/utils/numberParsing';
import WeightInput from '@/components/WeightInput';
import { ERROR_SHOULD_NOT_HAPPEN } from '@/constants/errors';
import { dateStrToDate } from '@/utils/dateParsing';
import { DataType } from '@/types/scheduling';

export default function ShiftRequestsPage() {
  const {
    dateData,
    peopleData,
    shiftTypeData,
    getPreferencesByType,
    updatePreferencesByType,
    addPersonHistory,
    updatePersonHistory,
    reorderItems,
  } = useSchedulingData();

  // Get shift request preferences from the flattened preferences
  const shiftRequestPreferences = getPreferencesByType<ShiftRequestPreference>(SHIFT_REQUEST);
  const updateShiftRequestPreferences = (newPrefs: ShiftRequestPreference[]) =>
    updatePreferencesByType(SHIFT_REQUEST, newPrefs);

  const [showInstructions, setShowInstructions] = useState(false);
  const [isAddMode, setIsAddMode] = useState(false);
  const [addFormData, setAddFormData] = useState<{
    shiftTypes: string[];
    weight: number | string;
  }>({
    shiftTypes: [],
    weight: 0,
  });
  const [errors, setErrors] = useState<{[key: string]: string}>({});
  const [editorState, setEditorState] = useState<{
    isOpen: boolean;
    personId: string;
    dateId: string;
  }>({
    isOpen: false,
    personId: '',
    dateId: '',
  });

  const [historyEditState, setHistoryEditState] = useState<{
    isOpen: boolean;
    personId: string;
    historyIndex: number;
  }>({
    isOpen: false,
    personId: '',
    historyIndex: -1,
  });

  // Sticky header
  const [showStickyHeader, setShowStickyHeader] = useState(false);
  const [columnWidths, setColumnWidths] = useState<number[]>([]);
  const [stickyHeaderLeft, setStickyHeaderLeft] = useState(0);
  const tableRef = useRef<HTMLTableElement>(null);
  const mainScrollContainerRef = useRef<HTMLDivElement>(null);
  const stickyScrollContainerRef = useRef<HTMLDivElement>(null);

  // Sticky Quick Add Preference
  const [showStickyQuickAdd, setShowStickyQuickAdd] = useState(false);
  const [quickAddHeight, setQuickAddHeight] = useState(0);
  const quickAddRef = useRef<HTMLDivElement>(null);
  const stickyQuickAddRef = useRef<HTMLDivElement>(null);
  // TODO(perf): The multi-select drag feature is now lagging, unsure why.

  enum SelectedCellType {
    PREFERENCE,
    HISTORY,
  }

  const isMultiSelectDragRef = useRef(false);

  // Add event listener for mouse up outside the component to end drag selection
  useEffect(() => {
    const handleGlobalMouseUp = () => {
      // End multi-select drag
      isMultiSelectDragRef.current = false;
      document.body.style.userSelect = '';
    };

    window.addEventListener('mouseup', handleGlobalMouseUp);
    // Cleanup event listener
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp);
      document.body.style.userSelect = '';
    };
  }, []);

  // Function to sync scroll position between main and sticky containers
  const syncScrollPosition = () => {
    if (mainScrollContainerRef.current && stickyScrollContainerRef.current && showStickyHeader) {
      stickyScrollContainerRef.current.scrollLeft = mainScrollContainerRef.current.scrollLeft;
    }
    if (mainScrollContainerRef.current && tableRef.current && showStickyHeader) {
      const tableRect = tableRef.current.getBoundingClientRect();
      setStickyHeaderLeft(tableRect.left + mainScrollContainerRef.current.scrollLeft);
    }
  };

  // Function to measure and sync column widths
  const syncColumnWidths = () => {
    if (tableRef.current) {
      const headerCells = tableRef.current.querySelectorAll('thead th');
      const widths = Array.from(headerCells).map(cell => cell.getBoundingClientRect().width);
      setColumnWidths(widths);
    }
  };

  // Add scroll event listener to detect when table header and quick add should be sticky
  useEffect(() => {
    const handleScroll = () => {
      // Compute required data check locally to avoid dependency issues
      const hasRequiredDataLocal = (dateData.range?.startDate && dateData.range?.endDate && dateData.items.length > 0 && peopleData.items.length > 0 && (shiftTypeData.items.length > 0 || shiftTypeData.groups.length > 0));

      if (tableRef.current && hasRequiredDataLocal) {
        const tableRect = tableRef.current.getBoundingClientRect();

        // Determine if sticky elements should show based on table position
        // Show sticky header when the table header is above the viewport but table bottom is still visible
        const shouldShowSticky = tableRect.top < 0 && tableRect.bottom > 0;

        // Quick Add sticky follows the same visibility as table header when in add mode
        if (isAddMode) {
          const quickAddRect = quickAddRef.current?.getBoundingClientRect();
          const shouldShowStickyQuickAdd = !!(shouldShowSticky || quickAddRect && quickAddRect.bottom < 0);
          setShowStickyQuickAdd(shouldShowStickyQuickAdd);

          // Measure height of sticky quick add section
          if (shouldShowStickyQuickAdd && stickyQuickAddRef.current) {
            setQuickAddHeight(stickyQuickAddRef.current.offsetHeight);
          } else {
            setQuickAddHeight(0);
          }

          // Adjust table header position for Quick Add height
          const topThreshold = shouldShowStickyQuickAdd ? (stickyQuickAddRef.current?.offsetHeight || 0) : 0;
          const shouldShowStickyHeader = tableRect.top < topThreshold && tableRect.bottom > topThreshold;
          setShowStickyHeader(shouldShowStickyHeader);
        } else {
          // Not in add mode - hide Quick Add and show normal table header
          setShowStickyQuickAdd(false);
          setQuickAddHeight(0);
          setShowStickyHeader(shouldShowSticky);
        }
      } else {
        // No table or required data - hide all sticky elements
        setShowStickyQuickAdd(false);
        setQuickAddHeight(0);
        setShowStickyHeader(false);
      }
    };

    window.addEventListener('scroll', handleScroll);
    // Cleanup event listener
    return () => {
      window.removeEventListener('scroll', handleScroll);
    };
  }, [showStickyHeader, showStickyQuickAdd, isAddMode, quickAddHeight, dateData, peopleData, shiftTypeData]);

  // Add resize observer to sync column widths when table layout changes
  useEffect(() => {
    if (!tableRef.current) return;

    const resizeObserver = new ResizeObserver(() => {
      if (showStickyHeader) {
        syncColumnWidths();
      }
    });

    resizeObserver.observe(tableRef.current);

    return () => {
      resizeObserver.disconnect();
    };
  }, [showStickyHeader]);

  // Add window resize listener to update sticky header position
  useEffect(() => {
    const handleResize = () => {
      syncScrollPosition();
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [showStickyHeader]);

  // Horizontal scroll synchronization with real-time updates
  useEffect(() => {
    const handleMainScroll = () => {
      syncScrollPosition();
    };

    const handleStickyScroll = () => {
      // Always reset sticky header to match main table - no independent scrolling allowed
      syncScrollPosition();
    };

    const mainContainer = mainScrollContainerRef.current;
    const stickyContainer = stickyScrollContainerRef.current;

    if (mainContainer) {
      mainContainer.addEventListener('scroll', handleMainScroll, { passive: true });
    }

    if (stickyContainer && showStickyHeader) {
      stickyContainer.addEventListener('scroll', handleStickyScroll, { passive: true });
    }

    // Always sync scroll position when sticky header visibility changes or DOM updates
    syncScrollPosition();

    return () => {
      if (mainContainer) {
        mainContainer.removeEventListener('scroll', handleMainScroll);
      }
      if (stickyContainer) {
        stickyContainer.removeEventListener('scroll', handleStickyScroll);
      }
    };
  }, [showStickyHeader]);

  // Sync scroll position after page refresh when user scrolls down and table has horizontal scroll
  useEffect(() => {
    syncScrollPosition();
  }, [columnWidths]);

  const resetForm = () => {
    setAddFormData({
      shiftTypes: [],
      weight: 0,
    });
    setErrors({});
  };

  const handleStartAdd = () => {
    resetForm();
    setIsAddMode(true);
  };

  const handleCancel = () => {
    setIsAddMode(false);
    resetForm();
  };

  const validateWeight = (): boolean => {
    const newErrors: {[key: string]: string} = {};

    if (!isValidWeightValue(addFormData.weight)) {
      newErrors.weight = 'Weight must be a valid number, Infinity, or -Infinity';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const validateShiftRequestCsvData = (csvData: string[][]): {
    isValid: boolean;
    error?: string;
    validatedData?: { personId: string; dateId: string; shiftType: string }[];
  } => {
    // Validate weight is valid
    if (!validateWeight()) {
      return { isValid: false, error: 'Weight must be a valid number, Infinity, or -Infinity.' };
    }

    // Validate weight is not zero
    if (addFormData.weight === 0) {
      return { isValid: false, error: 'Weight must be a non-zero number.' };
    }

    // Validate CSV shape - should have people count + 0 rows (header + people rows)
    const expectedPeopleCount = peopleData.items.length;
    const expectedDateCount = dateData.items.length;

    if (csvData.length !== expectedPeopleCount + 0) {
      return { isValid: false, error: `CSV should have ${expectedPeopleCount + 0} rows (1 header + ${expectedPeopleCount} people), but has ${csvData.length} rows.` };
    }

    // Create a map of valid person IDs for quick lookup
    const validPersonIds = new Set(peopleData.items.map(person => person.id));
    const personRowMap = new Map<string, number>(); // Map person ID to row index

    // Validate each row has correct number of columns (date count)
    // Validate that the first column contains a valid person ID (allow out-of-order)
    for (let i = 0; i < csvData.length; i++) {
      if (csvData[i].length !== expectedDateCount + 1) {
        return { isValid: false, error: `Row ${i + 1} should have ${expectedDateCount + 1} columns (dates), but has ${csvData[i].length} columns.` };
      }

      const personId = csvData[i][0].trim();
      if (!validPersonIds.has(personId)) {
        const validPersonList = Array.from(validPersonIds).join(', ');
        return { isValid: false, error: `Row ${i + 1} has invalid person ID "${personId}". Valid person IDs: ${validPersonList}` };
      }

      // Check for duplicate person IDs in the CSV
      if (personRowMap.has(personId)) {
        return { isValid: false, error: `Duplicate person ID "${personId}" found at row ${i + 1}. Person was already seen at row ${personRowMap.get(personId)! + 1}.` };
      }

      personRowMap.set(personId, i);
    }

    // Validate that all expected people are present in the CSV
    for (const person of peopleData.items) {
      if (!personRowMap.has(person.id)) {
        return { isValid: false, error: `Missing person "${person.id}" in CSV data. All people must be included.` };
      }
    }

    // Get all valid shift type IDs
    const validShiftTypes = getAllShiftTypes().map(st => st.id);
    const validatedData: { personId: string; dateId: string; shiftType: string }[] = [];

    // Validate shift types in data cells
    for (let r = 0; r < csvData.length; r++) {
      const personId = csvData[r][0].trim(); // Get person ID from first column

      for (let c = 1; c < csvData[r].length; c++) {
        const cellValue = csvData[r][c].trim();
        const dateId = dateData.items[c - 1].id;

        // Skip empty cells
        if (!cellValue) continue;

        // Validate shift type
        if (!validShiftTypes.includes(cellValue)) {
          return { isValid: false, error: `Invalid shift type "${cellValue}" at row ${r + 1}, column ${c + 1}. Valid shift types: ${validShiftTypes.join(', ')}` };
        }

        validatedData.push({
          personId,
          dateId,
          shiftType: cellValue
        });
      }
    }

    return { isValid: true, validatedData };
  };

  const processShiftRequestCsvData = (validatedData: { personId: string; dateId: string; shiftType: string }[]) => {
    console.log('CSV Data Processing Summary:');
    console.log('===========================');
    console.log(`Total entries to process: ${validatedData.length}`);
    console.log('Data entries:', validatedData);

    // Group by person and date for efficient processing
    const groupedData = validatedData.reduce((acc, entry) => {
      const key = `${entry.personId}-${entry.dateId}`;
      if (!acc[key]) {
        acc[key] = {
          personId: entry.personId,
          dateId: entry.dateId,
          deltaPreferences: []
        };
      }
      acc[key].deltaPreferences.push({
        shiftTypeId: entry.shiftType,
        weight: addFormData.weight as number
      });
      return acc;
    }, {} as Record<string, { personId: string; dateId: string; deltaPreferences: { shiftTypeId: string; weight: number }[] }>);

    console.log('Grouped data by person-date:', groupedData);

    // Prepare updates for computeNewShiftPreferences using delta mode
    const updates = Object.values(groupedData).map(({ personId, dateId, deltaPreferences }) => ({
      personId,
      dateId,
      deltaPreferences
    }));

    console.log('Updates to apply:', updates);

    // Use the same logic as _handleCellSet via computeNewShiftPreferences helper
    const newPreferences = computeNewShiftPreferences(shiftRequestPreferences, updates);

    console.log('Final computed preferences:', newPreferences);

    // Use updateShiftRequestPreferences to bulk update all preferences at once
    updateShiftRequestPreferences(newPreferences);

    console.log('CSV processing completed successfully!');
  };

  // Validation function for people history CSV data
  const validatePeopleHistoryCsvData = (csvData: string[][]): {
    isValid: boolean;
    error?: string;
    validatedData?: { personId: string; shiftTypeId: string; repetitionCount: number }[];
  } => {
    // Validate CSV shape - should have people count rows (no header)
    const expectedPeopleCount = peopleData.items.length;

    if (csvData.length !== expectedPeopleCount) {
      return { isValid: false, error: `CSV should have ${expectedPeopleCount} rows (one per person), but has ${csvData.length} rows.` };
    }

    // Create a map of valid person IDs for quick lookup
    const validPersonIds = new Set(peopleData.items.map(person => person.id));
    const personRowMap = new Map<string, number>(); // Map person ID to row index

    // Validate each row has correct number of columns (3 columns: name, shift type, repetition count)
    // Validate that the first column contains a valid person ID (allow out-of-order)
    for (let i = 0; i < csvData.length; i++) {
      if (csvData[i].length !== 3) {
        return { isValid: false, error: `Row ${i + 1} should have 3 columns (name, shift type, repetition count), but has ${csvData[i].length} columns.` };
      }

      const personId = csvData[i][0].trim();
      if (!validPersonIds.has(personId)) {
        const validPersonList = Array.from(validPersonIds).join(', ');
        return { isValid: false, error: `Row ${i + 1} has invalid person ID "${personId}". Valid person IDs: ${validPersonList}` };
      }

      // Check for duplicate person IDs in the CSV
      if (personRowMap.has(personId)) {
        return { isValid: false, error: `Duplicate person ID "${personId}" found at row ${i + 1}. Person was already seen at row ${personRowMap.get(personId)! + 1}.` };
      }

      personRowMap.set(personId, i);
    }

    // Validate that all expected people are present in the CSV
    for (const person of peopleData.items) {
      if (!personRowMap.has(person.id)) {
        return { isValid: false, error: `Missing person "${person.id}" in CSV data. All people must be included.` };
      }
    }

    // Get all valid shift type IDs
    const validShiftTypes = shiftTypeData.items.map(st => st.id);
    const validatedData: { personId: string; shiftTypeId: string; repetitionCount: number }[] = [];

    for (let i = 0; i < csvData.length; i++) {
      const [personId, shiftTypeId, repetitionStr] = csvData[i].map(cell => cell.trim());

      // Skip if shift type is empty
      if (!shiftTypeId) {
        validatedData.push({ personId, shiftTypeId: '', repetitionCount: 0 });
        continue;
      }

      // Validate shift type exists
      if (!validShiftTypes.includes(shiftTypeId)) {
        return { isValid: false, error: `Invalid shift type "${shiftTypeId}" at row ${i + 1}. Valid shift types: ${validShiftTypes.join(', ')}` };
      }

      // Validate repetition count is a non-negative integer
      const repetitionCount = parseInt(repetitionStr);
      if (isNaN(repetitionCount) || repetitionCount < 0) {
        return { isValid: false, error: `Invalid repetition count '${repetitionStr}' for person '${personId}' at row ${i + 1}. Must be a non-negative integer.` };
      }

      validatedData.push({ personId, shiftTypeId, repetitionCount });
    }

    return {
      isValid: true,
      validatedData
    };
  };

    // Processing function for people history CSV data
  const processPeopleHistoryCsvData = (validatedData: { personId: string; shiftTypeId: string; repetitionCount: number }[]) => {
    console.log('People History CSV Data Processing Summary:');
    console.log('==========================================');
    console.log(`Processing ${validatedData.length} people history entries`);

    // Create updated people data with new history
    const updatedPeopleData = {
      ...peopleData,
      items: peopleData.items.map((person) => {
        // Find the corresponding CSV entry for this person
        const csvEntry = validatedData.find(entry => entry.personId === person.id);

        if (!csvEntry) {
          console.error(`No CSV entry found for person '${person.id}'. ${ERROR_SHOULD_NOT_HAPPEN}`);
          return person;
        }

        // Create new history array with repetitions of the shift type
        const newHistory: string[] = [];
        for (let i = 0; i < csvEntry.repetitionCount; i++) {
          newHistory.push(csvEntry.shiftTypeId);
        }

        console.log(`Setting ${csvEntry.repetitionCount} instances of shift type '${csvEntry.shiftTypeId}' for person '${person.id}'`);

        return {
          ...person,
          history: newHistory
        };
      })
    };

    // Perform bulk update to people data using reorderItems (a bit hacky)
    // This triggers the state update properly like in the people page bulk add
    reorderItems(DataType.PEOPLE, updatedPeopleData, updatedPeopleData.items);

    console.log('People History CSV processing completed successfully!');
  };

  // File processing functions for UploadButton components
  const processShiftRequestFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      if (!content) {
        alert('No content found in the uploaded file.');
        return;
      }

      try {
        // Parse CSV content
        const lines = content.split('\n').map(line => line.trim()).filter(line => line.length > 0);
        const csvData = lines.map(line => line.split(',').map(cell => cell.trim()));

        console.log('Raw shift-requests CSV data:', csvData);

        // Validate CSV data
        const validation = validateShiftRequestCsvData(csvData);

        if (!validation.isValid) {
          alert(`CSV validation failed: ${validation.error}`);
          return;
        }

        if (validation.validatedData && validation.validatedData.length > 0) {
          // Process the validated data
          processShiftRequestCsvData(validation.validatedData);
          alert(`Successfully processed CSV file with ${validation.validatedData.length} shift preferences!`);
        } else {
          alert('No valid shift preferences found in CSV file.');
        }
      } catch (error) {
        console.error('Error processing shift-requests CSV file:', error);
        alert('Error processing shift-requests CSV file. Please check the file format.');
      }
    };

    reader.readAsText(file);
  };

  const processPeopleHistoryFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      if (!content) {
        alert('No content found in the uploaded file.');
        return;
      }

      try {
        // Parse CSV content
        const lines = content.split('\n').map(line => line.trim()).filter(line => line.length > 0);
        const csvData = lines.map(line => line.split(',').map(cell => cell.trim()));

        console.log('Raw people-history CSV data:', csvData);

        // Validate CSV data
        const validation = validatePeopleHistoryCsvData(csvData);

        if (!validation.isValid) {
          alert(`CSV validation failed: ${validation.error}`);
          return;
        }

        if (validation.validatedData && validation.validatedData.length > 0) {
          // Process the validated data
          processPeopleHistoryCsvData(validation.validatedData);
          alert(`Successfully processed ${validation.validatedData.length} shift type entries from people history CSV!`);
        } else {
          alert('No valid entries found in the people history CSV file.');
        }
      } catch (error) {
        console.error('Error processing people-history CSV file:', error);
        alert('Error processing people-history CSV file. Please check the file format.');
      }
    };

    reader.readAsText(file);
  };

  // Compute the history columns count (max history length + 1)
  const historyColumnsCount = Math.max(
    0,
    ...peopleData.items.map(person => person.history?.length || 0)
  ) + 1;

  // Helper function to get all shift types (items and groups combined)
  const getAllShiftTypes = () => {
    return [...shiftTypeData.items, ...shiftTypeData.groups];
  };

  // Helper function to create combined date entries (date groups + regular dates)
  const getCombinedDateEntries = () => {
    return [...dateData.groups, ...dateData.items];
  };

  // Helper function to create combined people entries (people groups + regular people)
  const getCombinedPeopleEntries = () => {
    return [...peopleData.groups, ...peopleData.items];
  };

  // Clear functions for different types of requests and history
  const clearAllPeopleHistory = () => {
    if (!confirm('Are you sure you want to clear all people history?')) {
      return;
    }

    const updatedPeopleData = {
      ...peopleData,
      items: peopleData.items.map(person => ({
        ...person,
        history: []
      }))
    };

    reorderItems(DataType.PEOPLE, updatedPeopleData, updatedPeopleData.items);
  };

  const clearIndividualPersonDateRequests = () => {
    if (!confirm('Are you sure you want to clear all requests between individual people and individual dates?')) {
      return;
    }

    // Filter out preferences where both person and date are individual items (not groups)
    const individualPeopleIds = new Set(peopleData.items.map(p => p.id));
    const individualDateIds = new Set(dateData.items.map(d => d.id));

    const filteredPreferences = shiftRequestPreferences.filter(pref => {
      const personId = pref.person[0];
      const isIndividualPerson = individualPeopleIds.has(personId);
      const hasOnlyIndividualDates = pref.date.every(dateId => individualDateIds.has(dateId));

      // Keep this preference if it's NOT (individual person AND only individual dates)
      return !(isIndividualPerson && hasOnlyIndividualDates);
    });

    updateShiftRequestPreferences(filteredPreferences);
  };

  const clearGroupToIndividualDateRequests = () => {
    if (!confirm('Are you sure you want to clear all requests between people groups and individual dates?')) {
      return;
    }

    // Filter out preferences where person is a group and dates are individual
    const peopleGroupIds = new Set(peopleData.groups.map(g => g.id));
    const individualDateIds = new Set(dateData.items.map(d => d.id));

    const filteredPreferences = shiftRequestPreferences.filter(pref => {
      const personId = pref.person[0];
      const isPersonGroup = peopleGroupIds.has(personId);
      const hasOnlyIndividualDates = pref.date.every(dateId => individualDateIds.has(dateId));

      // Keep this preference if it's NOT (people group AND only individual dates)
      return !(isPersonGroup && hasOnlyIndividualDates);
    });

    updateShiftRequestPreferences(filteredPreferences);
  };

  const clearIndividualPersonToDateGroupRequests = () => {
    if (!confirm('Are you sure you want to clear all requests between individual people and date groups?')) {
      return;
    }

    // Filter out preferences where person is individual and dates include groups
    const individualPeopleIds = new Set(peopleData.items.map(p => p.id));
    const dateGroupIds = new Set(dateData.groups.map(g => g.id));

    const filteredPreferences = shiftRequestPreferences.filter(pref => {
      const personId = pref.person[0];
      const isIndividualPerson = individualPeopleIds.has(personId);
      const hasAnyDateGroup = pref.date.some(dateId => dateGroupIds.has(dateId));

      // Keep this preference if it's NOT (individual person AND has any date group)
      return !(isIndividualPerson && hasAnyDateGroup);
    });

    updateShiftRequestPreferences(filteredPreferences);
  };

  const clearGroupToGroupRequests = () => {
    if (!confirm('Are you sure you want to clear all requests between people groups and date groups?')) {
      return;
    }

    // Filter out preferences where both person and dates are groups
    const peopleGroupIds = new Set(peopleData.groups.map(g => g.id));
    const dateGroupIds = new Set(dateData.groups.map(g => g.id));

    const filteredPreferences = shiftRequestPreferences.filter(pref => {
      const personId = pref.person[0];
      const isPersonGroup = peopleGroupIds.has(personId);
      const hasAnyDateGroup = pref.date.some(dateId => dateGroupIds.has(dateId));

      // Keep this preference if it's NOT (people group AND has any date group)
      return !(isPersonGroup && hasAnyDateGroup);
    });

    updateShiftRequestPreferences(filteredPreferences);
  };

  const clearAllRequests = () => {
    if (!confirm('Are you sure you want to clear ALL shift requests?')) {
      return;
    }
    updateShiftRequestPreferences([]);
  };

  // Helper function to check if a date is a weekend (Saturday or Sunday)
  const isWeekend = (dateId: string): boolean => {
    if (!dateData.range) return false;

    try {
      const date = dateStrToDate(dateId, dateData.range);
      const dayOfWeek = date.getDay(); // 0 = Sunday, 6 = Saturday
      return dayOfWeek === 0 || dayOfWeek === 6;
    } catch {
      return false;
    }
  };

  // Helper function to get shift preferences for a person-date combination
  const getShiftPreferences = (personId: string, dateId: string): ShiftRequestPreference[] => {
    return shiftRequestPreferences.filter(
      p => p.person[0] === personId && p.date.includes(dateId)
    );
  };

  // Helper function to compute new shift preferences from delta updates
  // This is necessary since ShiftRequestPreference is of type { person: string[]; date: string[]; shiftType: string[]; weight: number },
  // where person and shiftType are single-element arrays. The date array is for readability of the exported YAML.
  const computeNewShiftPreferences = (
    currentPreferences: ShiftRequestPreference[],
    updates: {
      personId: string;
      dateId: string;
      deltaPreferences: { shiftTypeId: string; weight: number }[];
      clearFirst?: boolean; // If true, clear all existing preferences for this person-date first
    }[]
  ): ShiftRequestPreference[] => {
    let filteredPreferences = [...currentPreferences];

    // Process each update
    for (const update of updates) {
      const { personId, dateId, deltaPreferences, clearFirst = false } = update;

      // Get current preferences for this person-date combination
      const currentPersonDatePreferences = filteredPreferences.filter(
        p => p.person[0] === personId && p.date.includes(dateId)
      );

      // Convert to the format expected for processing
      let updatedPreferences = currentPersonDatePreferences.map(pref => ({
        shiftTypeId: pref.shiftType[0],
        weight: pref.weight
      }));

      // Clear all existing preferences first if requested
      if (clearFirst) {
        updatedPreferences = [];
      }

      // Apply delta changes
      for (const delta of deltaPreferences) {
        const existingIndex = updatedPreferences.findIndex(pref => pref.shiftTypeId === delta.shiftTypeId);

        if (existingIndex >= 0) {
          // Update existing preference
          if (delta.weight === 0) {
            // Remove preference if weight is 0
            updatedPreferences.splice(existingIndex, 1);
          } else {
            updatedPreferences[existingIndex].weight = delta.weight;
          }
        } else {
          // Add new preference (only if weight is not 0)
          if (delta.weight !== 0) {
            updatedPreferences.push({
              shiftTypeId: delta.shiftTypeId,
              weight: delta.weight
            });
          }
        }
      }

      // Remove the date ID from all existing preferences for this person
      filteredPreferences = filteredPreferences.map(pref => {
        if (pref.person[0] === personId) {
          return {
            ...pref,
            date: pref.date.filter(id => id !== dateId),
          };
        }
        return pref;
      });

      // Add back the updated preferences
      for (const preference of updatedPreferences) {
        const existingPreference = filteredPreferences.find(
          p => p.person[0] === personId &&
          p.shiftType[0] === preference.shiftTypeId &&
          p.weight === preference.weight
        );
        if (existingPreference) {
          existingPreference.date.push(dateId);
        } else {
          filteredPreferences.push({
            type: SHIFT_REQUEST,
            person: [personId],
            date: [dateId],
            shiftType: [preference.shiftTypeId],
            weight: preference.weight,
          });
        }
      }
    }

    // Remove preferences with empty date
    return filteredPreferences.filter(p => p.date.length > 0);
  };

  // Helper function to update shift preferences for a person-date combination
  const updateShiftPreferences = (personId: string, dateId: string, deltaPreferences: { shiftTypeId: string; weight: number }[]) => {
    // Use delta preferences with clearFirst to replicate full replacement behavior
    const updates = [{ personId, dateId, deltaPreferences, clearFirst: true }];
    const newPreferences = computeNewShiftPreferences(shiftRequestPreferences, updates);
    updateShiftRequestPreferences(newPreferences);
  };

  // Helper function to get visual representation of preferences
  const getPreferenceDisplay = (personId: string, dateId: string) => {
    const preferences = getShiftPreferences(personId, dateId);
    if (preferences.length === 0) return null;

    // Sort preferences by magnitude (highest first), then by weight (positive first), then by shift type ID
    const sortedPreferences = preferences.sort((a, b) => {
      const magA = Math.abs(a.weight);
      const magB = Math.abs(b.weight);
      if (magB !== magA) {
        return magB - magA;
      }
      if (b.weight !== a.weight) {
        return b.weight - a.weight;
      }
      // Compare shift_type indices in shiftTypeData.items
      const indexA = getAllShiftTypes().findIndex(st => a.shiftType[0] === st.id);
      const indexB = getAllShiftTypes().findIndex(st => b.shiftType[0] === st.id);
      if (indexA < indexB) return -1;
      if (indexA > indexB) return 1;
      return 0;
    });

    // Find the global maximum weight
    const globalMaxWeight = 1000000;

    // Find the maximum absolute weight for this person-date combination
    const maxWeight = Math.min(globalMaxWeight, Math.max(...preferences.map(p => isFinite(p.weight) ? Math.abs(p.weight) : globalMaxWeight)));

    const ratio = Math.max(0.05, Math.log2(maxWeight) / Math.log2(globalMaxWeight));

    // Determine preference type
    const isAllPositive = preferences.every(p => p.weight > 0);
    const isAllNegative = preferences.every(p => p.weight < 0);

    // Set cell/text color based on preference type
    let cellColor = `rgba(250, 204, 21, ${ratio})`; // 'bg-yellow-400';
    let textColor = 'text-yellow-800';
    if (isAllPositive) {
      cellColor = `rgba(74, 222, 128, ${ratio})`; // 'bg-green-400';
      textColor = 'text-green-800';
    } else if (isAllNegative) {
      cellColor = `rgba(248, 113, 113, ${ratio})`; // 'bg-red-400';
      textColor = 'text-red-800';
    }

    return {
      preferences: sortedPreferences,
      color: cellColor,
      textColor: textColor,
      maxWeight: maxWeight
    };
  };

  const openEditor = (personId: string, dateId: string) => {
    setEditorState({
      isOpen: true,
      personId,
      dateId,
    });
  };

  const closeEditor = () => {
    setEditorState({
      isOpen: false,
      personId: '',
      dateId: '',
    });
  };

  const handleSavePreferences = (preferences: { shiftTypeId: string; weight: number }[]) => {
    updateShiftPreferences(editorState.personId, editorState.dateId, preferences);
  };

  const handleCellMouseEnter = (selectedCellType: SelectedCellType, personId: string, identifier: string | number) => {
    if (isAddMode && isMultiSelectDragRef.current) {
      if (selectedCellType === SelectedCellType.PREFERENCE) {
        _handleCellSet(personId, identifier as string);
      } else if (selectedCellType === SelectedCellType.HISTORY) {
        handleHistoryCellClickInternal(personId, identifier as number);
      }
    }
  };

  const handleCellMouseDown = (selectedCellType: SelectedCellType, personId: string, identifier: string | number, event: React.MouseEvent) => {
    if (event.button !== 0) return;

    isMultiSelectDragRef.current = true;
    if (isAddMode) {
      if (selectedCellType === SelectedCellType.PREFERENCE) {
        _handleCellSet(personId, identifier as string);
      } else if (selectedCellType === SelectedCellType.HISTORY) {
        handleHistoryCellClickInternal(personId, identifier as number);
      }
    }
    document.body.style.userSelect = 'none';
  };

  const handleCellMouseUp = (event: React.MouseEvent) => {
    if (event.button !== 0) return;

    // End multi-select drag
    isMultiSelectDragRef.current = false;
    document.body.style.userSelect = '';
  };

  const _handleCellSet = (personId: string, dateId: string) => {
    if (isAddMode) {
      // In add mode, update the preferences with the form data
      // If no shift types are selected, clear all preferences for this person-date combination
      if (addFormData.shiftTypes.length === 0) {
        updateShiftPreferences(personId, dateId, []);
        return;
      }

      // Validate weight before proceeding
      if (!validateWeight()) {
        return;
      }

      // Use the parseWeightValue helper to consistently parse the weight
      const weightValue = addFormData.weight as number; // We know it's valid from validateWeight()

      // Create delta preferences for each selected shift type
      const deltaPreferences = addFormData.shiftTypes.map(shiftTypeId => ({
        shiftTypeId,
        weight: weightValue
      }));

      // Use computeNewShiftPreferences with delta mode
      const updates = [{ personId, dateId, deltaPreferences }];
      const newPreferences = computeNewShiftPreferences(shiftRequestPreferences, updates);
      updateShiftRequestPreferences(newPreferences);
    }
  };

  const handleCellClick = (personId: string, dateId: string) => {
    if (isAddMode) {
      _handleCellSet(personId, dateId);
    } else {
      openEditor(personId, dateId);
    }
  };

  const handleHistoryCellClickInternal = (personId: string, historyIndex: number) => {
    if (isAddMode) {
      // In add mode, directly update the history cell
      const person = peopleData.items.find(p => p.id === personId);
      if (!person) {
        console.error(`Person ${personId} not found. ${ERROR_SHOULD_NOT_HAPPEN}`);
        return;
      }

      const currentHistory = person.history!;
      const offset = historyColumnsCount - currentHistory.length;

      // If no shift types are selected (Clear mode), clear the history position
      if (addFormData.shiftTypes.length === 0) {
        // If targeting a position after the actual history (empty history cells on the left)
        if (historyIndex >= offset) {
          const position = historyIndex - offset;
          updatePersonHistory(personId, position);
        }
      } else {
        if (addFormData.shiftTypes.length > 1) {
          setErrors({
            shiftTypes: 'Cannot set history to multiple shift types.'
          });
          return;
        }

        // History can only be set to one shift type at a time, so we use the first one
        const firstShiftType = addFormData.shiftTypes[0];

        if (!shiftTypeData.items.find(st => st.id === firstShiftType)) {
          // Cannot set history to a shift type group.
          console.warn(`Cannot set history to a shift type group.`);
          return;
        }
        if (historyIndex < offset) {
          // If targeting a position before the actual history, add a new history entry
          addPersonHistory(personId, firstShiftType);
        } else {
          // If targeting a position after the actual history, update the history entry
          const position = historyIndex - offset;
          updatePersonHistory(personId, position, firstShiftType);
        }
      }
    }
  };

  const getHistoryValue = (history: string[], columnIndex: number): string => {
    const offset = historyColumnsCount - history.length;  // Note that we always have one extra column for the history
    if (columnIndex < offset) return '';
    return history[columnIndex - offset];
  };

  const openHistoryEditor = (personId: string, historyIndex: number) => {
    setHistoryEditState({
      isOpen: true,
      personId,
      historyIndex,
    });
  };

  const closeHistoryEditor = () => {
    setHistoryEditState({
      isOpen: false,
      personId: '',
      historyIndex: -1,
    });
  };

  const handleSaveHistory = (shiftTypeId: string) => {
    const person = peopleData.items.find(p => p.id === historyEditState.personId);
    if (!person) {
      console.error(`Person ${historyEditState.personId} not found. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }

    const currentHistory = person.history!;
    const offset = historyColumnsCount - currentHistory.length;

    // If targeting a position before the actual history (empty history cells on the left)
    if (historyEditState.historyIndex < offset) {
      if (shiftTypeId !== '') {
        addPersonHistory(historyEditState.personId, shiftTypeId);
      } // else do nothing
    } else {
      const position = historyEditState.historyIndex - offset;
      if (shiftTypeId !== '') {
        updatePersonHistory(historyEditState.personId, position, shiftTypeId);
      } else {
        updatePersonHistory(historyEditState.personId, position);
      }
    }
    closeHistoryEditor();
  };

  const handleHistoryCellClick = (personId: string, historyIndex: number) => {
    if (isAddMode) {
      handleHistoryCellClickInternal(personId, historyIndex);
    } else {
      openHistoryEditor(personId, historyIndex);
    }
  };

  // Helper function to render table header
  const renderTableHeader = (isSticky = false) => {
    let columnIndex = 0;

    return (
      <tr>
        <th
          className={`sticky left-0 z-10 bg-gray-50 px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider border-r border-gray-200 shadow-sm`}
          style={isSticky && columnWidths[columnIndex] ? { width: `${columnWidths[columnIndex++]}px`, minWidth: `${columnWidths[columnIndex-1]}px`, maxWidth: `${columnWidths[columnIndex-1]}px` } : {}}
        >
          People
        </th>
        {/* History columns */}
        {Array.from({ length: historyColumnsCount }, (_, index) => (
          <th
            key={`history-${index}`}
            className="px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider border-r border-gray-200 bg-amber-100"
            title={`History position H-${historyColumnsCount - index}`}
            style={isSticky && columnWidths[columnIndex] ? { width: `${columnWidths[columnIndex++]}px`, minWidth: `${columnWidths[columnIndex-1]}px`, maxWidth: `${columnWidths[columnIndex-1]}px` } : {}}
          >
            <div className="whitespace-nowrap">H-{historyColumnsCount - index}</div>
          </th>
        ))}
        {getCombinedDateEntries().map((dateEntry) => {
          const isWeekendDate = dateData.items.find(item => item.id === dateEntry.id) && isWeekend(dateEntry.id);
          return (
            <th
              key={dateEntry.id}
              className={`px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase tracking-wider border-r border-gray-200 ${
                dateEntry.id === dateData.groups[0].id
                  ? 'border-l-2 border-l-blue-200'
                  : ''
              } ${
                dateEntry.id === dateData.groups[dateData.groups.length - 1].id
                  ? 'border-r-2 border-r-blue-200'
                  : ''
              } ${
                isWeekendDate ? 'bg-purple-100' : ''
              }`}
              title={dateEntry.description || dateEntry.id}
              style={isSticky && columnWidths[columnIndex] ? { width: `${columnWidths[columnIndex++]}px`, minWidth: `${columnWidths[columnIndex-1]}px`, maxWidth: `${columnWidths[columnIndex-1]}px` } : {}}
            >
              <div className="whitespace-nowrap">
                {dateEntry.id}
                {dateData.items.find(item => item.id === dateEntry.id) && (
                  <span className="ml-1">
                    {dateStrToDate(dateEntry.id, dateData.range!).toLocaleDateString('en-US', { weekday: 'short' })}
                  </span>
                )}
              </div>
            </th>
          );
        })}
        {/* Trailing empty white cell for better scrolling when sticky */}
        {isSticky && (
          <th className="px-2 py-2 bg-white border-r border-gray-200">
            <div className="whitespace-nowrap w-screen"></div>
          </th>
        )}
      </tr>
    );
  };

  // Instructions for the help component
  const instructions = [
    "This table shows shift preferences for each person on each date",
    "History columns (H-1, H-2, etc.) show previous shift types assigned to each person",
    "Click on any history cell to set or edit shift types for that time period",
    "Each row represents a person, followed by their history, then date columns",
    "Click on any cell to set shift preferences with weights for different shift types",
    "In 'Quick Add Preference' mode, you can drag across multiple cells to quickly apply the same preference",
    "Green cells indicate positive preferences (wants this shift type)",
    "Red cells indicate negative preferences (wants to avoid this shift type)",
    "Yellow cells indicate a mix of positive and negative preferences",
    "The displayed shift type prioritizes the one with the strongest preference or avoidance",
    "Use the navigation tabs or keyboard shortcuts to move between pages"
  ];



  // Check if we have the required data
  const hasRequiredData = (dateData.range?.startDate && dateData.range?.endDate && dateData.items.length > 0 && peopleData.items.length > 0 && (shiftTypeData.items.length > 0 || shiftTypeData.groups.length > 0));

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Sticky Quick Add Preference - compact version when scrolling */}
      {showStickyQuickAdd && hasRequiredData && isAddMode && (
        <div ref={stickyQuickAddRef} className="fixed top-0 left-0 right-0 z-50 bg-white shadow-md border-b border-gray-200">
          <div className="container mx-auto px-4 py-3">
            <div className="flex items-center gap-4 flex-wrap">
              {/* Compact Shift Types */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-700 whitespace-nowrap">Shift Types:</span>
                  <div className="flex-1">
                    <CheckboxList
                      items={getAllShiftTypes().map(shiftType => ({
                        id: shiftType.id,
                        description: shiftType.description
                      }))}
                      selectedIds={addFormData.shiftTypes}
                      onToggle={(id) => {
                        setAddFormData(prev => ({
                          ...prev,
                          shiftTypes: prev.shiftTypes.includes(id)
                            ? prev.shiftTypes.filter(shiftTypeId => shiftTypeId !== id)
                            : [...prev.shiftTypes, id]
                        }));
                        setErrors(prev => ({ ...prev, shiftTypes: '' }));
                      }}
                      label=""
                    />
                    {errors.shiftTypes && (
                      <p className="mt-1 text-xs text-red-600 flex items-center gap-1">
                        <FiAlertCircle className="h-3 w-3" />
                        {errors.shiftTypes}
                      </p>
                    )}
                  </div>
                </div>
              </div>

              {/* Inline Weight */}
              <div className="flex items-center gap-2">
                <label className="text-sm font-medium text-gray-700 whitespace-nowrap">Weight:</label>
                <div className="flex items-center gap-1">
                  <input
                    type="text"
                    value={addFormData.weight}
                    onChange={(e) => {
                      setAddFormData(prev => ({ ...prev, weight: parseWeightValue(e.target.value) }));
                      if (errors.weight) {
                        setErrors(prev => ({ ...prev, weight: '' }));
                      }
                    }}
                    placeholder="±#"
                    className={`w-16 px-2 py-1 text-sm border rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 text-center ${
                      errors.weight ? 'border-red-300 bg-red-50' : 'border-gray-300'
                    }`}
                  />
                  <div className="flex flex-col gap-0.5">
                    <button
                      type="button"
                      onClick={() => {
                        setAddFormData(prev => ({ ...prev, weight: Infinity }));
                        if (errors.weight) {
                          setErrors(prev => ({ ...prev, weight: '' }));
                        }
                      }}
                      className="px-1 py-0.5 text-xs bg-green-100 text-green-700 hover:bg-green-200 border border-green-300 rounded transition-colors focus:outline-none focus:ring-1 focus:ring-green-200"
                      title="Set to positive infinity (∞)"
                    >
                      +∞
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setAddFormData(prev => ({ ...prev, weight: -Infinity }));
                        if (errors.weight) {
                          setErrors(prev => ({ ...prev, weight: '' }));
                        }
                      }}
                      className="px-1 py-0.5 text-xs bg-red-100 text-red-700 hover:bg-red-200 border border-red-300 rounded transition-colors focus:outline-none focus:ring-1 focus:ring-red-200"
                      title="Set to negative infinity (-∞)"
                    >
                      -∞
                    </button>
                  </div>
                </div>
                {errors.weight && (
                  <div className="flex items-center">
                    <FiAlertCircle className="h-4 w-4 text-red-500" title={errors.weight} />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Sticky Header - appears when scrolling */}
      {showStickyHeader && hasRequiredData && columnWidths.length > 0 && (
        <div className="fixed z-40 bg-white shadow-md border-b border-gray-200"
             style={{
               top: `${showStickyQuickAdd ? quickAddHeight : 0}px`,
               left: `${stickyHeaderLeft}px`,
               width: `calc(100vw - ${stickyHeaderLeft}px)`
             }}>
          <div
            ref={stickyScrollContainerRef}
            className="overflow-x-auto [&::-webkit-scrollbar]:hidden"
            style={{
              scrollbarWidth: 'none', // Hide scrollbar on Firefox
              msOverflowStyle: 'none'  // Hide scrollbar on IE/Edge
            }}
          >
            <table className="min-w-full divide-y divide-gray-200" style={{ tableLayout: 'fixed' }}>
              <thead className="bg-gray-50">
                {renderTableHeader(true)}
              </thead>
            </table>
          </div>
        </div>
      )}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-800">Shift Requests</h1>
          {instructions.length > 0 && (
            <button
              onClick={() => setShowInstructions(!showInstructions)}
              className="text-gray-500 hover:text-gray-700 transition-colors"
              title="Toggle instructions"
            >
              <FiHelpCircle className="h-6 w-6" />
            </button>
          )}
        </div>
        <div className="flex gap-4">
          <ToggleButton
            label="Quick Add Preference"
            isToggled={isAddMode}
            onToggle={() => {
              if (isAddMode) {
                handleCancel();
              } else {
                handleStartAdd();
              }
            }}
          />
        </div>
      </div>

      {showInstructions && instructions.length > 0 && (
        <div className="mb-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h3 className="text-lg font-medium text-blue-800 mb-3">Instructions</h3>
          <ul className="space-y-2 text-sm text-blue-700">
            {instructions.map((instruction, index) => (
              <li key={index}>• {instruction}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Show appropriate message if data is missing */}
      {!hasRequiredData && (
        <div className="text-center">
          <div className="text-sm text-gray-500 italic p-4 text-center border border-gray-200 rounded-lg bg-gray-50">
            {(!dateData.range?.startDate || !dateData.range?.endDate || dateData.items.length === 0) ? (
              <>
                Please set up your dates first by visiting the{' '}
                <Link href="/dates" className="text-blue-600 hover:text-blue-800 underline">
                  Dates
                </Link>{' '}
                tab.
              </>
            ) : peopleData.items.length === 0 ? (
              <>
                Please set up your people first by visiting the{' '}
                <Link href="/people" className="text-blue-600 hover:text-blue-800 underline">
                  People
                </Link>{' '}
                tab.
              </>
            ) : (
              <>
                Please set up your shift types first by visiting the{' '}
                <Link href="/shift-types" className="text-blue-600 hover:text-blue-800 underline">
                  Shift Types
                </Link>{' '}
                tab.
              </>
            )}
          </div>
        </div>
      )}

      {hasRequiredData && isAddMode && (
        <div ref={quickAddRef} className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
          <div className="px-6 py-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800">
                Add Shift Preference
              </h2>
              <div className="flex gap-2">
                <UploadButton
                  onFileUpload={processPeopleHistoryFile}
                  acceptedFileTypes={['.csv', '.txt']}
                  buttonText="Upload People History (shorthand)"
                  tooltipText="Upload a CSV file with people history (name, shift type, repetition count)"
                  className="bg-green-600 text-white hover:bg-green-700 focus:ring-green-500"
                  icon={<FiUpload className="h-4 w-4" />}
                />
                <UploadButton
                  onFileUpload={(file) => {
                    // Validate weight before processing
                    if (!validateWeight()) {
                      return; // Don't proceed if weight is invalid
                    }
                    if (addFormData.weight === 0) {
                      alert('Weight must be a non-zero number.');
                      return; // Don't proceed if weight is zero
                    }
                    processShiftRequestFile(file);
                  }}
                  acceptedFileTypes={['.csv', '.txt']}
                  buttonText="Upload Shift Requests"
                  tooltipText={
                    !isValidWeightValue(addFormData.weight)
                      ? 'Weight must be a valid number, Infinity, or -Infinity'
                      : addFormData.weight === 0
                      ? 'Weight must be a non-zero number'
                      : 'Upload a CSV file with shift preferences (people x (dates + 1) matrix)'
                  }
                  disabled={!isValidWeightValue(addFormData.weight) || addFormData.weight === 0}
                  icon={<FiUpload className="h-4 w-4" />}
                />
              </div>
            </div>

            <div className="space-y-6">
              {/* Shift Type Selection */}
              <div>
                <CheckboxList
                  items={getAllShiftTypes().map(shiftType => ({
                    id: shiftType.id,
                    description: shiftType.description
                  }))}
                  selectedIds={addFormData.shiftTypes}
                  onToggle={(id) => {
                    setAddFormData(prev => ({
                      ...prev,
                      shiftTypes: prev.shiftTypes.includes(id)
                        ? prev.shiftTypes.filter(shiftTypeId => shiftTypeId !== id)
                        : [...prev.shiftTypes, id]
                    }));
                    setErrors(prev => ({ ...prev, shiftTypes: '' }));
                  }}
                  label="Shift Types (select multiple to set preferences for each)"
                />
                {errors.shiftTypes && (
                  <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {errors.shiftTypes}
                  </p>
                )}
              </div>

              {/* Weight Input */}
              <WeightInput
                value={addFormData.weight}
                onChange={(value) => {
                  setAddFormData(prev => ({ ...prev, weight: value }));
                  // Clear error when user starts typing
                  if (errors.weight) {
                    setErrors(prev => ({ ...prev, weight: '' }));
                  }
                }}
                error={errors.weight}
                placeholder="Enter weight (positive for preference, negative for avoidance, or Infinity/-Infinity)"
              />
            </div>
          </div>
        </div>
      )}

      {/* Show main content only if we have all required data */}
      {hasRequiredData && (
        <>
          {/* Clear Data Section */}
          <div className="mb-6 bg-white shadow-md rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800">Clear Data</h3>
              <p className="text-sm text-gray-600 mt-1">Remove different types of data with targeted clear operations</p>
            </div>
            <div className="px-6 py-4">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* Clear People History */}
                <button
                  onClick={clearAllPeopleHistory}
                  className="px-4 py-2 text-sm font-medium text-amber-800 bg-amber-50 hover:bg-amber-100 rounded-md transition-colors flex items-center gap-2"
                  title="Clear all shift history entries for all people"
                >
                  <FiTrash2 className="h-4 w-4" />
                  Clear All People History
                </button>

                {/* Clear All Requests */}
                <button
                  onClick={clearAllRequests}
                  className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-md transition-colors flex items-center gap-2"
                  title="Clear all shift requests completely"
                >
                  <FiTrash2 className="h-4 w-4" />
                  Clear All Requests
                </button>

                {/* Clear Person Individual-to-Individual Date Requests */}
                <button
                  onClick={clearIndividualPersonDateRequests}
                  className="px-4 py-2 text-sm font-medium text-rose-700 bg-rose-50 hover:bg-rose-100 rounded-md transition-colors flex items-center gap-2"
                  title="Clear all shift requests between individual people and individual dates"
                >
                  <FiTrash2 className="h-4 w-4" />
                  Clear Person Individual-to-Individual Date Requests
                </button>

                {/* Clear People Group-to-Individual Date Requests */}
                <button
                  onClick={clearGroupToIndividualDateRequests}
                  className="px-4 py-2 text-sm font-medium text-purple-700 bg-purple-50 hover:bg-purple-100 rounded-md transition-colors flex items-center gap-2"
                  title="Clear all shift requests between people groups and individual dates"
                >
                  <FiTrash2 className="h-4 w-4" />
                  Clear People Group-to-Individual Date Requests
                </button>

                {/* Clear Person Individual-to-Group Dates Requests */}
                <button
                  onClick={clearIndividualPersonToDateGroupRequests}
                  className="px-4 py-2 text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-md transition-colors flex items-center gap-2"
                  title="Clear all shift requests between individual people and date groups"
                >
                  <FiTrash2 className="h-4 w-4" />
                  Clear Person Individual-to-Group Dates Requests
                </button>

                {/* Clear People Group-to-Group Dates Requests */}
                <button
                  onClick={clearGroupToGroupRequests}
                  className="px-4 py-2 text-sm font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-md transition-colors flex items-center gap-2"
                  title="Clear all shift requests between people groups and date groups"
                >
                  <FiTrash2 className="h-4 w-4" />
                  Clear People Group-to-Group Dates Requests
                </button>
              </div>
            </div>
          </div>

          {/* Shift Requests Table */}
          <div className="bg-white shadow-md rounded-lg overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800">Shift Preference Matrix</h3>
            </div>

            <div ref={mainScrollContainerRef} className="overflow-x-auto">
              <table ref={tableRef} className="min-w-full divide-y divide-gray-200">
                {/* Header */}
                <thead className="bg-gray-50">
                  {renderTableHeader()}
                </thead>

                {/* Body */}
                <tbody className="bg-white divide-y divide-gray-200">
                  {getCombinedPeopleEntries().map((personEntry) => {
                    const isPeopleGroup = peopleData.groups.find(group => group.id === personEntry.id);
                    const person = isPeopleGroup ? null : (personEntry as Item);

                    // Calculate person index (only count actual people, not groups)
                    const personIndex = person ? peopleData.items.findIndex(p => p.id === personEntry.id) + 1 : 0;

                    return (
                    <tr key={personEntry.id} className={`hover:bg-gray-50 ${
                        personEntry.id === peopleData.groups[0].id
                        ? 'border-t-2 border-t-green-200'
                        : ''
                    } ${
                        personEntry.id === peopleData.groups[peopleData.groups.length - 1].id
                        ? 'border-b-2 border-b-green-200'
                        : ''
                    }`}>
                      {/* Person column */}
                      <td className="sticky left-0 z-10 bg-white px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 border-r border-gray-200 shadow-sm">
                        <div>
                          <div>{person ? `${personIndex}. ${personEntry.id}` : personEntry.id}</div>
                          {personEntry.description && (
                            <div className="text-gray-500 text-xs max-w-[150px] truncate">{personEntry.description}</div>
                          )}
                        </div>
                      </td>
                      {/* History columns */}
                      {Array.from({ length: historyColumnsCount }, (_, index) => {
                        // People groups don't have history, so show empty cells
                        if (isPeopleGroup) {
                          return (
                            <td
                              key={`${personEntry.id}-history-${index}`}
                              className="px-1 py-1 text-center border-r border-gray-200 bg-gray-50"
                            >
                              <div className="text-sm font-medium text-gray-300">—</div>
                            </td>
                          );
                        }

                        const historyValue = getHistoryValue(person!.history!, index);
                        const offset = historyColumnsCount - person!.history!.length;

                        // Only show one extra clickable cell, others are empty non-clickable
                        const isClickable = index >= offset - 1;

                        return (
                          <td
                            key={`${personEntry.id}-history-${index}`}
                            className={`px-1 py-1 text-center border-r border-gray-200 ${
                              isClickable
                                ? 'bg-amber-50 cursor-pointer hover:bg-amber-100 transition-colors duration-150'
                                : 'bg-gray-50'
                            }`}
                            onClick={() => isClickable && !isAddMode && handleHistoryCellClick(personEntry.id, index)}
                            onMouseEnter={() => isClickable && handleCellMouseEnter(SelectedCellType.HISTORY, personEntry.id, index)}
                            onMouseDown={(e) => isClickable && handleCellMouseDown(SelectedCellType.HISTORY, personEntry.id, index, e)}
                            onMouseUp={(e) => isClickable && handleCellMouseUp(e)}
                            title={isClickable ? (isAddMode
                              ? `Click or drag to set history position H-${historyColumnsCount - index} to ${addFormData.shiftTypes.length > 0 ? addFormData.shiftTypes[0] : 'clear'}`
                              : `Click to edit history position H-${historyColumnsCount - index}`) : ''}
                          >
                            <div className={`text-sm font-medium ${isClickable ? 'text-gray-900' : 'text-gray-300'}`}>
                              {!isClickable ? '' : (historyValue || '—')}
                            </div>
                          </td>
                        );
                      })}
                      {/* Date groups and per-date columns */}
                      {getCombinedDateEntries().map((dateEntry) => {
                        // Get preferences for both people groups and individual people
                        const display = getPreferenceDisplay(personEntry.id, dateEntry.id);
                        const isWeekendDate = dateData.items.find(item => item.id === dateEntry.id) && isWeekend(dateEntry.id);

                        return (
                          <td
                            key={`${personEntry.id}-${dateEntry.id}`}
                            className={`px-0.5 py-0.5 text-center cursor-pointer transition-colors duration-150 border-r border-gray-200 hover:bg-gray-100 ${
                              dateEntry.id === dateData.groups[0].id
                                ? 'border-l-2 border-l-blue-200'
                                : ''
                            } ${
                              dateEntry.id === dateData.groups[dateData.groups.length - 1].id
                                ? 'border-r-2 border-r-blue-200'
                                : ''
                            } ${
                              display
                                ? `${display.textColor}`
                                : ''
                            } ${
                              isWeekendDate && !display ? 'bg-purple-50' : ''
                            }`}
                            style={{
                              backgroundColor: display?.color || undefined
                            }}
                            title={isAddMode
                              ? `Click or drag to update preferences for ${personEntry.id} on date ${dateEntry.id}`
                              : `Click to update preferences for ${personEntry.id} on date ${dateEntry.id}`}
                            onClick={() => !isAddMode && handleCellClick(personEntry.id, dateEntry.id)}
                            onMouseEnter={() => handleCellMouseEnter(SelectedCellType.PREFERENCE, personEntry.id, dateEntry.id)}
                            onMouseDown={(e) => handleCellMouseDown(SelectedCellType.PREFERENCE, personEntry.id, dateEntry.id, e)}
                            onMouseUp={(e) => handleCellMouseUp(e)}
                          >
                            {display && (() => {
                              const maxVisible = display.preferences.length <= 3 ? 3 : 2; // Show all if 3 or fewer, otherwise show 2
                              const visiblePreferences = display.preferences.slice(0, maxVisible);
                              const remainingCount = display.preferences.length - maxVisible;

                              return (
                                <>
                                  {visiblePreferences.map((pref, index) => {
                                    return (
                                      <div key={index} className="text-xs font-semibold leading-tight px-0.5 whitespace-nowrap">
                                        {pref.shiftType} ({getWeightDisplayLabel(pref.weight)})
                                      </div>
                                    );
                                  })}
                                  {remainingCount > 0 && (
                                    <div className="text-[10px] font-medium opacity-75 px-0.5">
                                      +{remainingCount} more
                                    </div>
                                  )}
                                </>
                              );
                            })()}
                          </td>
                        );
                      })}
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Current Shift Requests */}
          <div className="mt-6 bg-blue-50 shadow-md rounded-lg overflow-hidden border border-blue-200">
            <div className="px-6 py-4 border-b border-blue-200 bg-blue-100">
              <h3 className="text-lg font-semibold text-blue-800">Current Shift Requests</h3>
              <p className="text-sm text-blue-600 mt-1">Auto-computed from the preference matrix above</p>
            </div>

            {shiftRequestPreferences.length === 0 ? (
              <div className="px-6 py-8 text-center text-blue-500">
                No shift requests defined yet. Click on any cell in the matrix above to add preferences.
              </div>
            ) : (
              <div className="divide-y divide-blue-200">
                {shiftRequestPreferences.map((preference, index) => {
                  // Get person and shift type descriptions for display
                  const person = peopleData.items.find(p => p.id === preference.person[0]);
                  const shiftType = getAllShiftTypes().find(st => st.id === preference.shiftType[0]);

                  return (
                    <div key={index} className="px-6 py-5 bg-blue-50">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-3 text-sm text-blue-600">
                            <div>
                              <span className="font-medium">Person:</span>{' '}
                              <span className="text-blue-900">{preference.person}</span>
                              {person?.description && (
                                <div className="text-xs text-blue-500 mt-1 max-w-[150px] truncate">{person.description}</div>
                              )}
                            </div>
                            <div>
                              <span className="font-medium">Date:</span>{' '}
                              <span className="text-blue-900">
                                {preference.date.join(', ')}
                              </span>
                            </div>
                            <div>
                              <span className="font-medium">Shift Type:</span>{' '}
                              <span className="text-blue-900">{preference.shiftType}</span>
                              {shiftType?.description && (
                                <div className="text-xs text-blue-500 mt-1 max-w-[150px] truncate">{shiftType.description}</div>
                              )}
                            </div>
                            <div>
                              <span className="font-medium">Weight:</span>{' '}
                              <span className={`font-medium ${preference.weight > 0 ? 'text-green-600' : preference.weight < 0 ? 'text-red-600' : 'text-blue-900'}`}>
                                {preference.weight > 0 ? '+' : ''}{preference.weight}
                              </span>
                              <div className="text-xs text-blue-500 mt-1">
                                {preference.weight > 0 ? 'Wants this shift' : preference.weight < 0 ? 'Wants to avoid' : 'Neutral'}
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Current People History */}
          <div className="mt-6 bg-blue-50 shadow-md rounded-lg overflow-hidden border border-blue-200">
            <div className="px-6 py-4 border-b border-blue-200 bg-blue-100">
              <h3 className="text-lg font-semibold text-blue-800">Current People History</h3>
              <p className="text-sm text-blue-600 mt-1">Auto-computed from the history matrix above</p>
            </div>

            {peopleData.items.every(person => person.history!.length === 0) ? (
              <div className="px-6 py-8 text-center text-blue-500">
                No history entries defined yet. Click on any history cell in the matrix above to add entries.
              </div>
            ) : (
              <div className="divide-y divide-blue-200">
                {peopleData.items.map((person) => {
                  if (!person.history || person.history.length === 0) return null;

                  return (
                    <div key={person.id} className="px-6 py-5 bg-blue-50">
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="mb-3">
                            <div className="text-sm font-medium text-blue-800">
                              Person: <span className="text-blue-900">{person.id}</span>
                            </div>
                            {person.description && (
                              <div className="text-xs text-blue-500 mt-1 max-w-[150px] truncate">{person.description}</div>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-x-6 gap-y-3">
                            {person.history.map((shiftTypeId, index) => {
                              const shiftType = getAllShiftTypes().find(st => st.id === shiftTypeId);
                              const historyPosition = person.history!.length - index;

                              return (
                                <div key={index} className="text-sm text-blue-600">
                                  <span className="font-medium">H-{historyPosition}:</span>{' '}
                                  <span className="text-blue-900">{shiftTypeId}</span>
                                  {shiftType?.description && (
                                    <div className="text-xs text-blue-500 mt-1 max-w-[150px] truncate">{shiftType.description}</div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                        <div className="flex justify-end space-x-2 ml-4">
                          <button
                            onClick={() => openHistoryEditor(person.id, historyColumnsCount - person.history!.length)}
                            className="text-blue-600 hover:text-blue-900 flex items-center gap-1 text-sm"
                          >
                            <FiEdit2 className="h-4 w-4" />
                            Edit
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}

      {/* Shift Preference Editor Modal */}
      <ShiftPreferenceEditor
        isOpen={editorState.isOpen}
        onClose={closeEditor}
        onSave={handleSavePreferences}
        personId={editorState.personId}
        dateId={editorState.dateId}
        shiftTypes={getAllShiftTypes()}
        initialPreferences={getShiftPreferences(editorState.personId, editorState.dateId).map(p => ({ shiftTypeId: p.shiftType[0], weight: p.weight }))}
      />

      {/* History Editor Modal */}
      {historyEditState.isOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-sm w-full mx-4">
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-800">
                Edit History - {historyEditState.personId}
              </h3>
              <p className="text-sm text-gray-600 mt-1">
                Position H-{historyColumnsCount - historyEditState.historyIndex}
              </p>
            </div>

            <div className="px-6 py-4">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Shift Type:
              </label>
              <select
                value={(() => {
                  const person = peopleData.items.find(p => p.id === historyEditState.personId);
                  if (!person) {
                    console.error(`Person ${historyEditState.personId} not found. ${ERROR_SHOULD_NOT_HAPPEN}`);
                    return '';
                  }
                  return getHistoryValue(person.history!, historyEditState.historyIndex);
                })()}
                onChange={(e) => handleSaveHistory(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                autoFocus
              >
                <option value="">-- Clear --</option>
                {shiftTypeData.items.map((shiftType) => (
                  <option key={shiftType.id} value={shiftType.id}>
                    {shiftType.id} - {shiftType.description}
                  </option>
                ))}
              </select>
            </div>

            <div className="px-6 py-4 border-t border-gray-200 flex justify-end">
              <button
                onClick={closeHistoryEditor}
                className="px-4 py-2 text-gray-600 hover:text-gray-800 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
