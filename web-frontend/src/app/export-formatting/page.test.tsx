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
  beforeEach(() => {
    mockUseSchedulingData.mockReturnValue({
      exportData: { formatting: [] },
      updateExportFormatting: vi.fn(),
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
});
