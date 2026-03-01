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

  it('calls edit and delete callbacks for the selected card', () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();

    render(
      <DraggableCardList<Card>
        title="Rules"
        items={[{ title: 'A' }]}
        emptyMessage="No rules"
        renderContent={(item) => <span>{item.title}</span>}
        onEdit={onEdit}
        onDelete={onDelete}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    fireEvent.click(screen.getByRole('button', { name: /delete/i }));

    expect(onEdit).toHaveBeenCalledWith(0);
    expect(onDelete).toHaveBeenCalledWith(0);
  });
});
