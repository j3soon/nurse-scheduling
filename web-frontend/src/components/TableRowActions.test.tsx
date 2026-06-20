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
import { TableRowActions } from '@/components/TableRowActions';

describe('TableRowActions', () => {
  it('renders nothing when no callbacks are provided', () => {
    const { container } = render(<TableRowActions />);
    expect(container.firstChild).toBeNull();
  });

  it('renders edit, duplicate, and delete buttons when callbacks are provided', async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    const onDuplicate = vi.fn();
    const onDelete = vi.fn();

    render(<TableRowActions onEdit={onEdit} onDuplicate={onDuplicate} onDelete={onDelete} />);

    expect(screen.getByRole('button', { name: /edit/i })).toHaveAttribute('title', 'Edit');
    expect(screen.getByRole('button', { name: /duplicate/i })).toHaveAttribute('title', 'Duplicate');
    expect(screen.getByRole('button', { name: /delete/i })).toHaveAttribute('title', 'Delete');
    expect(screen.getByRole('button', { name: /edit/i }).className).not.toContain('hover:bg');
    expect(screen.getByRole('button', { name: /duplicate/i }).className).not.toContain('hover:bg');
    expect(screen.getByRole('button', { name: /delete/i }).className).not.toContain('hover:bg');
    expect(screen.queryByText('Edit')).not.toBeInTheDocument();
    expect(screen.queryByText('Duplicate')).not.toBeInTheDocument();
    expect(screen.queryByText('Delete')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /edit/i }));
    await user.click(screen.getByRole('button', { name: /duplicate/i }));
    await user.click(screen.getByRole('button', { name: /delete/i }));

    expect(onEdit).toHaveBeenCalledTimes(1);
    expect(onDuplicate).toHaveBeenCalledTimes(1);
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it('renders only the provided action button', () => {
    const { rerender } = render(<TableRowActions onEdit={vi.fn()} />);
    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();

    rerender(<TableRowActions onDelete={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /duplicate/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();

    rerender(<TableRowActions onDuplicate={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /duplicate/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });

  it('supports Space key activation for action buttons', async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();

    render(<TableRowActions onEdit={onEdit} />);

    await user.tab();
    await user.keyboard(' ');

    expect(onEdit).toHaveBeenCalledTimes(1);
  });
});
