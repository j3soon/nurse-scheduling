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
import { DataTable } from '@/components/DataTable';

type Row = { id: string; name: string };

const columns = [
  { header: 'ID', accessor: 'id' as const },
  { header: 'Name', accessor: 'name' as const },
];

function createDataTransfer() {
  const store = new Map<string, string>();
  return {
    setData: (key: string, value: string) => store.set(key, value),
    getData: (key: string) => store.get(key) ?? '',
  };
}

describe('DataTable', () => {
  it('calls onReorder with reordered rows after drag and drop', () => {
    const onReorder = vi.fn();
    const data: Row[] = [
      { id: 'a', name: 'Alpha' },
      { id: 'b', name: 'Beta' },
      { id: 'c', name: 'Gamma' },
    ];

    const { container } = render(
      <DataTable<Row>
        title="Rows"
        columns={columns}
        data={data}
        onReorder={onReorder}
      />,
    );

    expect(screen.getByText('Rows')).toBeInTheDocument();

    const rows = container.querySelectorAll('tbody tr');
    const sourceRow = rows[0] as HTMLTableRowElement;
    const targetRow = rows[2] as HTMLTableRowElement;
    const dataTransfer = createDataTransfer();
    dataTransfer.setData('text/plain', '0');

    fireEvent.dragStart(sourceRow, { dataTransfer });
    fireEvent.drop(targetRow, { dataTransfer, clientY: 1 });

    expect(onReorder).toHaveBeenCalledTimes(1);
    expect(onReorder).toHaveBeenCalledWith([
      { id: 'b', name: 'Beta' },
      { id: 'a', name: 'Alpha' },
      { id: 'c', name: 'Gamma' },
    ]);
  });

  it('does not make rows draggable when getRowClassName marks them non-draggable', () => {
    const data: Row[] = [{ id: 'a', name: 'Alpha' }];

    const { container } = render(
      <DataTable<Row>
        title="Rows"
        columns={columns}
        data={data}
        onReorder={vi.fn()}
        getRowClassName={() => 'non-draggable'}
      />,
    );

    const row = container.querySelector('tbody tr') as HTMLTableRowElement;
    expect(row.getAttribute('draggable')).toBe('false');
  });

  it('does not make rows draggable when onReorder is undefined', () => {
    const data: Row[] = [{ id: 'a', name: 'Alpha' }];

    const { container } = render(
      <DataTable<Row>
        title="Rows"
        columns={columns}
        data={data}
      />,
    );

    const row = container.querySelector('tbody tr') as HTMLTableRowElement;
    expect(row.getAttribute('draggable')).toBe('false');
  });

  it('calls onRowClick when a row is clicked', () => {
    const onRowClick = vi.fn();
    const data: Row[] = [{ id: 'a', name: 'Alpha' }];

    render(
      <DataTable<Row>
        title="Rows"
        columns={columns}
        data={data}
        onRowClick={onRowClick}
      />,
    );

    fireEvent.click(screen.getByText('Alpha').closest('tr') as HTMLTableRowElement);

    expect(onRowClick).toHaveBeenCalledWith({ id: 'a', name: 'Alpha' }, 0);
  });

  it('renders footer content below the table', () => {
    const data: Row[] = [{ id: 'a', name: 'Alpha' }];

    render(
      <DataTable<Row>
        title="Rows"
        columns={columns}
        data={data}
        footer={<div>Footer action</div>}
      />,
    );

    expect(screen.getByText('Footer action')).toBeInTheDocument();
  });

  it('keeps order unchanged when dropping onto the same row index', () => {
    const onReorder = vi.fn();
    const data: Row[] = [
      { id: 'a', name: 'Alpha' },
      { id: 'b', name: 'Beta' },
    ];

    const { container } = render(
      <DataTable<Row>
        title="Rows"
        columns={columns}
        data={data}
        onReorder={onReorder}
      />,
    );

    const row = container.querySelectorAll('tbody tr')[0] as HTMLTableRowElement;
    const dataTransfer = createDataTransfer();
    dataTransfer.setData('text/plain', '0');

    fireEvent.dragStart(row, { dataTransfer });
    fireEvent.drop(row, { dataTransfer, clientY: 0 });

    expect(onReorder).toHaveBeenCalledWith([
      { id: 'a', name: 'Alpha' },
      { id: 'b', name: 'Beta' },
    ]);
  });

  it('clears drag-over visual state on drag leave', () => {
    const data: Row[] = [
      { id: 'a', name: 'Alpha' },
      { id: 'b', name: 'Beta' },
    ];

    const { container } = render(
      <DataTable<Row>
        title="Rows"
        columns={columns}
        data={data}
        onReorder={vi.fn()}
      />,
    );

    const row = container.querySelectorAll('tbody tr')[1] as HTMLTableRowElement;
    const dataTransfer = createDataTransfer();

    fireEvent.dragStart(row, { dataTransfer });
    fireEvent.dragOver(row, { dataTransfer, clientY: 0 });
    expect(row.className).toMatch(/border-(t|b)-2/);

    fireEvent.dragLeave(row);
    expect(row.className).not.toMatch(/border-(t|b)-2/);
    fireEvent.dragEnd(row, { dataTransfer });
  });

  it('ignores drops from another table', () => {
    const sourceOnReorder = vi.fn();
    const targetOnReorder = vi.fn();
    const sourceData: Row[] = [
      { id: 'group-a', name: 'Group Alpha' },
      { id: 'group-b', name: 'Group Beta' },
    ];
    const targetData: Row[] = [
      { id: 'person-a', name: 'Person Alpha' },
      { id: 'person-b', name: 'Person Beta' },
    ];

    const { container } = render(
      <>
        <DataTable<Row>
          title="Groups"
          columns={columns}
          data={sourceData}
          onReorder={sourceOnReorder}
        />
        <DataTable<Row>
          title="People"
          columns={columns}
          data={targetData}
          onReorder={targetOnReorder}
        />
      </>,
    );

    const sourceRow = screen.getByText('Group Alpha').closest('tr') as HTMLTableRowElement;
    const targetRow = screen.getByText('Person Beta').closest('tr') as HTMLTableRowElement;
    const dataTransfer = createDataTransfer();

    fireEvent.dragStart(sourceRow, { dataTransfer });
    fireEvent.dragOver(targetRow, { dataTransfer, clientY: 0 });
    expect(targetRow.className).not.toMatch(/border-(t|b)-2/);

    fireEvent.drop(targetRow, { dataTransfer, clientY: 0 });
    fireEvent.dragEnd(sourceRow, { dataTransfer });

    expect(sourceOnReorder).not.toHaveBeenCalled();
    expect(targetOnReorder).not.toHaveBeenCalled();
    expect(container.querySelectorAll('tbody tr')).toHaveLength(4);
  });
});
