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
import ExportLayoutPage from '@/app/export-layout/page';
import { ExportConfig } from '@/types/scheduling';
import { UnsavedEditingStateProvider } from '@/utils/unsavedEditingState';

const mockUseSchedulingData = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useSchedulingData', () => ({
  useSchedulingData: mockUseSchedulingData,
}));

const updateExportConfig = vi.fn();
const updateExportFormatting = vi.fn();
const updateExportExtraColumns = vi.fn();
const updateExportExtraRows = vi.fn();
const duplicateExportFormatting = vi.fn();
const duplicateExportExtraColumn = vi.fn();
const duplicateExportExtraRow = vi.fn();

function renderExportLayoutPage(exportData: ExportConfig = { formatting: [], extraColumns: [], extraRows: [] }) {
  mockUseSchedulingData.mockReturnValue({
    effectiveExportData: exportData,
    updateExportFormatting,
    updateExportExtraColumns,
    updateExportExtraRows,
    updateExportConfig,
    duplicateExportFormatting,
    duplicateExportExtraColumn,
    duplicateExportExtraRow,
    peopleData: {
      items: [{ id: 'P1', description: 'Person 1', history: [] }],
      groups: [],
    },
    dateData: {
      range: {
        startDate: new Date('2026-01-01T12:00:00.000Z'),
        endDate: new Date('2026-01-01T12:00:00.000Z'),
      },
      items: [{ id: '2026-01-01', description: 'Jan 1' }],
      groups: [],
    },
    shiftTypeData: {
      items: [
        { id: 'D', description: 'Day' },
        { id: 'N', description: 'Night' },
      ],
      groups: [{ id: 'WORK', members: ['D', 'N'], description: 'Working shifts' }],
    },
  });

  return render(
    <UnsavedEditingStateProvider>
      <ExportLayoutPage />
    </UnsavedEditingStateProvider>
  );
}

async function startExtraColumn(
  user: ReturnType<typeof userEvent.setup>,
  shiftTypeIds: string[]
) {
  await user.click(screen.getByRole('button', { name: 'Add Export Rule' }));
  await user.selectOptions(screen.getAllByRole('combobox')[0], 'extra column');
  await user.type(screen.getByPlaceholderText('OFF (Weekend)'), 'Score');
  for (const shiftTypeId of shiftTypeIds) {
    await user.click(screen.getByRole('checkbox', { name: shiftTypeId }));
  }
  await user.click(screen.getByRole('checkbox', { name: '2026-01-01' }));
}

