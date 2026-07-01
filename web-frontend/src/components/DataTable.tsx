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

// A table component that allows reordering of rows by dragging the mouse.
// Note that this file highly duplicates with DraggableCardList.tsx.
import { ReactNode, useRef, useState } from 'react';
import { ERROR_SHOULD_NOT_HAPPEN } from '../constants/errors';

interface Column<T> {
  header: string;
  accessor: ((item: T, index: number) => ReactNode) | keyof T;
  align?: 'left' | 'center' | 'right';
}

interface DataTableProps<T> {
  title: string;
  columns: Column<T>[];
  data: T[];
  onReorder?: (newData: T[]) => void;
  getRowClassName?: (item: T, index: number) => string;
  onRowClick?: (item: T, index: number) => void;
  headerAction?: ReactNode;
  footer?: ReactNode;
}

export function DataTable<T>({ title, columns, data, onReorder, getRowClassName, onRowClick, headerAction, footer }: DataTableProps<T>) {
  const draggedRowIndexRef = useRef<number | null>(null);
  const [dragOverState, setDragOverState] = useState<{ rowIndex: number; insertAfter: boolean } | null>(null);

  const handleDragStart = (e: React.DragEvent<HTMLTableRowElement>, index: number) => {
    draggedRowIndexRef.current = index;
    e.dataTransfer.setData('text/plain', index.toString());
    e.currentTarget.classList.add('opacity-50');
  };

  const handleDragEnd = (e: React.DragEvent<HTMLTableRowElement>) => {
    draggedRowIndexRef.current = null;
    e.currentTarget.classList.remove('opacity-50');
    setDragOverState(null);
  };

  const handleDragOver = (e: React.DragEvent<HTMLTableRowElement>, rowIndex: number) => {
    if (draggedRowIndexRef.current === null) {
      return;
    }

    e.preventDefault();
    const rect = e.currentTarget.getBoundingClientRect();
    const insertAfter = e.clientY > rect.top + rect.height / 2;
    setDragOverState({ rowIndex, insertAfter });
  };

  const handleDragLeave = () => {
    setDragOverState(null);
  };

  const handleDrop = (e: React.DragEvent<HTMLTableRowElement>, dropIndex: number) => {
    const dragIndex = draggedRowIndexRef.current;
    if (dragIndex === null) {
      setDragOverState(null);
      return;
    }

    e.preventDefault();
    setDragOverState(null);

    if (!onReorder) {
      console.error(`onReorder is not defined. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }

    const rect = e.currentTarget.getBoundingClientRect();
    const insertAfter = e.clientY > rect.top + rect.height / 2;
    const insertionIndex = insertAfter ? dropIndex + 1 : dropIndex;
    const adjustedDropIndex = dragIndex < insertionIndex ? insertionIndex - 1 : insertionIndex;

    const newData = [...data];
    const [draggedItem] = newData.splice(dragIndex, 1);
    newData.splice(adjustedDropIndex, 0, draggedItem);
    onReorder(newData);
  };

  return (
    <div className="bg-white shadow-md rounded-lg overflow-auto h-fit">
      <div className="px-4 py-3 border-b border-gray-200 flex justify-between items-center">
        <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
        {headerAction && <div className="flex items-center">{headerAction}</div>}
      </div>
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((column, index) => {
              const isFirstColumn = index === 0;
              const isThirdColumn = index === 2;
              return (
                <th
                  key={index}
                  className={`px-2 ${isFirstColumn ? 'pl-4' : ''} py-3 text-xs font-medium text-gray-500 uppercase tracking-wider ${
                    column.align === 'right' ? 'text-right' : column.align === 'center' ? 'text-center' : 'text-left'
                  }`}
                  style={isThirdColumn ? { width: '80px', minWidth: '80px', maxWidth: '80px' } : undefined}
                >
                  {column.header}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {data.map((item, rowIndex) => {
            const customClassName = getRowClassName ? getRowClassName(item, rowIndex) : '';
            const isDraggable = !!onReorder && !customClassName.includes('non-draggable');
            return (
              <tr
                key={rowIndex}
                draggable={isDraggable}
                onDragStart={isDraggable ? (e) => handleDragStart(e, rowIndex) : undefined}
                onDragEnd={isDraggable ? handleDragEnd : undefined}
                onDragOver={isDraggable ? (e) => handleDragOver(e, rowIndex) : undefined}
                onDragLeave={isDraggable ? handleDragLeave : undefined}
                onDrop={isDraggable ? (e) => handleDrop(e, rowIndex) : undefined}
                onClick={onRowClick ? () => onRowClick(item, rowIndex) : undefined}
                className={`${onRowClick ? 'cursor-pointer' : isDraggable ? 'cursor-move' : ''} ${isDraggable || onRowClick ? 'hover:bg-gray-50' : ''} ${
                  dragOverState?.rowIndex === rowIndex
                    ? (dragOverState.insertAfter ? 'border-b-2 border-b-blue-500' : 'border-t-2 border-t-blue-500')
                    : ''
                } ${customClassName}`}
              >
              {columns.map((column, colIndex) => {
                const isThirdColumn = colIndex === 2;
                return (
                  <td
                    key={colIndex}
                    className={`${colIndex === 0 ? 'pl-4 pr-2' : 'px-2'} py-1 whitespace-nowrap text-sm font-medium text-gray-900 ${
                      column.align === 'right' ? 'text-right' : column.align === 'center' ? 'text-center' : 'text-left'
                    }`}
                    style={isThirdColumn ? { width: '80px', minWidth: '80px', maxWidth: '80px' } : undefined}
                  >
                    {typeof column.accessor === 'function'
                      ? column.accessor(item, rowIndex)
                      : String(item[column.accessor])}
                  </td>
                );
              })}
                </tr>
              );
            })}
          </tbody>
      </table>
      {footer}
    </div>
  );
}
