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

import { act, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ShiftCountsPage from '@/app/shift-counts/page';
import { UnsavedEditingStateProvider } from '@/utils/unsavedEditingState';

const mockUseSchedulingData = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useSchedulingData', () => ({
  useSchedulingData: mockUseSchedulingData,
}));

function renderShiftCountsPage() {
  return render(
    <UnsavedEditingStateProvider>
      <ShiftCountsPage />
    </UnsavedEditingStateProvider>
  );
}

describe('ShiftCountsPage', () => {
  const updatePreferencesByType = vi.fn();
  const duplicatePreferenceByType = vi.fn();

  async function fillRequiredFieldsAndSelectShiftTypes(
    user: ReturnType<typeof userEvent.setup>,
    shiftTypeIds: string[]
  ) {
    await user.click(screen.getByRole('button', { name: /add shift count/i }));
    await user.click(screen.getByRole('checkbox', { name: 'P1' }));
    await user.click(screen.getByRole('checkbox', { name: '2026-01-01' }));
    for (const shiftTypeId of shiftTypeIds) {
      await user.click(screen.getByRole('checkbox', { name: shiftTypeId }));
    }
  }

  function setCoefficient(shiftTypeId: string, coefficient: number) {
    const input = screen.getByRole('spinbutton', { name: shiftTypeId });
    fireEvent.change(input, { target: { value: coefficient.toString() } });
  }

  it('blurs number inputs on wheel so scrolling does not step their value', async () => {
    const user = userEvent.setup();
    renderShiftCountsPage();

    await fillRequiredFieldsAndSelectShiftTypes(user, ['D', 'N']);

    const coefficientInput = screen.getByRole('spinbutton', { name: 'D' });
    coefficientInput.focus();
    expect(coefficientInput).toHaveFocus();

    fireEvent.wheel(coefficientInput, { deltaY: 120 });

    expect(coefficientInput).not.toHaveFocus();
  });

  beforeEach(() => {
    updatePreferencesByType.mockReset();
    duplicatePreferenceByType.mockReset();
    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '2026-01-01', description: 'Jan 1' }],
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
        groups: [{ id: 'WORK', members: ['D', 'N'], description: 'Working shifts' }],
      },
      getPreferencesByType: vi.fn(() => []),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
  });

  it('blocks overlapping coefficients for a shift type and a group containing it', async () => {
    const user = userEvent.setup();
    renderShiftCountsPage();

    await fillRequiredFieldsAndSelectShiftTypes(user, ['D', 'WORK']);
    setCoefficient('D', 2);
    setCoefficient('WORK', 3);
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByText('Shift type coefficients overlap: D, WORK include D')).toBeInTheDocument();
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });

  it('allows overlapping selected shift types when their default coefficients are omitted', async () => {
    const user = userEvent.setup();
    renderShiftCountsPage();

    await fillRequiredFieldsAndSelectShiftTypes(user, ['D', 'WORK']);
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(updatePreferencesByType).toHaveBeenCalledOnce();
    expect(updatePreferencesByType.mock.calls[0][1][0]).not.toHaveProperty('countShiftTypeCoefficients');
  });

  it('allows overlapping selected shift types when only one has a non-default coefficient', async () => {
    const user = userEvent.setup();
    renderShiftCountsPage();

    await fillRequiredFieldsAndSelectShiftTypes(user, ['D', 'WORK']);
    setCoefficient('WORK', 3);
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(updatePreferencesByType).toHaveBeenCalledOnce();
    expect(updatePreferencesByType.mock.calls[0][1][0].countShiftTypeCoefficients).toEqual([['WORK', 3]]);
  });

  it('blocks overlapping selected shift types when coefficient one is explicit', async () => {
    const user = userEvent.setup();
    renderShiftCountsPage();

    await fillRequiredFieldsAndSelectShiftTypes(user, ['D', 'WORK']);
    setCoefficient('D', 1);
    setCoefficient('WORK', 2);
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByText('Shift type coefficients overlap: D, WORK include D')).toBeInTheDocument();
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });

  it('saves explicit coefficient one', async () => {
    const user = userEvent.setup();
    renderShiftCountsPage();

    await fillRequiredFieldsAndSelectShiftTypes(user, ['D']);
    setCoefficient('D', 1);
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(updatePreferencesByType).toHaveBeenCalledOnce();
    expect(updatePreferencesByType.mock.calls[0][1][0].countShiftTypeCoefficients).toEqual([['D', 1]]);
  });

  it('allows non-overlapping non-default coefficients', async () => {
    const user = userEvent.setup();
    renderShiftCountsPage();

    await fillRequiredFieldsAndSelectShiftTypes(user, ['D', 'N']);
    setCoefficient('D', 2);
    setCoefficient('N', 3);
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(updatePreferencesByType).toHaveBeenCalledOnce();
    expect(updatePreferencesByType.mock.calls[0][1][0].countShiftTypeCoefficients).toEqual([
      ['D', 2],
      ['N', 3],
    ]);
  });

  it('preserves coefficients after deselecting down to one shift type', async () => {
    const user = userEvent.setup();
    renderShiftCountsPage();

    await fillRequiredFieldsAndSelectShiftTypes(user, ['D', 'N']);
    setCoefficient('D', 2);
    await user.click(screen.getByRole('checkbox', { name: 'N' }));
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(updatePreferencesByType).toHaveBeenCalledOnce();
    expect(updatePreferencesByType.mock.calls[0][1][0].countShiftTypeCoefficients).toEqual([['D', 2]]);
  });

  it('shows an invalid coefficient error before checking coefficient overlap', async () => {
    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '2026-01-01', description: 'Jan 1' }],
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
        groups: [{ id: 'WORK', members: ['D', 'N'], description: 'Working shifts' }],
      },
      getPreferencesByType: vi.fn(() => [{
        type: 'shift count',
        person: ['P1'],
        countDates: ['2026-01-01'],
        countShiftTypes: ['D', 'WORK'],
        countShiftTypeCoefficients: [['D', 0], ['WORK', 3]],
        expression: 'x >= T',
        target: 0,
        weight: -1,
      }]),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
    const user = userEvent.setup();
    renderShiftCountsPage();

    await user.click(screen.getByRole('button', { name: /edit/i }));
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('Coefficient for D must be an integer of at least 1')).toBeInTheDocument();
    expect(screen.queryByText(/Shift type coefficients overlap/)).not.toBeInTheDocument();
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });

  it('dismisses the edited shift count draft before duplicating a shift count', async () => {
    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '2026-01-01', description: 'Jan 1' }],
        groups: [],
      },
      peopleData: {
        items: [{ id: 'P1', description: 'Person 1', history: [] }],
        groups: [],
      },
      shiftTypeData: {
        items: [{ id: 'D', description: 'Day' }],
        groups: [],
      },
      getPreferencesByType: vi.fn(() => [{
        type: 'shift count',
        description: 'Original count',
        person: ['P1'],
        countDates: ['2026-01-01'],
        countShiftTypes: ['D'],
        expression: 'x >= T',
        target: 1,
        weight: -1,
      }]),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
    const user = userEvent.setup();
    renderShiftCountsPage();

    await user.click(screen.getByRole('button', { name: /edit/i }));
    await user.click(screen.getByRole('button', { name: /duplicate/i }));

    expect(screen.queryByRole('button', { name: 'Update' })).not.toBeInTheDocument();
    expect(duplicatePreferenceByType).toHaveBeenCalledWith('shift count', 0);
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });

  it('dismisses an added shift count draft before duplicating a shift count', async () => {
    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '2026-01-01', description: 'Jan 1' }],
        groups: [],
      },
      peopleData: {
        items: [{ id: 'P1', description: 'Person 1', history: [] }],
        groups: [],
      },
      shiftTypeData: {
        items: [{ id: 'D', description: 'Day' }],
        groups: [],
      },
      getPreferencesByType: vi.fn(() => [{
        type: 'shift count',
        description: 'Original count',
        person: ['P1'],
        countDates: ['2026-01-01'],
        countShiftTypes: ['D'],
        expression: 'x >= T',
        target: 1,
        weight: -1,
      }]),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
    const user = userEvent.setup();
    renderShiftCountsPage();

    await user.click(screen.getByRole('button', { name: /add shift count/i }));
    await user.type(screen.getByPlaceholderText('e.g., Working shifts should be close to the average'), 'Unsaved count');
    await user.click(screen.getByRole('button', { name: /duplicate/i }));

    expect(screen.queryByRole('button', { name: 'Add' })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Unsaved count')).not.toBeInTheDocument();
    expect(duplicatePreferenceByType).toHaveBeenCalledWith('shift count', 0);
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });

  it('shows all invalid coefficient errors and clears only the edited coefficient error', async () => {
    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '2026-01-01', description: 'Jan 1' }],
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
        type: 'shift count',
        person: ['P1'],
        countDates: ['2026-01-01'],
        countShiftTypes: ['D', 'N'],
        countShiftTypeCoefficients: [['D', 0], ['N', 0]],
        expression: 'x >= T',
        target: 0,
        weight: -1,
      }]),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
    const user = userEvent.setup();
    renderShiftCountsPage();

    await user.click(screen.getByRole('button', { name: /edit/i }));
    const dayCoefficientInput = screen.getByRole('spinbutton', { name: 'D' });
    const nightCoefficientInput = screen.getByRole('spinbutton', { name: 'N' });

    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('Coefficient for D must be an integer of at least 1')).toBeInTheDocument();
    expect(screen.getByText('Coefficient for N must be an integer of at least 1')).toBeInTheDocument();
    expect(dayCoefficientInput).toHaveClass('border-red-300');
    expect(nightCoefficientInput).toHaveClass('border-red-300');

    await user.type(dayCoefficientInput, '2');

    expect(screen.queryByText('Coefficient for D must be an integer of at least 1')).not.toBeInTheDocument();
    expect(screen.getByText('Coefficient for N must be an integer of at least 1')).toBeInTheDocument();
    expect(dayCoefficientInput).not.toHaveClass('border-red-300');
    expect(nightCoefficientInput).toHaveClass('border-red-300');
  });

  it('clears multiple coefficient errors queued before a render', async () => {
    mockUseSchedulingData.mockReturnValue({
      dateData: {
        range: {
          startDate: new Date('2026-01-01T12:00:00.000Z'),
          endDate: new Date('2026-01-01T12:00:00.000Z'),
        },
        items: [{ id: '2026-01-01', description: 'Jan 1' }],
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
        type: 'shift count',
        person: ['P1'],
        countDates: ['2026-01-01'],
        countShiftTypes: ['D', 'N'],
        countShiftTypeCoefficients: [['D', 0], ['N', 0]],
        expression: 'x >= T',
        target: 0,
        weight: -1,
      }]),
      updatePreferencesByType,
      duplicatePreferenceByType,
    });
    const user = userEvent.setup();
    renderShiftCountsPage();

    await user.click(screen.getByRole('button', { name: /edit/i }));
    const dayCoefficientInput = screen.getByRole('spinbutton', { name: 'D' });
    const nightCoefficientInput = screen.getByRole('spinbutton', { name: 'N' });

    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('Coefficient for D must be an integer of at least 1')).toBeInTheDocument();
    expect(screen.getByText('Coefficient for N must be an integer of at least 1')).toBeInTheDocument();

    act(() => {
      fireEvent.change(dayCoefficientInput, { target: { value: '2' } });
      fireEvent.change(nightCoefficientInput, { target: { value: '3' } });
    });

    expect(screen.queryByText('Coefficient for D must be an integer of at least 1')).not.toBeInTheDocument();
    expect(screen.queryByText('Coefficient for N must be an integer of at least 1')).not.toBeInTheDocument();
    expect(dayCoefficientInput).not.toHaveClass('border-red-300');
    expect(nightCoefficientInput).not.toHaveClass('border-red-300');
  });

  it('allows an empty target while editing and clears its save error only after a value change', async () => {
    const user = userEvent.setup();
    renderShiftCountsPage();

    await fillRequiredFieldsAndSelectShiftTypes(user, ['D']);
    const targetInput = screen.getByPlaceholderText('e.g., 5');

    await user.clear(targetInput);
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByText('Target must be a non-negative integer')).toBeInTheDocument();
    expect(targetInput).toHaveClass('border-red-300');

    await user.type(targetInput, 'abc');

    expect(screen.getByText('Target must be a non-negative integer')).toBeInTheDocument();
    expect(targetInput).toHaveClass('border-red-300');

    await user.type(targetInput, '2');

    expect(screen.queryByText('Target must be a non-negative integer')).not.toBeInTheDocument();
    expect(targetInput).not.toHaveClass('border-red-300');
  });

  it.each([
    ['0', 0],
    ['-1', -1],
    ['-Infinity', -Infinity],
  ])('allows squared-error expression with non-positive weight %s', async (weightInput, expectedWeight) => {
    const user = userEvent.setup();
    renderShiftCountsPage();

    await fillRequiredFieldsAndSelectShiftTypes(user, ['D']);
    await user.selectOptions(screen.getByRole('combobox'), '|x - T|^2');
    fireEvent.change(screen.getByPlaceholderText('e.g., -1, -10, ∞'), { target: { value: weightInput } });
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(updatePreferencesByType).toHaveBeenCalledOnce();
    expect(updatePreferencesByType.mock.calls[0][1][0].weight).toBe(expectedWeight);
  });

  it.each(['1', 'Infinity'])('rejects squared-error expression with positive weight %s', async (weightInput) => {
    const user = userEvent.setup();
    renderShiftCountsPage();

    await fillRequiredFieldsAndSelectShiftTypes(user, ['D']);
    await user.selectOptions(screen.getByRole('combobox'), '|x - T|^2');
    fireEvent.change(screen.getByPlaceholderText('e.g., -1, -10, ∞'), { target: { value: weightInput } });
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByText('Weight must be non-positive for shift count with "|x - T|^2"')).toBeInTheDocument();
    expect(updatePreferencesByType).not.toHaveBeenCalled();
  });

});
