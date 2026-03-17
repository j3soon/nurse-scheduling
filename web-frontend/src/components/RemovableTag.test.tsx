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
import { RemovableTag } from '@/components/RemovableTag';

describe('RemovableTag', () => {
  it('calls onRemove when remove button is clicked', () => {
    const onRemove = vi.fn();

    render(<RemovableTag id="P1" onRemove={onRemove} />);

    fireEvent.click(screen.getByRole('button', { name: '×' }));

    expect(onRemove).toHaveBeenCalledTimes(1);
  });

  it('hides remove button in readOnly mode', () => {
    render(<RemovableTag id="P1" onRemove={vi.fn()} readOnly={true} />);

    expect(screen.queryByRole('button', { name: '×' })).not.toBeInTheDocument();
    expect(screen.getByText('P1')).toBeInTheDocument();
  });

  it('applies drag state classes and triggers drag callbacks', () => {
    const onDragStart = vi.fn();
    const onDragOver = vi.fn();
    const onDrop = vi.fn();
    const onDragEnd = vi.fn();

    const { rerender } = render(
      <RemovableTag
        id="P1"
        onRemove={vi.fn()}
        draggable={true}
        index={3}
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDrop={onDrop}
        onDragEnd={onDragEnd}
      />,
    );

    const tag = screen.getByText('P1').closest('span') as HTMLSpanElement;
    const dataTransfer = {
      effectAllowed: '',
      dropEffect: '',
      setData: vi.fn(),
      getData: vi.fn(),
    };

    fireEvent.dragStart(tag, { dataTransfer });
    fireEvent.dragOver(tag, { dataTransfer });
    fireEvent.drop(tag, { dataTransfer });
    fireEvent.dragEnd(tag);

    expect(onDragStart).toHaveBeenCalledWith(3);
    expect(onDragOver).toHaveBeenCalled();
    expect(onDrop).toHaveBeenCalled();
    expect(onDragEnd).toHaveBeenCalled();

    rerender(
      <RemovableTag
        id="P1"
        onRemove={vi.fn()}
        isDragging={true}
      />,
    );
    expect(screen.getByText('P1').parentElement).toHaveClass('opacity-50');

    rerender(
      <RemovableTag
        id="P1"
        onRemove={vi.fn()}
        isDragOver={true}
      />,
    );
    expect(screen.getByText('P1').parentElement).toHaveClass('ring-2');
  });

  it('renders description tooltip in read-only mode', () => {
    render(<RemovableTag id="P1" description="Primary nurse" onRemove={vi.fn()} readOnly={true} />);

    expect(screen.getByText('P1').closest('[title="Primary nurse"]')).toBeInTheDocument();
    expect(screen.queryByTitle('Remove "P1"')).not.toBeInTheDocument();
  });

  it('triggers drag leave callback when provided', () => {
    const onDragLeave = vi.fn();

    render(
      <RemovableTag
        id="P1"
        onRemove={vi.fn()}
        draggable={true}
        onDragLeave={onDragLeave}
      />,
    );

    fireEvent.dragLeave(screen.getByText('P1').closest('span') as HTMLSpanElement);

    expect(onDragLeave).toHaveBeenCalledTimes(1);
  });

  it('sets drag-over event semantics for drop targets', () => {
    const onDragOver = vi.fn();
    const dataTransfer = { dropEffect: '' };

    render(
      <RemovableTag
        id="P1"
        onRemove={vi.fn()}
        draggable={true}
        index={2}
        onDragOver={onDragOver}
      />,
    );

    fireEvent.dragOver(screen.getByText('P1').closest('span') as HTMLSpanElement, {
      dataTransfer,
    });

    expect(dataTransfer.dropEffect).toBe('move');
    expect(onDragOver).toHaveBeenCalledWith(2, expect.any(Object));
  });
});
