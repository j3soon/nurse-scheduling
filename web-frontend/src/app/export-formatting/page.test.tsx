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
import ExportFormattingPage from '@/app/export-formatting/page';

const mockUseSchedulingData = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useSchedulingData', () => ({
  useSchedulingData: mockUseSchedulingData,
}));

describe('ExportFormattingPage validation', () => {
  const updateExportFormatting = vi.fn();

  beforeEach(() => {
    updateExportFormatting.mockReset();
    mockUseSchedulingData.mockReturnValue({
      exportData: { formatting: [] },
      updateExportFormatting,
      peopleData: { items: [{ id: 'P1', description: '' }], groups: [] },
      dateData: { items: [{ id: '01', description: '' }], groups: [] },
      shiftTypeData: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    });
  });

  it('shows error when saving without selecting targets', async () => {
    const user = userEvent.setup();

    render(<ExportFormattingPage />);

    await user.click(screen.getByRole('button', { name: /add formatting rule/i }));
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByText('Select at least one target')).toBeInTheDocument();
  });

  it('shows error for invalid hex color input', async () => {
    const user = userEvent.setup();

    render(<ExportFormattingPage />);

    await user.click(screen.getByRole('button', { name: /add formatting rule/i }));
    await user.click(screen.getByText('D'));

    const backgroundInput = screen.getByTitle('Enter background color in hex');
    fireEvent.change(backgroundInput, { target: { value: '#12345' } });

    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(screen.getByText('Background Color must be a valid hex color in #RRGGBB format')).toBeInTheDocument();
  });

  it('submits a valid formatting rule with Enter from the global keyboard handler', async () => {
    const user = userEvent.setup();

    render(<ExportFormattingPage />);

    await user.click(screen.getByRole('button', { name: /add formatting rule/i }));
    await user.selectOptions(screen.getByRole('combobox'), 'row');
    await user.click(screen.getByRole('checkbox', { name: /P1/ }));
    fireEvent.change(screen.getByTitle('Enter background color in hex'), { target: { value: '#abcdef' } });
    fireEvent.keyDown(document, { key: 'Enter' });

    expect(updateExportFormatting).toHaveBeenCalledWith([
      {
        type: 'row',
        targets: ['P1'],
        backgroundColor: '#abcdef',
      },
    ]);
  });

  it('cancels the open form with Escape without persisting a partial edit', async () => {
    const user = userEvent.setup();

    render(<ExportFormattingPage />);

    await user.click(screen.getByRole('button', { name: /add formatting rule/i }));
    await user.selectOptions(screen.getByRole('combobox'), 'column');
    await user.click(screen.getByRole('checkbox', { name: /01/ }));
    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByText('Add New Formatting Rule')).not.toBeInTheDocument();
    expect(updateExportFormatting).not.toHaveBeenCalled();
  });

  it('rejects stale invalid targets when editing a mismatched saved rule', async () => {
    const user = userEvent.setup();

    mockUseSchedulingData.mockReturnValue({
      exportData: {
        formatting: [
          {
            type: 'row',
            targets: ['D'],
            backgroundColor: '#abcdef',
          },
        ],
      },
      updateExportFormatting,
      peopleData: { items: [{ id: 'P1', description: '' }], groups: [] },
      dateData: { items: [{ id: '01', description: '' }], groups: [] },
      shiftTypeData: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    });

    render(<ExportFormattingPage />);

    await user.click(screen.getByRole('button', { name: /edit/i }));
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('Selected targets are invalid for this rule type')).toBeInTheDocument();
    expect(updateExportFormatting).not.toHaveBeenCalled();
  });

  it('blocks saving an edited rule when its previously valid targets disappear', async () => {
    const user = userEvent.setup();

    mockUseSchedulingData.mockReturnValue({
      exportData: {
        formatting: [
          {
            type: 'row',
            targets: ['P1'],
            backgroundColor: '#abcdef',
          },
        ],
      },
      updateExportFormatting,
      peopleData: { items: [{ id: 'P1', description: '' }], groups: [] },
      dateData: { items: [{ id: '01', description: '' }], groups: [] },
      shiftTypeData: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    });

    const { rerender } = render(<ExportFormattingPage />);

    await user.click(screen.getByRole('button', { name: /edit/i }));

    mockUseSchedulingData.mockReturnValue({
      exportData: {
        formatting: [
          {
            type: 'row',
            targets: ['P1'],
            backgroundColor: '#abcdef',
          },
        ],
      },
      updateExportFormatting,
      peopleData: { items: [], groups: [] },
      dateData: { items: [{ id: '01', description: '' }], groups: [] },
      shiftTypeData: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    });
    rerender(<ExportFormattingPage />);

    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(screen.getByText('Selected targets are invalid for this rule type')).toBeInTheDocument();
    expect(updateExportFormatting).not.toHaveBeenCalled();
  });

  it('normalizes edited color values before saving', async () => {
    const user = userEvent.setup();

    render(<ExportFormattingPage />);

    await user.click(screen.getByRole('button', { name: /add formatting rule/i }));
    await user.click(screen.getByText('D'));
    fireEvent.change(screen.getByTitle('Enter background color in hex'), { target: { value: '  #ABCDEF  ' } });
    fireEvent.change(screen.getByTitle('Enter bottom border color in hex'), { target: { value: ' #123ABC ' } });
    await user.click(screen.getByRole('button', { name: 'Add' }));

    expect(updateExportFormatting).toHaveBeenCalledWith([
      {
        type: 'cell',
        targets: ['D'],
        backgroundColor: '#abcdef',
        bottomBorderColor: '#123abc',
      },
    ]);
  });

  it('preserves rule order when editing one formatting rule without reordering', async () => {
    const user = userEvent.setup();

    mockUseSchedulingData.mockReturnValue({
      exportData: {
        formatting: [
          { type: 'row', targets: ['P1'], backgroundColor: '#111111' },
          { type: 'cell', targets: ['D'], backgroundColor: '#222222' },
        ],
      },
      updateExportFormatting,
      peopleData: { items: [{ id: 'P1', description: '' }], groups: [] },
      dateData: { items: [{ id: '01', description: '' }], groups: [] },
      shiftTypeData: { items: [{ id: 'D', description: 'Day' }], groups: [] },
    });

    render(<ExportFormattingPage />);

    await user.click(screen.getAllByRole('button', { name: /edit/i })[1]);
    fireEvent.change(screen.getByTitle('Enter background color in hex'), { target: { value: '#333333' } });
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(updateExportFormatting).toHaveBeenCalledWith([
      { type: 'row', targets: ['P1'], backgroundColor: '#111111' },
      { type: 'cell', targets: ['D'], backgroundColor: '#333333' },
    ]);
  });
});
