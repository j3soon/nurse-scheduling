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

import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';
import { DateGroupMemberSelector } from '@/components/DateGroupMemberSelector';

const mayItems = Array.from({ length: 31 }, (_, index) => ({
  id: String(index + 1).padStart(2, '0'),
  description: `May ${index + 1}`,
}));

function StatefulSelector() {
  const [selectedIds, setSelectedIds] = useState(['01']);

  return (
    <DateGroupMemberSelector
      dateRange={{
        startDate: new Date('2026-05-01'),
        endDate: new Date('2026-05-31'),
      }}
      items={mayItems}
      selectedIds={selectedIds}
      onToggle={(id) => setSelectedIds(current => current.includes(id)
        ? current.filter(selectedId => selectedId !== id)
        : [...current, id])}
    />
  );
}

describe('DateGroupMemberSelector', () => {
  it('renders a calendar for a full calendar month and toggles a date', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();

    render(
      <DateGroupMemberSelector
        dateRange={{
          startDate: new Date('2026-05-01'),
          endDate: new Date('2026-05-31'),
        }}
        items={mayItems}
        selectedIds={['01']}
        onToggle={onToggle}
      />,
    );

    expect(screen.getByText('May 2026')).toBeInTheDocument();
    expect(screen.getByText('Sun')).toBeInTheDocument();
    expect(screen.getByLabelText('01')).toBeChecked();

    await user.click(screen.getByLabelText('02'));

    expect(onToggle).toHaveBeenCalledWith('02');
  });

  it('preserves drag selection across calendar dates', () => {
    const onToggle = vi.fn();

    render(
      <DateGroupMemberSelector
        dateRange={{
          startDate: new Date('2026-05-01'),
          endDate: new Date('2026-05-31'),
        }}
        items={mayItems}
        selectedIds={[]}
        onToggle={onToggle}
      />,
    );

    const first = screen.getByText('01').closest('label') as HTMLLabelElement;
    const second = screen.getByText('02').closest('label') as HTMLLabelElement;
    fireEvent.mouseEnter(first);
    fireEvent.mouseDown(first, { button: 0 });
    fireEvent.mouseLeave(first);
    fireEvent.mouseEnter(second);
    fireEvent.mouseUp(second, { button: 0 });

    expect(onToggle).toHaveBeenNthCalledWith(1, '01');
    expect(onToggle).toHaveBeenNthCalledWith(2, '02');
  });

  it('preserves selections when switching between calendar and list views', async () => {
    const user = userEvent.setup();

    render(<StatefulSelector />);

    expect(screen.getByRole('button', { name: 'Calendar view' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('01')).toBeChecked();

    await user.click(screen.getByRole('button', { name: 'List view' }));
    expect(screen.getByRole('button', { name: 'List view' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByLabelText('02'));

    await user.click(screen.getByRole('button', { name: 'Calendar view' }));
    expect(screen.getByLabelText('01')).toBeChecked();
    expect(screen.getByLabelText('02')).toBeChecked();
  });

  it('uses the checkbox list for a partial month', () => {
    render(
      <DateGroupMemberSelector
        dateRange={{
          startDate: new Date('2026-05-01'),
          endDate: new Date('2026-05-30'),
        }}
        items={mayItems.slice(0, 30)}
        selectedIds={[]}
        onToggle={vi.fn()}
      />,
    );

    expect(screen.queryByText('May 2026')).not.toBeInTheDocument();
    expect(screen.getByText('Members')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Calendar view' })).not.toBeInTheDocument();
  });

  it('lists non-calendar date IDs separately', () => {
    render(
      <DateGroupMemberSelector
        dateRange={{
          startDate: new Date('2026-05-01'),
          endDate: new Date('2026-05-31'),
        }}
        items={[...mayItems, { id: 'SPECIAL', description: 'Manual date' }]}
        selectedIds={[]}
        onToggle={vi.fn()}
      />,
    );

    expect(screen.getByText('Other dates')).toBeInTheDocument();
    expect(screen.getByLabelText('SPECIAL')).toBeInTheDocument();
  });
});
