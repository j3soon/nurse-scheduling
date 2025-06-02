// The shift type management page for Tab "3. Shift Types"
'use client';

import { useState } from 'react';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import ItemGroupEditorPage from '@/components/ItemGroupEditorPage';
import { Mode } from '@/constants/modes';

export default function ShiftTypePage() {
  const {
    shiftTypeData,
    updateShiftTypeData,
  } = useSchedulingData();

  const [mode, setMode] = useState<Mode>(Mode.NORMAL);

  // Instructions for the help component
  const instructions = [
    "Add different types of shifts (e.g., \"Day (All Levels)\", \"Day (Senior Only)\")",
    "Create groups to organize shift types (e.g., \"Day\", \"Evening\", \"Night\", \"Administrative\")",
    "Click and drag through checkboxes to quickly select multiple groups or shift types when adding or editing",
    "Drag and drop to reorder shift types or groups",
    "Double-click to edit names or descriptions",
    "Navigate using the tabs or keyboard shortcuts (1, 2, etc.) to continue setup"
  ];

  return (
    <ItemGroupEditorPage
      title="Shift Type Management"
      instructions={instructions}
      data={shiftTypeData}
      updateData={updateShiftTypeData}
      itemLabel="Shift Type"
      itemLabelPlural="Shift Types"
      mode={mode}
      setMode={setMode}
    />
  );
}