describe('ExportLayoutPage extra column coefficients', () => {
  beforeEach(() => {
    updateExportConfig.mockReset();
    updateExportFormatting.mockReset();
    updateExportExtraColumns.mockReset();
    updateExportExtraRows.mockReset();
    duplicateExportFormatting.mockReset();
    duplicateExportExtraColumn.mockReset();
    duplicateExportExtraRow.mockReset();
  });

  it('shows the experimental export layout warning', () => {
    renderExportLayoutPage();

    expect(screen.getByText("This page is experimental. Only modify export layout entries if you know exactly what you're doing.")).toBeInTheDocument();
  });

  it('saves only non-default coefficients on an extra column', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await startExtraColumn(user, ['D', 'N']);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'N' }), { target: { value: '3' } });
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    expect(updateExportConfig).toHaveBeenCalledOnce();
    expect(updateExportConfig.mock.calls[0][0].extraColumns).toEqual([{
      description: '',
      type: 'count',
      header: 'Score',
      countShiftTypes: ['D', 'N'],
      countShiftTypeCoefficients: [['N', 3]],
      countDates: ['2026-01-01'],
    }]);
  });

  it('omits coefficients when every selected shift type uses the default value', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await startExtraColumn(user, ['D', 'WORK']);
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    expect(updateExportConfig).toHaveBeenCalledOnce();
    expect(updateExportConfig.mock.calls[0][0].extraColumns[0]).not.toHaveProperty('countShiftTypeCoefficients');
  });

  it('resets a coefficient after its shift type is deselected and reselected', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await startExtraColumn(user, ['D', 'N']);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'D' }), { target: { value: '3' } });
    await user.click(screen.getByRole('checkbox', { name: 'D' }));
    await user.click(screen.getByRole('checkbox', { name: 'D' }));
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    expect(updateExportConfig).toHaveBeenCalledOnce();
    expect(updateExportConfig.mock.calls[0][0].extraColumns[0]).not.toHaveProperty('countShiftTypeCoefficients');
  });

  it('blocks overlapping non-default coefficients from an item and containing group', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await startExtraColumn(user, ['D', 'WORK']);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'D' }), { target: { value: '2' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'WORK' }), { target: { value: '3' } });
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    const overlapError = screen.getByText('Shift type coefficients overlap: D, WORK include D');
    expect(overlapError).toBeInTheDocument();
    expect(
      overlapError.compareDocumentPosition(screen.getByText('Count Dates *')) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(updateExportConfig).not.toHaveBeenCalled();
  });

  it('blocks overlapping explicit coefficient one from an item and containing group', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await startExtraColumn(user, ['D', 'WORK']);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'D' }), { target: { value: '1' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'WORK' }), { target: { value: '2' } });
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    expect(screen.getByText('Shift type coefficients overlap: D, WORK include D')).toBeInTheDocument();
    expect(updateExportConfig).not.toHaveBeenCalled();
  });

  it('clears an overlap error when the count shift type selection changes', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await startExtraColumn(user, ['D', 'WORK']);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'D' }), { target: { value: '2' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'WORK' }), { target: { value: '3' } });
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    expect(screen.getByText('Shift type coefficients overlap: D, WORK include D')).toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: 'D' }));

    expect(screen.queryByText(/Shift type coefficients overlap/)).not.toBeInTheDocument();
  });

  it('loads and updates an existing extra column coefficient', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage({
      formatting: [],
      extraColumns: [{
        type: 'count',
        header: 'Existing Score',
        countShiftTypes: ['D', 'N'],
        countShiftTypeCoefficients: [['D', 2]],
        countDates: ['2026-01-01'],
      }],
      extraRows: [],
    });

    await user.click(screen.getByRole('button', { name: 'Edit' }));
    expect(screen.getByRole('spinbutton', { name: 'D' })).toHaveValue(2);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'D' }), { target: { value: '4' } });
    await user.click(screen.getByRole('button', { name: 'Update', exact: true }));

    expect(updateExportConfig.mock.calls[0][0].extraColumns[0].countShiftTypeCoefficients).toEqual([['D', 4]]);
  });

  it('duplicates an export rule under the original with a copied description', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage({
      formatting: [],
      extraColumns: [{
        type: 'count',
        header: 'Existing Score',
        countShiftTypes: ['D'],
        countDates: ['2026-01-01'],
      }],
      extraRows: [],
    });

    await user.click(screen.getByRole('button', { name: 'Duplicate' }));

    expect(duplicateExportExtraColumn).toHaveBeenCalledWith(0);
    expect(updateExportExtraColumns).not.toHaveBeenCalled();
  });

  it('dismisses the edited export draft before duplicating export entries', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage({
      formatting: [{
        description: 'Weekend style',
        type: 'cell',
        people: ['P1'],
        dates: ['2026-01-01'],
        shiftTypes: ['D'],
        backgroundColor: '#ffffff',
      }],
      extraColumns: [{
        type: 'count',
        header: 'Existing Score',
        countShiftTypes: ['D'],
        countDates: ['2026-01-01'],
      }],
      extraRows: [{
        type: 'count',
        header: 'Existing Total',
        countShiftTypes: ['D'],
        countPeople: ['P1'],
      }],
    });

    await user.click(screen.getAllByRole('button', { name: 'Edit' })[0]);
    for (const duplicateButton of screen.getAllByRole('button', { name: 'Duplicate' })) {
      await user.click(duplicateButton);
    }

    expect(screen.queryByRole('button', { name: 'Update' })).not.toBeInTheDocument();
    expect(duplicateExportFormatting).toHaveBeenCalledWith(0);
    expect(duplicateExportExtraColumn).toHaveBeenCalledWith(0);
    expect(duplicateExportExtraRow).toHaveBeenCalledWith(0);
  });

  it('dismisses an added export draft before duplicating export entries', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage({
      formatting: [{
        description: 'Weekend style',
        type: 'cell',
        people: ['P1'],
        dates: ['2026-01-01'],
        shiftTypes: ['D'],
        backgroundColor: '#ffffff',
      }],
      extraColumns: [],
      extraRows: [],
    });

    await user.click(screen.getByRole('button', { name: 'Add Export Rule' }));
    await user.type(screen.getByPlaceholderText('Optional note for this export rule'), 'Unsaved rule');
    await user.click(screen.getByRole('button', { name: 'Duplicate' }));

    expect(screen.queryByRole('button', { name: 'Add', exact: true })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Unsaved rule')).not.toBeInTheDocument();
    expect(duplicateExportFormatting).toHaveBeenCalledWith(0);
  });

  it('dismisses an added export draft before deleting an export entry', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage({
      formatting: [{
        description: 'Weekend style',
        type: 'cell',
        people: ['P1'],
        dates: ['2026-01-01'],
        shiftTypes: ['D'],
        backgroundColor: '#ffffff',
      }],
      extraColumns: [],
      extraRows: [],
    });

    await user.click(screen.getByRole('button', { name: 'Add Export Rule' }));
    await user.type(screen.getByPlaceholderText('Optional note for this export rule'), 'Unsaved rule');
    await user.click(screen.getByRole('button', { name: 'Delete' }));

    expect(screen.queryByRole('button', { name: 'Add', exact: true })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('Unsaved rule')).not.toBeInTheDocument();
    expect(updateExportFormatting).toHaveBeenCalledWith([]);
  });

  it('clears an invalid coefficient error after correction and saves the rule', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage({
      formatting: [],
      extraColumns: [{
        type: 'count',
        header: 'Score',
        countShiftTypes: ['D', 'N'],
        countShiftTypeCoefficients: [['D', 0]],
        countDates: ['2026-01-01'],
      }],
      extraRows: [],
    });

    await user.click(screen.getByRole('button', { name: 'Edit' }));
    const coefficientInput = screen.getByRole('spinbutton', { name: 'D' });
    await user.click(screen.getByRole('button', { name: 'Update', exact: true }));

    expect(screen.getByText('Coefficient for D must be an integer of at least 1')).toBeInTheDocument();
    expect(coefficientInput).toHaveClass('border-red-300');
    expect(updateExportConfig).not.toHaveBeenCalled();

    await user.type(coefficientInput, '2');
    expect(screen.queryByText('Coefficient for D must be an integer of at least 1')).not.toBeInTheDocument();
    expect(coefficientInput).not.toHaveClass('border-red-300');

    await user.click(screen.getByRole('button', { name: 'Update', exact: true }));
    expect(updateExportConfig).toHaveBeenCalledOnce();
    expect(updateExportConfig.mock.calls[0][0].extraColumns[0].countShiftTypeCoefficients).toEqual([['D', 2]]);
  });

  it('shows the required header error under the header input with a red border', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await user.click(screen.getByRole('button', { name: 'Add Export Rule' }));
    await user.selectOptions(screen.getAllByRole('combobox')[0], 'extra column');
    await user.click(screen.getByRole('checkbox', { name: 'D' }));
    await user.click(screen.getByRole('checkbox', { name: '2026-01-01' }));
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    const headerInput = screen.getByPlaceholderText('OFF (Weekend)');
    const headerError = screen.getByText('Column header is required');
    expect(headerInput).toHaveClass('border-red-300');
    expect(
      headerInput.compareDocumentPosition(headerError) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();

    await user.type(headerInput, 'Score');

    expect(screen.queryByText('Column header is required')).not.toBeInTheDocument();
    expect(headerInput).not.toHaveClass('border-red-300');
  });

  it('shows the count dates error under the count dates list', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await user.click(screen.getByRole('button', { name: 'Add Export Rule' }));
    await user.selectOptions(screen.getAllByRole('combobox')[0], 'extra column');
    await user.type(screen.getByPlaceholderText('OFF (Weekend)'), 'Score');
    await user.click(screen.getByRole('checkbox', { name: 'D' }));
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    const countDatesLabel = screen.getByText('Count Dates *');
    const countDatesError = screen.getByText('Select at least one date target to count over');
    expect(
      countDatesLabel.compareDocumentPosition(countDatesError) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
  });

  it('shows color errors under the corresponding color field with a red border', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await startExtraColumn(user, ['D', 'N']);
    const rightBorderInput = screen.getByTitle('Enter right border color in hex');
    await user.type(rightBorderInput, 'red');
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    expect(screen.getByText('Right Border Color must be a valid hex color in #RRGGBB format')).toBeInTheDocument();
    expect(rightBorderInput).toHaveClass('border-red-300');
  });

  it('shows all extra column validation errors from one save attempt', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await user.click(screen.getByRole('button', { name: 'Add Export Rule' }));
    await user.selectOptions(screen.getAllByRole('combobox')[0], 'extra column');
    await user.type(screen.getByTitle('Enter right border color in hex'), 'red');
    await user.click(screen.getByRole('checkbox', { name: 'D' }));
    await user.click(screen.getByRole('checkbox', { name: 'N' }));
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    expect(screen.getByText('Column header is required')).toBeInTheDocument();
    expect(screen.getByText('Right Border Color must be a valid hex color in #RRGGBB format')).toBeInTheDocument();
    expect(screen.getByText('Select at least one date target to count over')).toBeInTheDocument();
    expect(updateExportConfig).not.toHaveBeenCalled();
  });

  it('shows all style validation errors and places the style field error after styles', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await user.click(screen.getByRole('button', { name: 'Add Export Rule' }));
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    const fontColorInput = screen.getByTitle('Enter font color in hex');
    const styleFieldError = screen.getByText('At least one style or annotation field is required');
    const appendTextLabel = screen.getByText('Append Text');

    expect(screen.getByText('Select at least one people')).toBeInTheDocument();
    expect(screen.getByText('Select at least one dates')).toBeInTheDocument();
    expect(screen.getByText('Select at least one shift types')).toBeInTheDocument();
    expect(
      fontColorInput.compareDocumentPosition(styleFieldError) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(
      styleFieldError.compareDocumentPosition(appendTextLabel) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(updateExportConfig).not.toHaveBeenCalled();
  });

  it('clears a coefficient error when the count shift type selection changes', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await startExtraColumn(user, ['D', 'WORK']);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'D' }), { target: { value: '2' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'WORK' }), { target: { value: '3' } });
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    expect(screen.getByText('Shift type coefficients overlap: D, WORK include D')).toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: 'D' }));

    expect(screen.queryByText(/Shift type coefficients overlap/)).not.toBeInTheDocument();
  });

  it('preserves unrelated errors when a coefficient changes', async () => {
    const user = userEvent.setup();
    renderExportLayoutPage();

    await user.click(screen.getByRole('button', { name: 'Add Export Rule' }));
    await user.selectOptions(screen.getAllByRole('combobox')[0], 'extra column');
    await user.click(screen.getByRole('checkbox', { name: 'D' }));
    await user.click(screen.getByRole('checkbox', { name: 'N' }));
    await user.click(screen.getByRole('checkbox', { name: '2026-01-01' }));
    await user.click(screen.getByRole('button', { name: 'Add', exact: true }));

    expect(screen.getByText('Column header is required')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('spinbutton', { name: 'D' }), { target: { value: '2' } });

    expect(screen.getByText('Column header is required')).toBeInTheDocument();
  });
});
