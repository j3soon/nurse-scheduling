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
import WeightInput from '@/components/WeightInput';

describe('WeightInput', () => {
  it('parses shorthand number input and reports parsed value', () => {
    const onChange = vi.fn();

    render(<WeightInput value={0} onChange={onChange} />);

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: '10k' } });

    expect(onChange).toHaveBeenLastCalledWith(10000);
  });

  it('sets positive and negative infinity using action buttons', () => {
    const onChange = vi.fn();

    render(<WeightInput value={0} onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: '+∞' }));
    fireEvent.click(screen.getByRole('button', { name: '-∞' }));

    expect(onChange).toHaveBeenNthCalledWith(1, Infinity);
    expect(onChange).toHaveBeenNthCalledWith(2, -Infinity);
  });

  it('renders validation error text when error is provided', () => {
    render(<WeightInput value={0} onChange={vi.fn()} error="Invalid weight" />);

    expect(screen.getByText('Invalid weight')).toBeInTheDocument();
  });
});
