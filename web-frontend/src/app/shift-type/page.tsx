'use client';

import { useScheduling } from '@/contexts/SchedulingContexts';
import ManagementPage from '@/components/ManagementPage';

export default function ShiftTypePage() {
  const {
    shiftTypes: items,
    shiftTypeGroups: groups,
    addShiftType: addItem,
    addShiftTypeGroup: addGroup,
    updateShiftType: updateItem,
    updateShiftTypeGroup: updateGroup,
    deleteShiftType: deleteItem,
    deleteShiftTypeGroup: deleteGroup,
    removeShiftTypeFromGroup: removeItemFromGroup,
    reorderShiftTypes: reorderItems,
    updateShiftTypeGroups: updateGroups,
  } = useScheduling();

  return (
    <ManagementPage
      title="Shift Type Management"
      items={items}
      groups={groups}
      addItem={addItem}
      addGroup={addGroup}
      updateItem={updateItem}
      updateGroup={updateGroup}
      deleteItem={deleteItem}
      deleteGroup={deleteGroup}
      removeItemFromGroup={removeItemFromGroup}
      reorderItems={reorderItems}
      updateGroups={updateGroups}
      itemLabel="Shift Type"
      groupLabel="Shift Types Group"
    />
  );
}
