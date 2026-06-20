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
import { DraggableCardList } from '@/components/DraggableCardList';

type Card = { title: string };

function createDataTransfer() {
  const store = new Map<string, string>();
  return {
    setData: (key: string, value: string) => store.set(key, value),
    getData: (key: string) => store.get(key) ?? '',
  };
}

describe('DraggableCardList', () => {
  it('reorders items on drag and drop', () => {
    const onReorder = vi.fn();
    const items: Card[] = [{ title: 'A' }, { title: 'B' }, { title: 'C' }];

    const { container } = render(
      <DraggableCardList<Card>
        title="Rules"
        items={items}
        emptyMessage="No rules"
        renderContent={(item) => <span>{item.title}</span>}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onReorder={onReorder}
      />,
    );

    const cards = container.querySelectorAll('[draggable="true"]');
    const source = cards[0] as HTMLDivElement;
    const target = cards[2] as HTMLDivElement;
    const dataTransfer = createDataTransfer();
    dataTransfer.setData('text/plain', '0');

    fireEvent.dragStart(source, { dataTransfer });
    fireEvent.drop(target, { dataTransfer, clientY: 1 });

    expect(onReorder).toHaveBeenCalledWith([{ title: 'B' }, { title: 'A' }, { title: 'C' }]);
  });

  it('calls edit, duplicate, and delete callbacks for the selected card', () => {
    const onEdit = vi.fn();
    const onDuplicate = vi.fn();
    const onDelete = vi.fn();

    render(
      <DraggableCardList<Card>
        title="Rules"
        items={[{ title: 'A' }]}
        emptyMessage="No rules"
        renderContent={(item) => <span>{item.title}</span>}
        onEdit={onEdit}
        onDuplicate={onDuplicate}
        onDelete={onDelete}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    fireEvent.click(screen.getByRole('button', { name: /duplicate/i }));
    fireEvent.click(screen.getByRole('button', { name: /delete/i }));

    expect(onEdit).toHaveBeenCalledWith(0);
    expect(onDuplicate).toHaveBeenCalledWith(0);
    expect(onDelete).toHaveBeenCalledWith(0);
  });

  it('renders empty state without action buttons when list is empty', () => {
    render(
      <DraggableCardList<Card>
        title="Rules"
        items={[]}
        emptyMessage="No rules"
        renderContent={(item) => <span>{item.title}</span>}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText('No rules')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /edit/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /duplicate/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });

  it('supports keyboard activation for edit, duplicate, and delete buttons', async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    const onDuplicate = vi.fn();
    const onDelete = vi.fn();

    render(
      <DraggableCardList<Card>
        title="Rules"
        items={[{ title: 'A' }]}
        emptyMessage="No rules"
        renderContent={(item) => <span>{item.title}</span>}
        onEdit={onEdit}
        onDuplicate={onDuplicate}
        onDelete={onDelete}
      />,
    );

    await user.tab();
    await user.keyboard('{Enter}');
    await user.tab();
    await user.keyboard('{Enter}');
    await user.tab();
    await user.keyboard('{Enter}');

    expect(onEdit).toHaveBeenCalledWith(0);
    expect(onDuplicate).toHaveBeenCalledWith(0);
    expect(onDelete).toHaveBeenCalledWith(0);
  });

  it('reorders items with insert-after drop logic and toggles drag-over styles', () => {
    const onReorder = vi.fn();
    const items: Card[] = [{ title: 'A' }, { title: 'B' }, { title: 'C' }];

    const { container } = render(
      <DraggableCardList<Card>
        title="Rules"
        items={items}
        emptyMessage="No rules"
        renderContent={(item) => <span>{item.title}</span>}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onReorder={onReorder}
      />,
    );

    const cards = container.querySelectorAll('[draggable="true"]');
    const source = cards[0] as HTMLDivElement;
    const target = cards[1] as HTMLDivElement;
    const dataTransfer = createDataTransfer();
    dataTransfer.setData('text/plain', '0');

    vi.spyOn(target, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      width: 100,
      height: 100,
      top: 0,
      right: 100,
      bottom: 100,
      left: 0,
      toJSON: () => ({}),
    });

    fireEvent.dragStart(source, { dataTransfer });
    fireEvent.dragOver(target, { dataTransfer, clientY: 80 });
    expect(target.className).toMatch(/border-(t|b)-2/);

    fireEvent.dragLeave(target);
    expect(target.className).not.toContain('border-b-2');

    fireEvent.drop(target, { dataTransfer, clientY: 80 });
    expect(onReorder).toHaveBeenCalledWith([{ title: 'A' }, { title: 'B' }, { title: 'C' }]);
  });

  it('renders cards as non-draggable when onReorder is missing', () => {
    const items: Card[] = [{ title: 'A' }, { title: 'B' }];

    const { container } = render(
      <DraggableCardList<Card>
        title="Rules"
        items={items}
        emptyMessage="No rules"
        renderContent={(item) => <span>{item.title}</span>}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    const cards = container.querySelectorAll('[draggable="false"]');
    expect(cards).toHaveLength(2);
  });

  it('reorders the last item to the front when dropped in the top half of the first card', () => {
    const onReorder = vi.fn();
    const items: Card[] = [{ title: 'A' }, { title: 'B' }, { title: 'C' }];

    const { container } = render(
      <DraggableCardList<Card>
        title="Rules"
        items={items}
        emptyMessage="No rules"
        renderContent={(item) => <span>{item.title}</span>}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onReorder={onReorder}
      />,
    );

    const cards = container.querySelectorAll('[draggable="true"]');
    const source = cards[2] as HTMLDivElement;
    const target = cards[0] as HTMLDivElement;
    const dataTransfer = createDataTransfer();
    dataTransfer.setData('text/plain', '2');

    vi.spyOn(target, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      width: 100,
      height: 100,
      top: 0,
      right: 100,
      bottom: 100,
      left: 0,
      toJSON: () => ({}),
    });

    fireEvent.dragStart(source, { dataTransfer });
    fireEvent.drop(target, { dataTransfer, clientY: 10 });

    expect(onReorder).toHaveBeenCalledWith([{ title: 'C' }, { title: 'A' }, { title: 'B' }]);
  });

  it('keeps the same order when an item is dropped back onto its current insert-after position', () => {
    const onReorder = vi.fn();
    const items: Card[] = [{ title: 'A' }, { title: 'B' }, { title: 'C' }];

    const { container } = render(
      <DraggableCardList<Card>
        title="Rules"
        items={items}
        emptyMessage="No rules"
        renderContent={(item) => <span>{item.title}</span>}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onReorder={onReorder}
      />,
    );

    const cards = container.querySelectorAll('[draggable="true"]');
    const source = cards[1] as HTMLDivElement;
    const target = cards[1] as HTMLDivElement;
    const dataTransfer = createDataTransfer();
    dataTransfer.setData('text/plain', '1');

    vi.spyOn(target, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      width: 100,
      height: 100,
      top: 0,
      right: 100,
      bottom: 100,
      left: 0,
      toJSON: () => ({}),
    });

    fireEvent.dragStart(source, { dataTransfer });
    fireEvent.drop(target, { dataTransfer, clientY: 90 });

    expect(onReorder).toHaveBeenCalledWith([{ title: 'A' }, { title: 'B' }, { title: 'C' }]);
  });

  it('clears drag-start visual state on drag end', () => {
    const items: Card[] = [{ title: 'A' }, { title: 'B' }];

    const { container } = render(
      <DraggableCardList<Card>
        title="Rules"
        items={items}
        emptyMessage="No rules"
        renderContent={(item) => <span>{item.title}</span>}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onReorder={vi.fn()}
      />,
    );

    const card = container.querySelector('[draggable="true"]') as HTMLDivElement;
    const dataTransfer = createDataTransfer();

    fireEvent.dragStart(card, { dataTransfer });
    expect(card.className).toContain('opacity-50');

    fireEvent.dragEnd(card);
    expect(card.className).not.toContain('opacity-50');
    expect(card.className).not.toContain('border-t-2');
    expect(card.className).not.toContain('border-b-2');
  });

  it('moves drag-over highlight from one target to another', () => {
    const items: Card[] = [{ title: 'A' }, { title: 'B' }, { title: 'C' }];

    const { container } = render(
      <DraggableCardList<Card>
        title="Rules"
        items={items}
        emptyMessage="No rules"
        renderContent={(item) => <span>{item.title}</span>}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onReorder={vi.fn()}
      />,
    );

    const cards = container.querySelectorAll('[draggable="true"]');
    const source = cards[0] as HTMLDivElement;
    const firstTarget = cards[1] as HTMLDivElement;
    const secondTarget = cards[2] as HTMLDivElement;
    const dataTransfer = createDataTransfer();
    dataTransfer.setData('text/plain', '0');

    vi.spyOn(firstTarget, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 0,
      width: 100,
      height: 100,
      top: 0,
      right: 100,
      bottom: 100,
      left: 0,
      toJSON: () => ({}),
    });
    vi.spyOn(secondTarget, 'getBoundingClientRect').mockReturnValue({
      x: 0,
      y: 100,
      width: 100,
      height: 100,
      top: 100,
      right: 100,
      bottom: 200,
      left: 0,
      toJSON: () => ({}),
    });

    fireEvent.dragStart(source, { dataTransfer });
    fireEvent.dragOver(firstTarget, { dataTransfer, clientY: 110 });
    expect(firstTarget.className).toMatch(/border-(t|b)-2/);

    fireEvent.dragOver(secondTarget, { dataTransfer, clientY: 190 });
    expect(firstTarget.className).not.toMatch(/border-(t|b)-2/);
    expect(secondTarget.className).toMatch(/border-(t|b)-2/);
  });
});
