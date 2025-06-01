// The people management page for Tab "2. People"
'use client';

import { useState } from 'react';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import ItemGroupEditorPage from '@/components/ItemGroupEditorPage';
import { Mode } from '@/constants/modes';

export default function PeoplePage() {
  const {
    peopleData,
    updatePeopleData,
  } = useSchedulingData();
  
  const [mode, setMode] = useState<Mode>(Mode.NORMAL);
  
  // Instructions for the help component
  const instructions = [
    "Add people who will be scheduled for work (e.g., \"Alice\", \"Bob\", \"Charlie\")",
    "Create groups to organize people (e.g., \"Nurses\", \"Senior Nurses\", \"Contractors\")",
    "Click and drag through checkboxes to quickly select multiple groups or people when adding or editing",
    "Drag and drop to reorder people or groups",
    "Double-click to edit names or descriptions",
    "Navigate using the tabs or keyboard shortcuts (1, 2, etc.) to continue setup"
  ];

  return (
    <ItemGroupEditorPage
      title="People Management"
      instructions={instructions}
      data={peopleData}
      updateData={updatePeopleData}
      itemLabel="Person"
      itemLabelPlural="People"
      mode={mode}
      setMode={setMode}
    />
  );
}
