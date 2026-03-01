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
import { InlineEdit } from '@/components/InlineEdit';

describe('InlineEdit', () => {
  it('renders display mode and supports double click callback', async () => {
    const user = userEvent.setup();
    const onDoubleClick = vi.fn();

    render(
      <InlineEdit
        value="Nurse A"
        isEditing={false}
        onSave={vi.fn()}
        onCancel={vi.fn()}
        onDoubleClick={onDoubleClick}
      />,
    );

    const value = screen.getByText('Nurse A');
    await user.dblClick(value);
    expect(onDoubleClick).toHaveBeenCalledTimes(1);
  });

  it('renders placeholder text when value is empty', () => {
    render(
      <InlineEdit
        value=""
        isEditing={false}
        onSave={vi.fn()}
        onCancel={vi.fn()}
        emptyText="Add person"
      />,
    );

    expect(screen.getByText('Add person')).toBeInTheDocument();
  });

  it('saves trimmed input on Enter', async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();

    render(
      <InlineEdit
        value="  Nurse B  "
        isEditing={true}
        onSave={onSave}
        onCancel={vi.fn()}
      />,
    );

    const input = screen.getByRole('textbox');
    await user.clear(input);
    await user.type(input, '  Nurse C  ');
    await user.keyboard('{Enter}');

    expect(onSave).toHaveBeenCalledWith('Nurse C');
  });

  it('cancels on Escape', async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();

    render(
      <InlineEdit
        value="Nurse D"
        isEditing={true}
        onSave={vi.fn()}
        onCancel={onCancel}
      />,
    );

    await user.keyboard('{Escape}');
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
