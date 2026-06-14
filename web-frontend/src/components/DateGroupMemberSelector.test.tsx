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
    expect(screen.getByRole('button', { name: '01' })).toHaveAttribute('aria-pressed', 'true');

    await user.click(screen.getByRole('button', { name: '02' }));

    expect(onToggle).toHaveBeenCalledWith('02');
  });

  it('shows normal weekends and Taiwan calendar exceptions without overriding selection', () => {
    render(
      <DateGroupMemberSelector
        dateRange={{
          startDate: new Date('2025-02-01'),
          endDate: new Date('2025-02-28'),
        }}
        items={mayItems.slice(0, 28)}
        selectedIds={['09']}
        onToggle={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: '08' })).toHaveClass('bg-white', 'text-slate-700');
    expect(screen.getByRole('button', { name: '09' })).toHaveClass('bg-blue-600', 'text-white');
    expect(screen.getByRole('button', { name: '16' })).toHaveClass('bg-amber-50/70', 'text-amber-700');
    expect(screen.getByRole('button', { name: '28' })).toHaveClass('bg-amber-50/70', 'font-medium', 'text-amber-800');
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

    const first = screen.getByRole('button', { name: '01' });
    const second = screen.getByRole('button', { name: '02' });
    fireEvent.mouseEnter(first);
    fireEvent.mouseDown(first, { button: 0 });
    fireEvent.mouseEnter(second);
    fireEvent.mouseUp(second, { button: 0 });

    expect(onToggle).toHaveBeenNthCalledWith(1, '01');
    expect(onToggle).toHaveBeenNthCalledWith(2, '02');
  });

  it('ends a mouse gesture when released between calendar dates', () => {
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

    fireEvent.mouseDown(screen.getByRole('button', { name: '01' }), { button: 0 });
    fireEvent.mouseUp(screen.getByTestId('calendar-month-grid'), { button: 0 });
    fireEvent.mouseEnter(screen.getByRole('button', { name: '02' }));

    expect(onToggle).not.toHaveBeenCalled();
  });

  it('preserves selections when switching between calendar and list views', async () => {
    const user = userEvent.setup();

    render(<StatefulSelector />);

    expect(screen.getByRole('button', { name: 'Calendar view' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '01' })).toHaveAttribute('aria-pressed', 'true');

    await user.click(screen.getByRole('button', { name: 'List view' }));
    expect(screen.getByRole('button', { name: 'List view' })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByLabelText('02'));

    await user.click(screen.getByRole('button', { name: 'Calendar view' }));
    expect(screen.getByRole('button', { name: '01' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '02' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows a bounded calendar for a partial month', () => {
    render(
      <DateGroupMemberSelector
        dateRange={{
          startDate: new Date('2026-05-05'),
          endDate: new Date('2026-05-30'),
        }}
        items={mayItems.slice(4, 30)}
        selectedIds={[]}
        onToggle={vi.fn()}
      />,
    );

    expect(screen.getByText('May 2026')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous month' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next month' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Unavailable 2026-05-04' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '05' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Unavailable 2026-05-31' })).toBeDisabled();
  });

  it('navigates between months within a multi-month range', async () => {
    const user = userEvent.setup();
    const items = [
      ...Array.from({ length: 17 }, (_, index) => ({
        id: `05-${String(index + 15).padStart(2, '0')}`,
        description: '',
      })),
      ...Array.from({ length: 10 }, (_, index) => ({
        id: `06-${String(index + 1).padStart(2, '0')}`,
        description: '',
      })),
    ];

    render(
      <DateGroupMemberSelector
        dateRange={{
          startDate: new Date('2026-05-15'),
          endDate: new Date('2026-06-10'),
        }}
        items={items}
        selectedIds={[]}
        onToggle={vi.fn()}
      />,
    );

    expect(screen.getByText('May 2026')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous month' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next month' })).toBeEnabled();
    expect(screen.getByRole('button', { name: '05-15' })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: 'Next month' }));

    expect(screen.getByText('June 2026')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous month' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Next month' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '06-10' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Unavailable 2026-06-11' })).toBeDisabled();
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
