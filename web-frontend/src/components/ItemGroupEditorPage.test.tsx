/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2026 Johnson Sun
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

// This test is mostly AI generated.

import { ReactNode, useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ItemGroupEditorPage, { ItemGroupEditorPageData } from '@/components/ItemGroupEditorPage';
import { Mode } from '@/constants/modes';
import { DataType, Group, Item } from '@/types/scheduling';
import { getUniqueCopyLabel } from '@/utils/duplicateLabels';
import * as scrolling from '@/utils/scrolling';
import { UnsavedEditingStateProvider } from '@/utils/unsavedEditingState';

function ItemGroupEditorHarness({
  initialData,
  itemsReadOnly = false,
  groupsReadOnly = false,
  instructions = [],
  extraButtons,
  children,
}: {
  initialData?: ItemGroupEditorPageData;
  itemsReadOnly?: boolean;
  groupsReadOnly?: boolean;
  instructions?: string[];
  extraButtons?: ReactNode;
  children?: ReactNode;
}) {
  const [mode, setMode] = useState(Mode.NORMAL);
  const [data, setData] = useState<ItemGroupEditorPageData>({
    ...(initialData || {
      items: [{ id: 'Person 1', description: 'First person', history: [] }],
      groups: [{ id: 'Team A', members: ['Person 1'], description: 'Initial team' }],
      history: [],
    }),
  });

  const addItem = (_dataType: DataType, prev: ItemGroupEditorPageData, id: string, groupIds: string[], description?: string) => {
    setData({
      ...prev,
      items: [...prev.items, { id, description: description || '', history: [] }],
      groups: prev.groups.map(group =>
        groupIds.includes(group.id) ? { ...group, members: [...group.members, id] } : group,
      ),
    });
  };

  const addGroup = (_dataType: DataType, prev: ItemGroupEditorPageData, id: string, memberIds: string[], description?: string) => {
    setData({
      ...prev,
      groups: [...prev.groups, { id, members: memberIds, description: description || '' }],
    });
  };

  const duplicateItem = (_dataType: DataType, prev: ItemGroupEditorPageData, id: string) => {
    const newId = getUniqueCopyLabel(id, [
      ...prev.items.map(item => item.id),
      ...prev.groups.map(group => group.id),
    ]);
    const sourceIndex = prev.items.findIndex(item => item.id === id);
    const sourceItem = prev.items[sourceIndex];
    setData({
      ...prev,
      items: [
        ...prev.items.slice(0, sourceIndex + 1),
        { ...sourceItem, id: newId },
        ...prev.items.slice(sourceIndex + 1),
      ],
      groups: prev.groups.map(group => {
        const memberIndex = group.members.indexOf(id);
        return memberIndex === -1
          ? group
          : {
              ...group,
              members: [
                ...group.members.slice(0, memberIndex + 1),
                newId,
                ...group.members.slice(memberIndex + 1),
              ],
            };
      }),
    });
  };

  const duplicateGroup = (_dataType: DataType, prev: ItemGroupEditorPageData, id: string) => {
    const newId = getUniqueCopyLabel(id, [
      ...prev.items.map(item => item.id),
      ...prev.groups.map(group => group.id),
    ]);
    const sourceIndex = prev.groups.findIndex(group => group.id === id);
    setData({
      ...prev,
      groups: [
        ...prev.groups.slice(0, sourceIndex + 1),
        { ...prev.groups[sourceIndex], id: newId },
        ...prev.groups.slice(sourceIndex + 1),
      ],
    });
  };

  const updateItem = (_dataType: DataType, prev: ItemGroupEditorPageData, oldId: string, newId: string, groupIds?: string[], description?: string) => {
    const updatedItems = prev.items.map(item =>
      item.id === oldId ? { ...item, id: newId, description: description ?? item.description } : item,
    );

    const updatedGroups = prev.groups.map(group => {
      const currentMembers = group.members.filter(member => member !== oldId);
      const shouldInclude = groupIds ? groupIds.includes(group.id) : group.members.includes(oldId);
      return {
        ...group,
        members: shouldInclude ? [...currentMembers, newId] : currentMembers,
      };
    });

    setData({ ...prev, items: updatedItems, groups: updatedGroups });
  };

  const updateGroup = (_dataType: DataType, prev: ItemGroupEditorPageData, oldId: string, newId: string, members?: string[], description?: string) => {
    const updatedGroups = prev.groups.map(group =>
      group.id === oldId
        ? {
            ...group,
            id: newId,
            members: members ?? group.members,
            description: description ?? group.description,
          }
        : group,
    );
    setData({ ...prev, groups: updatedGroups });
  };

  const deleteItem = (_dataType: DataType, prev: ItemGroupEditorPageData, id: string) => {
    setData({
      ...prev,
      items: prev.items.filter(item => item.id !== id),
      groups: prev.groups.map(group => ({ ...group, members: group.members.filter(member => member !== id) })),
    });
  };

  const deleteGroup = (_dataType: DataType, prev: ItemGroupEditorPageData, id: string) => {
    setData({ ...prev, groups: prev.groups.filter(group => group.id !== id) });
  };

  const removeItemFromGroup = (_dataType: DataType, prev: ItemGroupEditorPageData, itemId: string, groupId: string) => {
    setData({
      ...prev,
      groups: prev.groups.map(group =>
        group.id === groupId ? { ...group, members: group.members.filter(member => member !== itemId) } : group,
      ),
    });
  };

  const reorderItems = (_dataType: DataType, prev: ItemGroupEditorPageData, reorderedItems: Item[]) => {
    setData({ ...prev, items: reorderedItems });
  };

  const reorderGroups = (_dataType: DataType, prev: ItemGroupEditorPageData, newGroups: Group[]) => {
    setData({ ...prev, groups: newGroups });
  };

  return (
    <UnsavedEditingStateProvider>
      <ItemGroupEditorPage
        title="People"
        instructions={instructions}
        data={data}
        dataType={DataType.PEOPLE}
        mode={mode}
        setMode={setMode}
        itemsReadOnly={itemsReadOnly}
        groupsReadOnly={groupsReadOnly}
        extraButtons={extraButtons}
        addItem={addItem}
        addGroup={addGroup}
        duplicateItem={duplicateItem}
        duplicateGroup={duplicateGroup}
        updateItem={updateItem}
        updateGroup={updateGroup}
        deleteItem={deleteItem}
        deleteGroup={deleteGroup}
        removeItemFromGroup={removeItemFromGroup}
        reorderItems={reorderItems}
        reorderGroups={reorderGroups}
        filterItemGroups={(entities) => entities}
      >
        {children}
      </ItemGroupEditorPage>
    </UnsavedEditingStateProvider>
  );
}

function createDataTransfer() {
  const store = new Map<string, string>();
  return {
    setData: (key: string, value: string) => store.set(key, value),
    getData: (key: string) => store.get(key) ?? '',
  };
}

describe('ItemGroupEditorPage', () => {
  it('supports add, edit, and delete flow for items', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    await user.click(screen.getByRole('button', { name: /add person/i }));
    await user.type(screen.getByPlaceholderText('Enter person ID'), 'Person 2');
    await user.type(screen.getByPlaceholderText('Enter person description \(optional\)'), 'Second person');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByText('2. Person 2')).toBeInTheDocument();

    const person2Row = screen.getByText('2. Person 2').closest('tr') as HTMLTableRowElement;
    await user.click(within(person2Row).getByRole('button', { name: /edit/i }));

    const idInput = screen.getByDisplayValue('Person 2');
    await user.clear(idInput);
    await user.type(idInput, 'Person 2X');
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('2. Person 2X')).toBeInTheDocument();

    const updatedRow = screen.getByText('2. Person 2X').closest('tr') as HTMLTableRowElement;
    await user.click(within(updatedRow).getByRole('button', { name: /delete/i }));

    expect(screen.queryByText('2. Person 2X')).not.toBeInTheDocument();
  }, 15000);

  it('supports add, edit, and delete flow for groups', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    await user.click(screen.getByRole('button', { name: /add group/i }));
    await user.type(screen.getByPlaceholderText('Enter group ID'), 'Team B');
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByText('Team B')).toBeInTheDocument();

    const teamBRow = screen.getByText('Team B').closest('tr') as HTMLTableRowElement;
    await user.click(within(teamBRow).getByRole('button', { name: /edit/i }));

    const idInput = screen.getByDisplayValue('Team B');
    await user.clear(idInput);
    await user.type(idInput, 'Team C');
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('Team C')).toBeInTheDocument();

    const teamCRow = screen.getByText('Team C').closest('tr') as HTMLTableRowElement;
    await user.click(within(teamCRow).getByRole('button', { name: /delete/i }));

    expect(screen.queryByText('Team C')).not.toBeInTheDocument();
  }, 15000);

  it('duplicates an item under the original with a unique copied ID without opening the form', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    const person1Row = screen.getByText('1. Person 1').closest('tr') as HTMLTableRowElement;
    await user.click(within(person1Row).getByRole('button', { name: /duplicate/i }));

    expect(screen.getByText('1. Person 1')).toBeInTheDocument();
    expect(screen.getByText('2. Person 1 copy')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Enter person ID')).not.toBeInTheDocument();
  });

  it('dismisses the edited item draft before duplicating an item', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    const person1Row = screen.getByText('1. Person 1').closest('tr') as HTMLTableRowElement;
    await user.click(within(person1Row).getByRole('button', { name: /edit/i }));
    await user.clear(screen.getByDisplayValue('Person 1'));
    await user.type(screen.getByPlaceholderText('Enter person ID'), 'Unsaved Person');
    await user.click(within(person1Row).getByRole('button', { name: /duplicate/i }));

    expect(screen.queryByRole('button', { name: 'Update' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Unsaved Person')).not.toBeInTheDocument();
    expect(screen.getByText('1. Person 1')).toBeInTheDocument();
    expect(screen.getByText('2. Person 1 copy')).toBeInTheDocument();
  });

  it('dismisses an added item draft before duplicating an item', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    await user.click(screen.getByRole('button', { name: /add person/i }));
    await user.type(screen.getByPlaceholderText('Enter person ID'), 'Unsaved Person');
    const person1Row = screen.getByText('1. Person 1').closest('tr') as HTMLTableRowElement;
    await user.click(within(person1Row).getByRole('button', { name: /duplicate/i }));

    expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Unsaved Person')).not.toBeInTheDocument();
    expect(screen.getByText('1. Person 1')).toBeInTheDocument();
    expect(screen.getByText('2. Person 1 copy')).toBeInTheDocument();
  });

  it('dismisses the edited item draft before deleting an item', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    const person1Row = screen.getByText('1. Person 1').closest('tr') as HTMLTableRowElement;
    await user.click(within(person1Row).getByRole('button', { name: /edit/i }));
    await user.clear(screen.getByDisplayValue('Person 1'));
    await user.type(screen.getByPlaceholderText('Enter person ID'), 'Unsaved Person');
    await user.click(within(person1Row).getByRole('button', { name: /delete/i }));

    expect(screen.queryByRole('button', { name: 'Update' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Unsaved Person')).not.toBeInTheDocument();
    expect(screen.queryByText('1. Person 1')).not.toBeInTheDocument();
  });

  it('dismisses an added item draft before reordering items', async () => {
    const user = userEvent.setup();

    const { container } = render(
      <ItemGroupEditorHarness
        initialData={{
          items: [
            { id: 'Person 1', description: 'First person', history: [] },
            { id: 'Person 2', description: 'Second person', history: [] },
          ],
          groups: [],
          history: [],
        }}
      />,
    );

    await user.click(screen.getByRole('button', { name: /add person/i }));
    await user.type(screen.getByPlaceholderText('Enter person ID'), 'Unsaved Person');

    const rows = container.querySelectorAll('tbody tr');
    const sourceRow = rows[1] as HTMLTableRowElement;
    const targetRow = rows[0] as HTMLTableRowElement;
    const dataTransfer = createDataTransfer();
    dataTransfer.setData('text/plain', '1');
    fireEvent.dragStart(sourceRow, { dataTransfer });
    fireEvent.drop(targetRow, { dataTransfer, clientY: 0 });

    expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Unsaved Person')).not.toBeInTheDocument();
    expect(screen.getByText('1. Person 2')).toBeInTheDocument();
    expect(screen.getByText('2. Person 1')).toBeInTheDocument();
  });

  it('disables item reordering while inline editing', async () => {
    const user = userEvent.setup();

    const { container } = render(
      <ItemGroupEditorHarness
        initialData={{
          items: [
            { id: 'Person 1', description: 'First person', history: [] },
            { id: 'Person 2', description: 'Second person', history: [] },
          ],
          groups: [],
          history: [],
        }}
      />,
    );

    await user.dblClick(screen.getByText('1. Person 1'));

    const rows = container.querySelectorAll('tbody tr');
    expect(rows[0]).not.toHaveAttribute('draggable', 'true');
    expect(rows[1]).not.toHaveAttribute('draggable', 'true');

    const input = screen.getByDisplayValue('Person 1');
    fireEvent.keyDown(input, { key: 'Enter' });

    const reorderedRows = container.querySelectorAll('tbody tr');
    expect(reorderedRows[0]).toHaveAttribute('draggable', 'true');
    expect(reorderedRows[1]).toHaveAttribute('draggable', 'true');
  });

  it('disables group reordering while inline editing', async () => {
    const user = userEvent.setup();

    const { container } = render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'Person 1', description: 'First person', history: [] }],
          groups: [
            { id: 'Team A', members: ['Person 1'], description: 'Initial team' },
            { id: 'Team B', members: [], description: 'Backup team' },
          ],
          history: [],
        }}
      />,
    );

    const tables = container.querySelectorAll('table');
    const groupRows = tables[1].querySelectorAll('tbody tr');
    await user.dblClick(within(groupRows[0]).getByTitle('Team A'));

    expect(groupRows[0]).not.toHaveAttribute('draggable', 'true');
    expect(groupRows[1]).not.toHaveAttribute('draggable', 'true');

    const input = screen.getByDisplayValue('Team A');
    fireEvent.keyDown(input, { key: 'Enter' });

    const reorderedGroupRows = tables[1].querySelectorAll('tbody tr');
    expect(reorderedGroupRows[0]).toHaveAttribute('draggable', 'true');
    expect(reorderedGroupRows[1]).toHaveAttribute('draggable', 'true');
  });

  it('increments copied item IDs when the first copy name already exists', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [
            { id: 'Person 1', description: 'First person', history: [] },
            { id: 'Person 1 copy', description: 'Existing copy', history: [] },
          ],
          groups: [{ id: 'Team A', members: ['Person 1'], description: 'Initial team' }],
          history: [],
        }}
      />,
    );

    const person1Row = screen.getByText('1. Person 1').closest('tr') as HTMLTableRowElement;
    await user.click(within(person1Row).getByRole('button', { name: /duplicate/i }));

    expect(screen.getByText('1. Person 1')).toBeInTheDocument();
    expect(screen.getByText('2. Person 1 copy 2')).toBeInTheDocument();
    expect(screen.getByText('3. Person 1 copy')).toBeInTheDocument();
  });

  it('duplicates a group under the original with copied members', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    const teamARow = screen.getByTitle('Team A').closest('tr') as HTMLTableRowElement;
    await user.click(within(teamARow).getByRole('button', { name: /duplicate/i }));

    expect(screen.getByTitle('Team A')).toBeInTheDocument();
    expect(screen.getByTitle('Team A copy')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Enter group ID')).not.toBeInTheDocument();
  });

  it('hides add actions in read-only modes', () => {
    render(<ItemGroupEditorHarness itemsReadOnly={true} groupsReadOnly={true} />);

    expect(screen.queryByRole('button', { name: /add person/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add group/i })).not.toBeInTheDocument();
  });

  it('keeps person actions available while groups are read-only', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness groupsReadOnly={true} />);

    expect(screen.getByRole('button', { name: /add person/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /add group/i })).not.toBeInTheDocument();

    await user.dblClick(screen.getByTitle('Team A'));
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /add person/i }));
    expect(screen.getByPlaceholderText('Enter person ID')).toBeInTheDocument();
  });

  it('keeps group actions available while items are read-only', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness itemsReadOnly={true} />);

    expect(screen.queryByRole('button', { name: /add person/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add group/i })).toBeInTheDocument();

    await user.dblClick(screen.getByText('1. Person 1'));
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /add group/i }));
    expect(screen.getByPlaceholderText('Enter group ID')).toBeInTheDocument();
  });

  it('does not enter group inline edit mode on double-click when groups are read-only', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness groupsReadOnly={true} />);

    await user.dblClick(screen.getByTitle('Team A'));
    await user.dblClick(screen.getByText('Initial team'));

    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Team A')).not.toBeInTheDocument();
  });

  it('shows auto indicator and hides edit/delete for auto-generated rows', () => {
    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'AUTO_PERSON', description: '', isAutoGenerated: true, history: [] }],
          groups: [{ id: 'AUTO_GROUP', members: ['AUTO_PERSON'], description: '', isAutoGenerated: true }],
          history: [],
        }}
      />,
    );

    // One auto row in each table.
    expect(screen.getAllByText('Auto')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });

  it('validates empty, reserved, and duplicate IDs when adding an item', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'Person 1', description: '', history: [] }],
          groups: [{ id: 'ALL', members: ['Person 1'], description: '', isAutoGenerated: true }],
          history: [],
        }}
      />,
    );

    await user.click(screen.getByRole('button', { name: /add person/i }));

    await user.click(screen.getByRole('button', { name: 'Add' }));
    expect(screen.getByText('Person ID cannot be empty')).toBeInTheDocument();

    const idInput = screen.getByPlaceholderText('Enter person ID');
    await user.type(idInput, 'ALL');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    expect(screen.getByText('"ALL" is a reserved keyword and cannot be used as an ID')).toBeInTheDocument();

    await user.clear(idInput);
    await user.type(idInput, 'Person 1');
    await user.click(screen.getByRole('button', { name: 'Add' }));
    expect(screen.getByText('This ID is already used by another person or group')).toBeInTheDocument();
  });

  it('submits on Enter and cancels on Escape when the form is visible', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    await user.click(screen.getByRole('button', { name: /add person/i }));
    await user.type(screen.getByPlaceholderText('Enter person ID'), 'Person Enter');
    fireEvent.keyDown(document, { key: 'Enter' });

    expect(screen.getByText('2. Person Enter')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Enter person ID')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /add person/i }));
    expect(screen.getByPlaceholderText('Enter person ID')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByPlaceholderText('Enter person ID')).not.toBeInTheDocument();
  });

  it('toggles add form off when clicking the same add button twice', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    await user.click(screen.getByRole('button', { name: /add person/i }));
    expect(screen.getByPlaceholderText('Enter person ID')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /add person/i }));
    expect(screen.queryByPlaceholderText('Enter person ID')).not.toBeInTheDocument();
  });

  it('toggles group add form off when clicking the same add button twice', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    await user.click(screen.getByRole('button', { name: /add group/i }));
    expect(screen.getByPlaceholderText('Enter group ID')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /add group/i }));
    expect(screen.queryByPlaceholderText('Enter group ID')).not.toBeInTheDocument();
  });

  it('does not open inline editor on read-only or auto-generated rows', async () => {
    const user = userEvent.setup();

    const { unmount } = render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'Person 1', description: '', history: [] }],
          groups: [{ id: 'Team A', members: ['Person 1'], description: '' }],
          history: [],
        }}
        itemsReadOnly={true}
      />,
    );

    await user.dblClick(screen.getByText('1. Person 1'));
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();

    unmount();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'AUTO_PERSON', description: '', history: [], isAutoGenerated: true }],
          groups: [{ id: 'AUTO_GROUP', members: ['AUTO_PERSON'], description: '', isAutoGenerated: true }],
          history: [],
        }}
      />,
    );

    await user.dblClick(screen.getByText('1. AUTO_PERSON'));
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
  });

  it('suppresses inline edit for auto-generated IDs and descriptions across both items and groups', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'AUTO_PERSON', description: 'Generated person', history: [], isAutoGenerated: true }],
          groups: [{ id: 'AUTO_GROUP', members: ['AUTO_PERSON'], description: 'Generated group', isAutoGenerated: true }],
          history: [],
        }}
      />,
    );

    await user.dblClick(screen.getByText('1. AUTO_PERSON'));
    await user.dblClick(screen.getByText('Generated person'));
    await user.dblClick(screen.getByTitle('AUTO_GROUP'));
    await user.dblClick(screen.getByText('Generated group'));

    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('AUTO_PERSON')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Generated person')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('AUTO_GROUP')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Generated group')).not.toBeInTheDocument();
  });

  it('renders instructions, children, and extra buttons when provided', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        instructions={['Use stable IDs', 'Avoid duplicates']}
        extraButtons={<button type="button">Extra Action</button>}
      >
        <div>Child Content</div>
      </ItemGroupEditorHarness>,
    );

    expect(screen.getByText('Child Content')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Extra Action' })).toBeInTheDocument();
    expect(screen.queryByText('Instructions')).not.toBeInTheDocument();

    await user.click(screen.getByTitle('Toggle instructions'));
    expect(screen.getByText('Instructions')).toBeInTheDocument();
    expect(screen.getByText('• Use stable IDs')).toBeInTheDocument();
    expect(screen.getByText('• Avoid duplicates')).toBeInTheDocument();
  });

  it('removes item membership from groups via removable tag action', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'Person 1', description: '', history: [] }],
          groups: [{ id: 'Team A', members: ['Person 1'], description: '' }],
          history: [],
        }}
      />,
    );

    await user.click(screen.getByTitle('Remove "Team A"'));

    expect(screen.getByText('0 groups')).toBeInTheDocument();
    expect(screen.getByText('0 members')).toBeInTheDocument();
  });

  it('dismisses an added item draft before removing membership via removable tag action', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'Person 1', description: '', history: [] }],
          groups: [{ id: 'Team A', members: ['Person 1'], description: '' }],
          history: [],
        }}
      />,
    );

    await user.click(screen.getByRole('button', { name: /add person/i }));
    await user.type(screen.getByPlaceholderText('Enter person ID'), 'Unsaved Person');
    await user.click(screen.getByTitle('Remove "Team A"'));

    expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Unsaved Person')).not.toBeInTheDocument();
    expect(screen.getByText('0 groups')).toBeInTheDocument();
    expect(screen.getByText('0 members')).toBeInTheDocument();
  });

  it('removes group membership via member-side removable tag action', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'Person 1', description: '', history: [] }],
          groups: [{ id: 'Team A', members: ['Person 1'], description: '' }],
          history: [],
        }}
      />,
    );

    await user.click(screen.getByTitle('Remove "Person 1"'));

    expect(screen.getByText('0 groups')).toBeInTheDocument();
    expect(screen.getByText('0 members')).toBeInTheDocument();
  });

  it('updates item group membership through the edit form checkboxes', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'Person 1', description: '', history: [] }],
          groups: [
            { id: 'Team A', members: ['Person 1'], description: '' },
            { id: 'Team B', members: [], description: '' },
          ],
          history: [],
        }}
      />,
    );

    const personRow = screen.getByText('1. Person 1').closest('tr') as HTMLTableRowElement;
    await user.click(within(personRow).getByRole('button', { name: /edit/i }));
    await user.click(screen.getByLabelText('Team A'));
    await user.click(screen.getByLabelText('Team B'));
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('1 group')).toBeInTheDocument();
    expect(screen.queryByTitle('Remove "Team A"')).not.toBeInTheDocument();
    expect(screen.getByTitle('Remove "Team B"')).toBeInTheDocument();
  });

  it('updates group members through the edit form checkboxes', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [
            { id: 'Person 1', description: '', history: [] },
            { id: 'Person 2', description: '', history: [] },
          ],
          groups: [{ id: 'Team A', members: ['Person 1'], description: '' }],
          history: [],
        }}
      />,
    );

    const groupRow = screen.getByTitle('Team A').closest('tr') as HTMLTableRowElement;
    await user.click(within(groupRow).getByRole('button', { name: /edit/i }));
    await user.click(screen.getByLabelText('Person 1'));
    await user.click(screen.getByLabelText('Person 2'));
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('1 member')).toBeInTheDocument();
    expect(screen.queryByTitle('Remove "Person 1"')).not.toBeInTheDocument();
    expect(screen.getByTitle('Remove "Person 2"')).toBeInTheDocument();
  });

  it('shows inline validation error for reserved group ID edits', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'Person 1', description: '', history: [] }],
          groups: [{ id: 'Team A', members: ['Person 1'], description: '' }],
          history: [],
        }}
      />,
    );

    await user.dblClick(screen.getByTitle('Team A'));
    const input = screen.getByDisplayValue('Team A');
    await user.clear(input);
    await user.type(input, 'ALL');
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(input).toHaveClass('border-red-500');
  });

  it('shows inline validation error for empty item ID edits', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    await user.dblClick(screen.getByText('1. Person 1'));
    const input = screen.getByDisplayValue('Person 1');
    await user.clear(input);
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(input).toHaveValue('');
    expect(input).toHaveClass('border-red-500');
  });

  it('shows inline validation error for duplicate group ID edits', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'Person 1', description: '', history: [] }],
          groups: [
            { id: 'Team A', members: ['Person 1'], description: '' },
            { id: 'Team B', members: [], description: '' },
          ],
          history: [],
        }}
      />,
    );

    await user.dblClick(screen.getByTitle('Team A'));
    const input = screen.getByDisplayValue('Team A');
    await user.clear(input);
    await user.type(input, 'Team B');
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(screen.getByDisplayValue('Team B')).toBeInTheDocument();
    expect(input).toHaveClass('border-red-500');
  });

  it('blocks renaming a person to an existing group ID', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    const personRow = screen.getByText('1. Person 1').closest('tr') as HTMLTableRowElement;
    await user.click(within(personRow).getByRole('button', { name: /edit/i }));

    const idInput = screen.getByDisplayValue('Person 1');
    await user.clear(idInput);
    await user.type(idInput, 'Team A');
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('This ID is already used by another person or group')).toBeInTheDocument();
    expect(screen.getByText('1. Person 1')).toBeInTheDocument();
    expect(screen.getAllByText('Team A').length).toBeGreaterThan(0);
  });

  it('blocks renaming a group to an existing person ID', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    const groupRow = screen.getByTitle('Team A').closest('tr') as HTMLTableRowElement;
    await user.click(within(groupRow).getByRole('button', { name: /edit/i }));

    const idInput = screen.getByDisplayValue('Team A');
    await user.clear(idInput);
    await user.type(idInput, 'Person 1');
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('This ID is already used by another person or group')).toBeInTheDocument();
    expect(screen.getAllByText('Team A').length).toBeGreaterThan(0);
    expect(screen.getByText('1. Person 1')).toBeInTheDocument();
  });

  it('logs and blocks adding when read-only add actions are triggered programmatically', async () => {
    const user = userEvent.setup();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(<ItemGroupEditorHarness itemsReadOnly={true} groupsReadOnly={true} />);

    fireEvent.keyDown(document, { key: 'Enter' });
    await user.keyboard('{Escape}');

    expect(screen.queryByPlaceholderText('Enter person ID')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Enter group ID')).not.toBeInTheDocument();
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('keeps auto-generated group actions unavailable and ignores member removal affordance', () => {
    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [{ id: 'Person 1', description: '', history: [] }],
          groups: [{ id: 'AUTO_GROUP', members: ['Person 1'], description: '', isAutoGenerated: true }],
          history: [],
        }}
      />,
    );

    const autoGroupRow = screen.getByTitle('AUTO_GROUP').closest('tr') as HTMLTableRowElement;
    expect(within(autoGroupRow).queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
    expect(within(autoGroupRow).queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
    expect(screen.queryByTitle('Remove "AUTO_GROUP"')).not.toBeInTheDocument();
  });

  it('saves scroll position when starting form edit and restores it on cancel', async () => {
    const user = userEvent.setup();
    const saveSpy = vi.spyOn(scrolling, 'saveScrollPosition').mockImplementation(() => undefined);
    const restoreSpy = vi.spyOn(scrolling, 'restoreScrollPosition').mockImplementation(() => undefined);
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);

    render(<ItemGroupEditorHarness />);

    const personRow = screen.getByText('1. Person 1').closest('tr') as HTMLTableRowElement;
    await user.click(within(personRow).getByRole('button', { name: /edit/i }));
    expect(saveSpy).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(restoreSpy).toHaveBeenCalledTimes(1);
  });

  it('saves inline description edits on Enter and clears inline mode', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    await user.dblClick(screen.getByText('First person'));
    const input = screen.getByDisplayValue('First person');
    await user.clear(input);
    await user.type(input, 'Updated description');
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(screen.getByText('Updated description')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('Updated description')).not.toBeInTheDocument();
  });

  it('saves group inline description edits on Enter and clears inline mode', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    await user.dblClick(screen.getByText('Initial team'));
    const input = screen.getByDisplayValue('Initial team');
    await user.clear(input);
    await user.type(input, 'Updated team description');
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(screen.getByText('Updated team description')).toBeInTheDocument();
    expect(screen.queryByDisplayValue('Updated team description')).not.toBeInTheDocument();
  });

  it('keeps inline duplicate-ID errors until Escape cancels the inline edit', async () => {
    const user = userEvent.setup();

    render(<ItemGroupEditorHarness />);

    await user.dblClick(screen.getByText('1. Person 1'));
    const input = screen.getByDisplayValue('Person 1');
    await user.clear(input);
    await user.type(input, 'Team A');
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(screen.getByDisplayValue('Team A')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Team A')).toHaveClass('border-red-500');

    fireEvent.keyDown(input, { key: 'Escape' });

    expect(screen.queryByDisplayValue('Team A')).not.toBeInTheDocument();
    expect(screen.getByText('1. Person 1')).toBeInTheDocument();
  });

  it('invokes scroll helper lifecycle when canceling add mode', async () => {
    const user = userEvent.setup();
    const saveSpy = vi.spyOn(scrolling, 'saveScrollPosition').mockImplementation(() => undefined);
    const restoreSpy = vi.spyOn(scrolling, 'restoreScrollPosition').mockImplementation(() => undefined);

    render(<ItemGroupEditorHarness />);

    await user.click(screen.getByRole('button', { name: /add person/i }));
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(saveSpy).toHaveBeenCalledTimes(1);
    expect(restoreSpy).toHaveBeenCalledTimes(1);
  });

  it('propagates group rename through rendered mixed references on the page', async () => {
    const user = userEvent.setup();

    render(
      <ItemGroupEditorHarness
        initialData={{
          items: [
            { id: 'P1', description: '', history: [] },
            { id: 'P2', description: '', history: [] },
          ],
          groups: [{ id: 'Group 1', members: ['P1', 'P2'], description: '' }],
          history: [],
        }}
      />,
    );

    const groupRow = screen.getByTitle('Group 1').closest('tr') as HTMLTableRowElement;
    await user.click(within(groupRow).getByRole('button', { name: /edit/i }));
    const idInput = screen.getByDisplayValue('Group 1');
    await user.clear(idInput);
    await user.type(idInput, 'Group X');
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByTitle('Group X')).toBeInTheDocument();
    expect(screen.queryByTitle('Group 1')).not.toBeInTheDocument();
    expect(screen.getAllByTitle('Remove "Group X"')).toHaveLength(2);
  });
});
