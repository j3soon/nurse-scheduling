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
import { CheckboxList } from '@/components/CheckboxList';

describe('CheckboxList', () => {
  it('toggles one item on normal click sequence', () => {
    const onToggle = vi.fn();

    render(
      <CheckboxList
        label="Items"
        items={[{ id: 'A' }, { id: 'B' }]}
        selectedIds={[]}
        onToggle={onToggle}
      />,
    );

    const labelA = screen.getByText('A').closest('label') as HTMLLabelElement;
    fireEvent.mouseEnter(labelA);
    fireEvent.mouseDown(labelA, { button: 0 });
    fireEvent.mouseUp(labelA, { button: 0 });

    expect(onToggle).toHaveBeenCalledWith('A');
  });

  it('supports drag multi-select toggle across items', () => {
    const onToggle = vi.fn();

    render(
      <CheckboxList
        label="Items"
        items={[{ id: 'A' }, { id: 'B' }]}
        selectedIds={[]}
        onToggle={onToggle}
      />,
    );

    const labelA = screen.getByText('A').closest('label') as HTMLLabelElement;
    const labelB = screen.getByText('B').closest('label') as HTMLLabelElement;

    fireEvent.mouseEnter(labelA);
    fireEvent.mouseDown(labelA, { button: 0 });
    fireEvent.mouseLeave(labelA);
    fireEvent.mouseEnter(labelB);
    fireEvent.mouseUp(labelB, { button: 0 });

    expect(onToggle).toHaveBeenNthCalledWith(1, 'A');
    expect(onToggle).toHaveBeenNthCalledWith(2, 'B');
  });

  it('toggles all checkboxes when dragging across them with the mouse button held down', () => {
    const onToggle = vi.fn();

    render(
      <CheckboxList
        label="Items"
        items={[{ id: 'A' }, { id: 'B' }, { id: 'C' }, { id: 'D' }]}
        selectedIds={[]}
        onToggle={onToggle}
      />,
    );

    const labelA = screen.getByText('A').closest('label') as HTMLLabelElement;
    const labelB = screen.getByText('B').closest('label') as HTMLLabelElement;
    const labelC = screen.getByText('C').closest('label') as HTMLLabelElement;
    const labelD = screen.getByText('D').closest('label') as HTMLLabelElement;

    fireEvent.mouseEnter(labelA);
    fireEvent.mouseDown(labelA, { button: 0 });
    fireEvent.mouseLeave(labelA);

    fireEvent.mouseEnter(labelB);
    fireEvent.mouseLeave(labelB);

    fireEvent.mouseEnter(labelC);
    fireEvent.mouseLeave(labelC);

    fireEvent.mouseEnter(labelD);
    fireEvent.mouseUp(labelD, { button: 0 });

    expect(onToggle).toHaveBeenCalledTimes(4);
    expect(onToggle).toHaveBeenNthCalledWith(1, 'A');
    expect(onToggle).toHaveBeenNthCalledWith(2, 'B');
    expect(onToggle).toHaveBeenNthCalledWith(3, 'C');
    expect(onToggle).toHaveBeenNthCalledWith(4, 'D');
  });
});
