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

import { render, screen } from '@testing-library/react';
import { CountShiftTypeCoefficientFields } from '@/components/CountShiftTypeCoefficientFields';

const shiftTypeEntries = [
  { id: 'D' },
  { id: 'N' },
  { id: 'WORK' },
];
const shiftTypeData = {
  items: [
    { id: 'D', description: 'Day' },
    { id: 'N', description: 'Night' },
  ],
  groups: [{ id: 'WORK', members: ['D', 'N'], description: 'Working shifts' }],
};

describe('CountShiftTypeCoefficientFields', () => {
  it('shows a hint instead of fields when no shift type is selected', () => {
    render(
      <CountShiftTypeCoefficientFields
        selectedShiftTypeIds={[]}
        coefficients={[]}
        shiftTypeEntries={shiftTypeEntries}
        shiftTypeData={shiftTypeData}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('Count Shift Type Coefficients')).toBeInTheDocument();
    expect(screen.getByText('Coefficients are not needed when no count shift type is selected.')).toBeInTheDocument();
  });

  it('shows coefficient inputs when one shift type is selected', () => {
    render(
      <CountShiftTypeCoefficientFields
        selectedShiftTypeIds={['D']}
        coefficients={[]}
        shiftTypeEntries={shiftTypeEntries}
        shiftTypeData={shiftTypeData}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('Count Shift Type Coefficients')).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'D' })).toHaveValue(null);
  });

  it('shows coefficient inputs when more than one shift type is selected', () => {
    render(
      <CountShiftTypeCoefficientFields
        selectedShiftTypeIds={['D', 'N']}
        coefficients={[]}
        shiftTypeEntries={shiftTypeEntries}
        shiftTypeData={shiftTypeData}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('Count Shift Type Coefficients')).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'D' })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'N' })).toBeInTheDocument();
  });

  it('shows selected group members and fully covered groups', () => {
    render(
      <CountShiftTypeCoefficientFields
        selectedShiftTypeIds={['WORK']}
        coefficients={[]}
        shiftTypeEntries={shiftTypeEntries}
        shiftTypeData={shiftTypeData}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByRole('spinbutton', { name: 'D' })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'N' })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'WORK' })).toBeInTheDocument();
  });

  it('uses one selected shift type as the fixed threshold for the hint', () => {
    render(
      <CountShiftTypeCoefficientFields
        selectedShiftTypeIds={[]}
        coefficients={[]}
        shiftTypeEntries={shiftTypeEntries}
        shiftTypeData={shiftTypeData}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText('Coefficients are not needed when no count shift type is selected.')).toBeInTheDocument();
  });
});
