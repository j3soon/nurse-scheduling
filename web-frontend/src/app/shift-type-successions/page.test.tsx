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
import ShiftTypeSuccessionsPage from '@/app/shift-type-successions/page';
import { UnsavedEditingStateProvider } from '@/utils/unsavedEditingState';

const mockUseSchedulingData = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useSchedulingData', () => ({
  useSchedulingData: mockUseSchedulingData,
}));

function renderShiftTypeSuccessionsPage() {
  return render(
    <UnsavedEditingStateProvider>
      <ShiftTypeSuccessionsPage />
    </UnsavedEditingStateProvider>
  );
}

describe('ShiftTypeSuccessionsPage', () => {
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
        items: [{ id: 'P1', description: 'Person 1', history: [] }],
        groups: [],
      },
      shiftTypeData: {
        items: [
          { id: 'D', description: 'Day' },
          { id: 'N', description: 'Night' },
        ],
        groups: [],
      },
      getPreferencesByType: vi.fn(() => []),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
  });

  it('clears stale field errors when the related succession field is edited', async () => {
    const user = userEvent.setup();
    renderShiftTypeSuccessionsPage();

    await user.click(screen.getByRole('button', { name: /add succession/i }));
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByText('At least one person must be selected')).toBeInTheDocument();
    expect(screen.getByText('At least 2 shift types must be selected for a succession pattern')).toBeInTheDocument();
    expect(screen.getByText('At least one date must be selected')).toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: 'P1' }));
    await user.click(screen.getByRole('button', { name: 'D' }));
    await user.click(screen.getByRole('checkbox', { name: '01' }));

    expect(screen.queryByText('At least one person must be selected')).not.toBeInTheDocument();
    expect(screen.queryByText('At least 2 shift types must be selected for a succession pattern')).not.toBeInTheDocument();
    expect(screen.queryByText('At least one date must be selected')).not.toBeInTheDocument();
  });

  it('dismisses the edited succession draft before duplicating a succession', async () => {
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
        items: [{ id: 'P1', description: 'Person 1', history: [] }],
        groups: [],
      },
      shiftTypeData: {
        items: [
          { id: 'D', description: 'Day' },
          { id: 'N', description: 'Night' },
        ],
        groups: [],
      },
      getPreferencesByType: vi.fn(() => [{
        type: 'shift type successions',
        description: 'Original succession',
        person: ['P1'],
        pattern: ['D', 'N'],
        date: ['01'],
        weight: -1,
      }]),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
    renderShiftTypeSuccessionsPage();

    await user.click(screen.getByRole('button', { name: /edit/i }));
    await user.click(screen.getByRole('button', { name: /duplicate/i }));

    expect(screen.queryByRole('button', { name: 'Update' })).not.toBeInTheDocument();
    expect(duplicatePreferenceByType).toHaveBeenCalledWith('shift type successions', 0);
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });

  it('dismisses an added succession draft before duplicating a succession', async () => {
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
        items: [{ id: 'P1', description: 'Person 1', history: [] }],
        groups: [],
      },
      shiftTypeData: {
        items: [
          { id: 'D', description: 'Day' },
          { id: 'N', description: 'Night' },
        ],
        groups: [],
      },
      getPreferencesByType: vi.fn(() => [{
        type: 'shift type successions',
        description: 'Original succession',
        person: ['P1'],
        pattern: ['D', 'N'],
        date: ['01'],
        weight: -1,
      }]),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
    renderShiftTypeSuccessionsPage();

    await user.click(screen.getByRole('button', { name: /add succession/i }));
    await user.type(screen.getByPlaceholderText('e.g., Forbid Evening -> Day succession'), 'Unsaved succession');
    await user.click(screen.getByRole('button', { name: /duplicate/i }));

    expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Unsaved succession')).not.toBeInTheDocument();
    expect(duplicatePreferenceByType).toHaveBeenCalledWith('shift type successions', 0);
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });
});
