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
import ShiftAffinitiesPage from '@/app/shift-affinities/page';
import { UnsavedEditingStateProvider } from '@/utils/unsavedEditingState';

const mockUseSchedulingData = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useSchedulingData', () => ({
  useSchedulingData: mockUseSchedulingData,
}));

function renderShiftAffinitiesPage() {
  return render(
    <UnsavedEditingStateProvider>
      <ShiftAffinitiesPage />
    </UnsavedEditingStateProvider>
  );
}

describe('ShiftAffinitiesPage', () => {
  const updatePreferencesByType = vi.fn();
  const duplicatePreferenceByType = vi.fn();

  beforeEach(() => {
    updatePreferencesByType.mockReset();
    duplicatePreferenceByType.mockReset();
    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '01', description: 'Jan 1' }],
        groups: [],
      },
      peopleData: {
        items: [
          { id: 'P1', description: 'Person 1', history: [] },
          { id: 'P2', description: 'Person 2', history: [] },
        ],
        groups: [],
      },
      shiftTypeData: {
        items: [{ id: 'D', description: 'Day' }],
        groups: [],
      },
      getPreferencesByType: vi.fn(() => []),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
  });

  it('clears stale field errors when the related affinity field is edited', async () => {
    const user = userEvent.setup();
    renderShiftAffinitiesPage();

    await user.click(screen.getByRole('button', { name: /add shift affinity/i }));
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByText('At least one date must be selected')).toBeInTheDocument();
    expect(screen.getByText('At least one person must be selected for People 1')).toBeInTheDocument();
    expect(screen.getByText('At least one person must be selected for People 2')).toBeInTheDocument();
    expect(screen.getByText('At least one shift type must be selected')).toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: '01' }));
    await user.click(screen.getAllByRole('checkbox', { name: 'P1' })[0]);
    await user.click(screen.getAllByRole('checkbox', { name: 'P2' })[1]);
    await user.click(screen.getByRole('checkbox', { name: 'D' }));

    expect(screen.queryByText('At least one date must be selected')).not.toBeInTheDocument();
    expect(screen.queryByText('At least one person must be selected for People 1')).not.toBeInTheDocument();
    expect(screen.queryByText('At least one person must be selected for People 2')).not.toBeInTheDocument();
    expect(screen.queryByText('At least one shift type must be selected')).not.toBeInTheDocument();
  });

  it('dismisses the edited affinity draft before duplicating an affinity', async () => {
    const user = userEvent.setup();
    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '01', description: 'Jan 1' }],
        groups: [],
      },
      peopleData: {
        items: [
          { id: 'P1', description: 'Person 1', history: [] },
          { id: 'P2', description: 'Person 2', history: [] },
        ],
        groups: [],
      },
      shiftTypeData: {
        items: [{ id: 'D', description: 'Day' }],
        groups: [],
      },
      getPreferencesByType: vi.fn(() => [{
        type: 'shift affinity',
        description: 'Original affinity',
        date: ['01'],
        people1: ['P1'],
        people2: ['P2'],
        shiftTypes: ['D'],
        weight: 1,
      }]),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
    renderShiftAffinitiesPage();

    await user.click(screen.getByRole('button', { name: /edit/i }));
    await user.click(screen.getByRole('button', { name: /duplicate/i }));

    expect(screen.queryByRole('button', { name: 'Update' })).not.toBeInTheDocument();
    expect(duplicatePreferenceByType).toHaveBeenCalledWith('shift affinity', 0);
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });

  it('dismisses an added affinity draft before duplicating an affinity', async () => {
    const user = userEvent.setup();
    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '01', description: 'Jan 1' }],
        groups: [],
      },
      peopleData: {
        items: [
          { id: 'P1', description: 'Person 1', history: [] },
          { id: 'P2', description: 'Person 2', history: [] },
        ],
        groups: [],
      },
      shiftTypeData: {
        items: [{ id: 'D', description: 'Day' }],
        groups: [],
      },
      getPreferencesByType: vi.fn(() => [{
        type: 'shift affinity',
        description: 'Original affinity',
        date: ['01'],
        people1: ['P1'],
        people2: ['P2'],
        shiftTypes: ['D'],
        weight: 1,
      }]),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
    renderShiftAffinitiesPage();

    await user.click(screen.getByRole('button', { name: /add shift affinity/i }));
    await user.type(screen.getByPlaceholderText('e.g., Encourage newcomers and seniors to work together'), 'Unsaved affinity');
    await user.click(screen.getByRole('button', { name: /duplicate/i }));

    expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Unsaved affinity')).not.toBeInTheDocument();
    expect(duplicatePreferenceByType).toHaveBeenCalledWith('shift affinity', 0);
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });
});
