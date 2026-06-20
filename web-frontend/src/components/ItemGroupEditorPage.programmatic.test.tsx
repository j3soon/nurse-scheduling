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

import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DataType } from '@/types/scheduling';
import { Mode } from '@/constants/modes';
import ItemGroupEditorPage, { ItemGroupEditorPageData } from '@/components/ItemGroupEditorPage';
import { UnsavedEditingStateProvider } from '@/utils/unsavedEditingState';

let latestItemEdit: ((id: string) => void) | undefined;
let latestItemDelete: ((id: string) => void) | undefined;
let latestGroupEdit: ((id: string) => void) | undefined;
let latestGroupDelete: ((id: string) => void) | undefined;

vi.mock('@/components/TableColumns', () => ({
  useItemTableColumns: ({
    onEdit,
    onDelete,
  }: {
    onEdit: (id: string) => void;
    onDelete: (id: string) => void;
  }) => {
    latestItemEdit = onEdit;
    latestItemDelete = onDelete;
    return [
      { header: 'ID', accessor: (item: { id: string }) => <span>{item.id}</span> },
      {
        header: 'Actions',
        accessor: (item: { id: string }) => (
          <div>
            <button type="button" onClick={() => onEdit(item.id)}>
              Programmatic Edit {item.id}
            </button>
            <button type="button" onClick={() => onDelete(item.id)}>
              Programmatic Delete {item.id}
            </button>
          </div>
        ),
      },
    ];
  },
  useGroupTableColumns: ({
    onEdit,
    onDelete,
  }: {
    onEdit: (id: string) => void;
    onDelete: (id: string) => void;
  }) => {
    latestGroupEdit = onEdit;
    latestGroupDelete = onDelete;
    return [
      { header: 'ID', accessor: (group: { id: string }) => <span>{group.id}</span> },
      {
        header: 'Actions',
        accessor: (group: { id: string }) => (
          <div>
            <button type="button" onClick={() => onEdit(group.id)}>
              Programmatic Edit {group.id}
            </button>
            <button type="button" onClick={() => onDelete(group.id)}>
              Programmatic Delete {group.id}
            </button>
          </div>
        ),
      },
    ];
  },
}));

function Harness({
  initialData,
  itemsReadOnly = false,
  groupsReadOnly = false,
}: {
  initialData: ItemGroupEditorPageData;
  itemsReadOnly?: boolean;
  groupsReadOnly?: boolean;
}) {
  const [mode, setMode] = useState(Mode.NORMAL);
  const [data, setData] = useState<ItemGroupEditorPageData>(initialData);

  return (
    <UnsavedEditingStateProvider>
      <ItemGroupEditorPage
        title="People"
        instructions={[]}
        data={data}
        dataType={DataType.PEOPLE}
        mode={mode}
        setMode={setMode}
        itemsReadOnly={itemsReadOnly}
        groupsReadOnly={groupsReadOnly}
        addItem={vi.fn()}
        addGroup={vi.fn()}
        duplicateItem={vi.fn()}
        duplicateGroup={vi.fn()}
        updateItem={vi.fn()}
        updateGroup={vi.fn()}
        deleteItem={(_dataType, prev, id) => setData({ ...prev, items: prev.items.filter(item => item.id !== id) })}
        deleteGroup={(_dataType, prev, id) => setData({ ...prev, groups: prev.groups.filter(group => group.id !== id) })}
        removeItemFromGroup={vi.fn()}
        reorderItems={vi.fn()}
        reorderGroups={vi.fn()}
        filterItemGroups={(entities) => entities}
        extraButtons={
          <div>
            <button type="button" onClick={() => latestItemEdit?.('Person 1')}>
              Programmatic Edit Missing Person 1
            </button>
            <button type="button" onClick={() => latestItemDelete?.('Person 1')}>
              Programmatic Delete Missing Person 1
            </button>
            <button type="button" onClick={() => latestGroupEdit?.('Team A')}>
              Programmatic Edit Missing Team A
            </button>
            <button type="button" onClick={() => latestGroupDelete?.('Team A')}>
              Programmatic Delete Missing Team A
            </button>
          </div>
        }
      />
    </UnsavedEditingStateProvider>
  );
}

