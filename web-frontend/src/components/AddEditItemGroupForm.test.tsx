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

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AddEditItemGroupForm } from '@/components/AddEditItemGroupForm';
import { Mode } from '@/constants/modes';

describe('AddEditItemGroupForm', () => {
  it('renders item-mode labels and selected groups through the checkbox list', () => {
    render(
      <AddEditItemGroupForm
        mode={Mode.ADDING}
        draft={{
          id: 'P1',
          description: 'Primary person',
          groups: ['Team A'],
          members: [],
          isItem: true,
        }}
        items={[{ id: 'P1', description: 'Primary person' }]}
        groups={[
          { id: 'Team A', description: 'Primary team', members: ['P1'] },
          { id: 'Team B', description: 'Secondary team', members: [] },
        ]}
        itemLabel="Person"
        itemLabelPlural="People"
        error=""
        filterItemGroups={(entries) => entries}
        onIdChange={() => undefined}
        onDescriptionChange={() => undefined}
        onMemberToggle={() => undefined}
        onSave={() => undefined}
        onCancel={() => undefined}
      />,
    );

    expect(screen.getByText('Add New Person')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter person ID')).toBeInTheDocument();
    expect(screen.getByText('Groups')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Team A/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /Team B/ })).not.toBeChecked();
  });

  it('renders group-mode labels and selected members through the checkbox list', () => {
    render(
      <AddEditItemGroupForm
        mode={Mode.EDITING}
        draft={{
          id: 'Team A',
          description: 'Primary team',
          groups: [],
          members: ['P1'],
          isItem: false,
        }}
        items={[
          { id: 'P1', description: 'Primary person' },
          { id: 'P2', description: 'Secondary person' },
        ]}
        groups={[{ id: 'Team A', description: 'Primary team', members: ['P1'] }]}
        itemLabel="Person"
        itemLabelPlural="People"
        error=""
        filterItemGroups={(entries) => entries}
        onIdChange={() => undefined}
        onDescriptionChange={() => undefined}
        onMemberToggle={() => undefined}
        onSave={() => undefined}
        onCancel={() => undefined}
      />,
    );

    expect(screen.getByText('Edit Group')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Enter group ID')).toBeInTheDocument();
    expect(screen.getByText('Members')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /P1/ })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /P2/ })).not.toBeChecked();
  });

  it('wires change, toggle, save, and cancel handlers through the shared form', async () => {
    const user = userEvent.setup();
    const onIdChange = vi.fn();
    const onDescriptionChange = vi.fn();
    const onMemberToggle = vi.fn();
    const onSave = vi.fn();
    const onCancel = vi.fn();

    render(
      <AddEditItemGroupForm
        mode={Mode.ADDING}
        draft={{
          id: '',
          description: '',
          groups: [],
          members: [],
          isItem: true,
        }}
        items={[]}
        groups={[{ id: 'Team A', description: 'Primary team', members: [] }]}
        itemLabel="Person"
        itemLabelPlural="People"
        error=""
        filterItemGroups={(entries) => entries}
        onIdChange={onIdChange}
        onDescriptionChange={onDescriptionChange}
        onMemberToggle={onMemberToggle}
        onSave={onSave}
        onCancel={onCancel}
      />,
    );

    await user.type(screen.getByPlaceholderText('Enter person ID'), 'PX');
    await user.type(screen.getByPlaceholderText('Enter person description (optional)'), 'Desc');
    await user.click(screen.getByRole('checkbox', { name: /Team A/ }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(onIdChange).toHaveBeenCalled();
    expect(onDescriptionChange).toHaveBeenCalled();
    expect(onMemberToggle).toHaveBeenCalledWith('Team A');
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['Date', 'Dates'],
    ['Person', 'People'],
    ['Shift Type', 'Shift Types'],
  ])('shows a setup hint when a group has no available %s members', (itemLabel, itemLabelPlural) => {
    const renderGroupMemberSelector = vi.fn();

    render(
      <AddEditItemGroupForm
        mode={Mode.ADDING}
        draft={{
          id: '',
          description: '',
          groups: [],
          members: [],
          isItem: false,
        }}
        items={[]}
        groups={[]}
        itemLabel={itemLabel}
        itemLabelPlural={itemLabelPlural}
        error=""
        filterItemGroups={(entries) => entries}
        renderGroupMemberSelector={renderGroupMemberSelector}
        onIdChange={() => undefined}
        onDescriptionChange={() => undefined}
        onMemberToggle={() => undefined}
        onSave={() => undefined}
        onCancel={() => undefined}
      />,
    );

    expect(screen.getByText(
      `No ${itemLabelPlural.toLowerCase()} available. Please set up ${itemLabelPlural.toLowerCase()} first.`,
    )).toBeInTheDocument();
    expect(renderGroupMemberSelector).not.toHaveBeenCalled();
  });

  it('shows a setup hint when an item has no available groups', () => {
    render(
      <AddEditItemGroupForm
        mode={Mode.ADDING}
        draft={{
          id: '',
          description: '',
          groups: [],
          members: [],
          isItem: true,
        }}
        items={[{ id: 'P1', description: 'Primary person' }]}
        groups={[]}
        itemLabel="Person"
        itemLabelPlural="People"
        error=""
        filterItemGroups={(entries) => entries}
        onIdChange={() => undefined}
        onDescriptionChange={() => undefined}
        onMemberToggle={() => undefined}
        onSave={() => undefined}
        onCancel={() => undefined}
      />,
    );

    expect(screen.getByText('Groups')).toBeInTheDocument();
    expect(screen.getByText('No groups available.')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });
});
