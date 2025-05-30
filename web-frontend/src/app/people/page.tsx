'use client';

import { useScheduling } from '@/contexts/SchedulingContexts';
import ManagementPage from '@/components/ManagementPage';

export default function PeoplePage() {
  const {
    people: items,
    peopleGroups: groups,
    addPerson: addItem,
    addPeopleGroup: addGroup,
    updatePerson: updateItem,
    updatePeopleGroup: updateGroup,
    deletePerson: deleteItem,
    deletePeopleGroup: deleteGroup,
    removePersonFromGroup: removeItemFromGroup,
    reorderPeople: reorderItems,
    updatePeopleGroups: updateGroups,
  } = useScheduling();

  return (
    <ManagementPage
      title="People Management"
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
      itemLabel="Person"
      itemLabelPlural="People"
      groupLabel="Group"
      groupLabelPlural="Groups"
    />
  );
}
