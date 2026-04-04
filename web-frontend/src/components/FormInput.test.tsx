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
import { FormInput } from '@/components/FormInput';

describe('FormInput', () => {
  it('forwards onKeyDown to the primary ID input', async () => {
    const user = userEvent.setup();
    const onKeyDown = vi.fn();

    render(
      <FormInput
        itemValue=""
        itemPlaceholder="Enter person ID"
        onItemChange={() => undefined}
        descriptionValue=""
        descriptionPlaceholder="Enter person description"
        onDescriptionChange={() => undefined}
        onKeyDown={onKeyDown}
        onAction={() => undefined}
        onCancel={() => undefined}
        actionText="Add"
      />,
    );

    const idInput = screen.getByPlaceholderText('Enter person ID');
    await user.click(idInput);
    fireEvent.keyDown(idInput, { key: 'Enter' });

    expect(onKeyDown).toHaveBeenCalledTimes(1);
    expect(onKeyDown.mock.calls[0][0].key).toBe('Enter');
  });

  it('calls cancel and action handlers from the footer buttons', async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    const onCancel = vi.fn();

    render(
      <FormInput
        itemValue="P1"
        onItemChange={() => undefined}
        descriptionValue=""
        onDescriptionChange={() => undefined}
        onAction={onAction}
        onCancel={onCancel}
        actionText="Update"
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByRole('button', { name: 'Update' }));

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onAction).toHaveBeenCalledTimes(1);
  });

  it('renders inline errors and child content together', () => {
    render(
      <FormInput
        itemValue=""
        onItemChange={() => undefined}
        descriptionValue=""
        onDescriptionChange={() => undefined}
        error="ID is required"
        onAction={() => undefined}
        onCancel={() => undefined}
        actionText="Add"
      >
        <div>Extra child content</div>
      </FormInput>,
    );

    expect(screen.getByText('ID is required')).toBeInTheDocument();
    expect(screen.getByText('Extra child content')).toBeInTheDocument();
  });
});
