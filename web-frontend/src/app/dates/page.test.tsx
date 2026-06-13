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

import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DatePage from '@/app/dates/page';
import Navigation from '@/components/Navigation';
import { UnsavedEditingStateProvider } from '@/utils/unsavedEditingState';

const mockUseSchedulingData = vi.hoisted(() => vi.fn());
const mockPush = vi.hoisted(() => vi.fn());
const mockUsePathname = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useSchedulingData', () => ({
  useSchedulingData: mockUseSchedulingData,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => mockUsePathname(),
}));

vi.mock('@/components/ItemGroupEditorPage', () => ({
  __esModule: true,
  default: ({
    title,
    extraButtons,
    children,
  }: {
    title: string;
    extraButtons?: React.ReactNode;
    children?: React.ReactNode;
  }) => (
    <div>
      <h1>{title}</h1>
      {extraButtons}
      {children}
    </div>
  ),
}));

function renderDatePage() {
  return render(
    <UnsavedEditingStateProvider>
      <DatePage />
    </UnsavedEditingStateProvider>
  );
}

describe('DatePage', () => {
  const updateDateRange = vi.fn();

  beforeEach(() => {
    mockPush.mockReset();
    mockUsePathname.mockReturnValue('/dates');
    updateDateRange.mockReset();
    vi.stubGlobal('confirm', vi.fn(() => true));
    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-31T12:00:00.000Z'),
        },
        items: [],
        groups: [],
      },
      updateDateRange,
      addItem: vi.fn(),
      addGroup: vi.fn(),
      updateItem: vi.fn(),
      updateGroup: vi.fn(),
      deleteItem: vi.fn(),
      deleteGroup: vi.fn(),
      removeItemFromGroup: vi.fn(),
      reorderItems: vi.fn(),
      reorderGroups: vi.fn(),
    });
  });

  it('shows required-field errors when applying without dates', async () => {
    const user = userEvent.setup();

    renderDatePage();

    await user.click(screen.getByRole('button', { name: /set date range/i }));
    fireEvent.change(screen.getByLabelText('Start Date *'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('End Date *'), { target: { value: '' } });
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('Start date is required')).toBeInTheDocument();
    expect(screen.getByText('End date is required')).toBeInTheDocument();
    expect(updateDateRange).not.toHaveBeenCalled();
  });

  it('clears date range errors when the related date is edited', async () => {
    const user = userEvent.setup();

    renderDatePage();

    await user.click(screen.getByRole('button', { name: /set date range/i }));
    fireEvent.change(screen.getByLabelText('Start Date *'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('End Date *'), { target: { value: '' } });
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('Start date is required')).toBeInTheDocument();
    expect(screen.getByText('End date is required')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Start Date *'), { target: { value: '2026-05-01' } });

    expect(screen.queryByText('Start date is required')).not.toBeInTheDocument();
    expect(screen.getByText('End date is required')).toBeInTheDocument();
  });

  it('shows an end-date validation error when the end date is before the start date', async () => {
    const user = userEvent.setup();

    renderDatePage();

    await user.click(screen.getByRole('button', { name: /set date range/i }));
    fireEvent.change(screen.getByLabelText('Start Date *'), { target: { value: '2026-05-10' } });
    fireEvent.change(screen.getByLabelText('End Date *'), { target: { value: '2026-05-01' } });
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('End date must be after start date')).toBeInTheDocument();
    expect(updateDateRange).not.toHaveBeenCalled();
  });

  it('disables Taiwan holiday import for unsupported ranges and saves with import disabled', async () => {
    const user = userEvent.setup();

    renderDatePage();

    await user.click(screen.getByRole('button', { name: /set date range/i }));
    fireEvent.change(screen.getByLabelText('Start Date *'), { target: { value: '2027-01-01' } });
    fireEvent.change(screen.getByLabelText('End Date *'), { target: { value: '2027-01-31' } });

    const importCheckbox = screen.getByRole('checkbox', { name: /import taiwan holidays into date groups/i });
    expect(importCheckbox).toBeDisabled();
    expect(screen.getByText(/Available only when the selected date range stays within/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(updateDateRange).toHaveBeenCalledWith(
      {
        startDate: new Date('2027-01-01'),
        endDate: new Date('2027-01-31'),
      },
      { importTaiwanHolidays: false },
    );
  });

  it('shows supported Taiwan holiday entries and imports them by default on save', async () => {
    const user = userEvent.setup();

    renderDatePage();

    await user.click(screen.getByRole('button', { name: /set date range/i }));
    fireEvent.change(screen.getByLabelText('Start Date *'), { target: { value: '2026-05-01' } });
    fireEvent.change(screen.getByLabelText('End Date *'), { target: { value: '2026-05-31' } });

    expect(screen.getByText('Included holiday entries')).toBeInTheDocument();
    expect(screen.getByText(/2026-05-01 \(Fri\)/)).toBeInTheDocument();
    expect(screen.getByText('FREEDAY')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(updateDateRange).toHaveBeenCalledWith(
      {
        startDate: new Date('2026-05-01'),
        endDate: new Date('2026-05-31'),
      },
      { importTaiwanHolidays: true },
    );
  });

  it('respects turning Taiwan holiday import off before save', async () => {
    const user = userEvent.setup();

    renderDatePage();

    await user.click(screen.getByRole('button', { name: /set date range/i }));
    fireEvent.change(screen.getByLabelText('Start Date *'), { target: { value: '2026-05-01' } });
    fireEvent.change(screen.getByLabelText('End Date *'), { target: { value: '2026-05-31' } });

    const importCheckbox = screen.getByRole('checkbox', { name: /import taiwan holidays into date groups/i });
    await user.click(importCheckbox);
    expect(importCheckbox).not.toBeChecked();

    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(updateDateRange).toHaveBeenCalledWith(
      {
        startDate: new Date('2026-05-01'),
        endDate: new Date('2026-05-31'),
      },
      { importTaiwanHolidays: false },
    );
  });

  it('still requests Taiwan holiday import when editable holiday groups already exist', async () => {
    const user = userEvent.setup();

    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-31T12:00:00.000Z'),
        },
        items: [],
        groups: [
          { id: 'WORKDAY', members: ['02'], description: 'Existing workday group' },
          { id: 'FREEDAY', members: ['01'], description: 'Existing freeday group' },
        ],
      },
      updateDateRange,
      addItem: vi.fn(),
      addGroup: vi.fn(),
      updateItem: vi.fn(),
      updateGroup: vi.fn(),
      deleteItem: vi.fn(),
      deleteGroup: vi.fn(),
      removeItemFromGroup: vi.fn(),
      reorderItems: vi.fn(),
      reorderGroups: vi.fn(),
    });

    renderDatePage();

    await user.click(screen.getByRole('button', { name: /set date range/i }));
    fireEvent.change(screen.getByLabelText('Start Date *'), { target: { value: '2026-05-01' } });
    fireEvent.change(screen.getByLabelText('End Date *'), { target: { value: '2026-05-31' } });
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(updateDateRange).toHaveBeenCalledWith(
      {
        startDate: new Date('2026-05-01'),
        endDate: new Date('2026-05-31'),
      },
      { importTaiwanHolidays: true },
    );
  });

  it('clears validation errors and restores persisted values after canceling from an invalid draft', async () => {
    const user = userEvent.setup();

    renderDatePage();

    await user.click(screen.getByRole('button', { name: /set date range/i }));
    fireEvent.change(screen.getByLabelText('Start Date *'), { target: { value: '2026-05-10' } });
    fireEvent.change(screen.getByLabelText('End Date *'), { target: { value: '2026-05-01' } });
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('End date must be after start date')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByRole('button', { name: /set date range/i }));

    expect(screen.queryByText('End date must be after start date')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Start Date *')).toHaveValue('2026-01-01');
    expect(screen.getByLabelText('End Date *')).toHaveValue('2026-01-31');
  });

  it('shows and then clears full-month and Labor Day warnings as the draft range changes', async () => {
    const user = userEvent.setup();

    renderDatePage();

    await user.click(screen.getByRole('button', { name: /set date range/i }));
    fireEvent.change(screen.getByLabelText('Start Date *'), { target: { value: '2024-05-01' } });
    fireEvent.change(screen.getByLabelText('End Date *'), { target: { value: '2024-05-15' } });

    expect(screen.getByText(/Selected dates do not represent a full month/)).toBeInTheDocument();
    expect(screen.getByText(/Taiwan holiday import does not include Labor Day on May 1/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Start Date *'), { target: { value: '2026-05-01' } });
    fireEvent.change(screen.getByLabelText('End Date *'), { target: { value: '2026-05-31' } });

    expect(screen.queryByText(/Selected dates do not represent a full month/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Taiwan holiday import does not include Labor Day on May 1/)).not.toBeInTheDocument();
  });

  it('warns before switching tabs while the date range draft is open', async () => {
    const user = userEvent.setup();
    (confirm as unknown as ReturnType<typeof vi.fn>).mockReturnValue(false);

    render(
      <UnsavedEditingStateProvider>
        <DatePage />
        <Navigation />
      </UnsavedEditingStateProvider>
    );

    await user.click(screen.getByRole('button', { name: /set date range/i }));

    await user.click(screen.getByRole('button', { name: '2. People' }));

    expect(confirm).toHaveBeenCalledWith('You have unsaved edits. Leave this page without saving?');
    expect(mockPush).not.toHaveBeenCalled();
  });
});