describe('ItemGroupEditorPage programmatic guards', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    latestItemEdit = undefined;
    latestItemDelete = undefined;
    latestGroupEdit = undefined;
    latestGroupDelete = undefined;
  });

  it('logs and blocks programmatic delete attempts for read-only and auto-generated rows', async () => {
    const user = userEvent.setup();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(
      <Harness
        itemsReadOnly={true}
        groupsReadOnly={true}
        initialData={{
          items: [
            { id: 'Person 1', description: '', history: [] },
            { id: 'AUTO_PERSON', description: '', history: [], isAutoGenerated: true },
          ],
          groups: [
            { id: 'Team A', members: ['Person 1'], description: '' },
            { id: 'AUTO_GROUP', members: ['AUTO_PERSON'], description: '', isAutoGenerated: true },
          ],
          history: [],
        }}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Programmatic Delete Person 1' }));
    await user.click(screen.getByRole('button', { name: 'Programmatic Delete Team A' }));
    await user.click(screen.getByRole('button', { name: 'Programmatic Delete AUTO_PERSON' }));
    await user.click(screen.getByRole('button', { name: 'Programmatic Delete AUTO_GROUP' }));

    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining('Cannot delete person Person 1 - items are read-only.'),
    );
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining('Cannot delete group Team A - groups are read-only.'),
    );
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining('Cannot delete person AUTO_PERSON - items are read-only.'),
    );
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining('Cannot delete group AUTO_GROUP - groups are read-only.'),
    );
    expect(screen.getByText('Person 1')).toBeInTheDocument();
    expect(screen.getByText('Team A')).toBeInTheDocument();
    expect(screen.getByText('AUTO_PERSON')).toBeInTheDocument();
    expect(screen.getByText('AUTO_GROUP')).toBeInTheDocument();
  });

  it('logs and blocks programmatic edit attempts for read-only and auto-generated rows', async () => {
    const user = userEvent.setup();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(
      <Harness
        initialData={{
          items: [
            { id: 'Person 1', description: '', history: [] },
            { id: 'AUTO_PERSON', description: '', history: [], isAutoGenerated: true },
          ],
          groups: [
            { id: 'Team A', members: ['Person 1'], description: '' },
            { id: 'AUTO_GROUP', members: ['AUTO_PERSON'], description: '', isAutoGenerated: true },
          ],
          history: [],
        }}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Programmatic Edit AUTO_PERSON' }));
    await user.click(screen.getByRole('button', { name: 'Programmatic Edit AUTO_GROUP' }));

    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining('Cannot edit auto-generated person AUTO_PERSON.'),
    );
    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining('Cannot edit auto-generated group AUTO_GROUP.'),
    );
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
  });

  it('ignores programmatic delete attempts for missing entities without recreating rows', async () => {
    const user = userEvent.setup();

    render(
      <Harness
        initialData={{
          items: [{ id: 'Person 1', description: '', history: [] }],
          groups: [{ id: 'Team A', members: ['Person 1'], description: '' }],
          history: [],
        }}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Programmatic Delete Person 1' }));
    expect(screen.queryByText('Person 1')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Programmatic Delete Missing Person 1' }));
    await user.click(screen.getByRole('button', { name: 'Programmatic Delete Team A' }));
    expect(screen.queryByText('Team A')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Programmatic Delete Missing Team A' }));
    expect(screen.queryByText('Person 1')).not.toBeInTheDocument();
    expect(screen.queryByText('Team A')).not.toBeInTheDocument();
  });

  it('logs and ignores programmatic edit attempts for missing entities', async () => {
    const user = userEvent.setup();
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(
      <Harness
        initialData={{
          items: [{ id: 'Person 1', description: '', history: [] }],
          groups: [{ id: 'Team A', members: ['Person 1'], description: '' }],
          history: [],
        }}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Programmatic Delete Person 1' }));
    await user.click(screen.getByRole('button', { name: 'Programmatic Edit Missing Person 1' }));
    await user.click(screen.getByRole('button', { name: 'Programmatic Delete Team A' }));
    await user.click(screen.getByRole('button', { name: 'Programmatic Edit Missing Team A' }));

    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining('Group with ID Team A not found during edit.'),
    );
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();
  });
});
