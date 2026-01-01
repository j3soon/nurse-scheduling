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

// A list component that allows reordering of card items by dragging.
// Note that this file highly duplicates with DataTable.tsx.
import { ReactNode } from 'react';
import { ERROR_SHOULD_NOT_HAPPEN } from '../constants/errors';
import { FiEdit2, FiTrash2 } from 'react-icons/fi';

interface DraggableCardListProps<T> {
  title: string;
  items: T[];
  emptyMessage: string;
  renderContent: (item: T, index: number) => ReactNode;
  onEdit: (index: number) => void;
  onDelete: (index: number) => void;
  onReorder?: (newItems: T[]) => void;
}

export function DraggableCardList<T>({
  title,
  items,
  emptyMessage,
  renderContent,
  onEdit,
  onDelete,
  onReorder,
}: DraggableCardListProps<T>) {
  const handleDragStart = (e: React.DragEvent<HTMLDivElement>, index: number) => {
    e.dataTransfer.setData('text/plain', index.toString());
    e.currentTarget.classList.add('opacity-50');
  };

  const handleDragEnd = (e: React.DragEvent<HTMLDivElement>) => {
    e.currentTarget.classList.remove('opacity-50');
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.currentTarget.classList.add('border-t-2', 'border-t-blue-500');
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.currentTarget.classList.remove('border-t-2', 'border-t-blue-500');
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>, dropIndex: number) => {
    e.preventDefault();
    e.currentTarget.classList.remove('border-t-2', 'border-t-blue-500');

    const dragIndex = parseInt(e.dataTransfer.getData('text/plain'));
    if (!onReorder) {
      console.error(`onReorder is not defined. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }

    // The dropIndex here is where the item should be placed.
    const newItems = [...items];
    const [draggedItem] = newItems.splice(dragIndex, 1);
    newItems.splice(dropIndex, 0, draggedItem);
    onReorder(newItems);
  };

  return (
    <div className="bg-white shadow-md rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200">
        <h3 className="text-lg font-semibold text-gray-800">{title}</h3>
      </div>

      {items.length === 0 ? (
        <div className="px-6 py-8 text-center text-gray-500">
          {emptyMessage}
        </div>
      ) : (
        <div className="divide-y divide-gray-200">
          {items.map((item, index) => {
            const isDraggable = !!onReorder;
            return (
              <div
                key={index}
                className={`px-4 py-2 ${isDraggable ? 'cursor-move hover:bg-gray-50' : ''}`}
                draggable={isDraggable}
                onDragStart={isDraggable ? (e) => handleDragStart(e, index) : undefined}
                onDragEnd={isDraggable ? handleDragEnd : undefined}
                onDragOver={isDraggable ? handleDragOver : undefined}
                onDragLeave={isDraggable ? handleDragLeave : undefined}
                onDrop={isDraggable ? (e) => handleDrop(e, index) : undefined}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    {renderContent(item, index)}
                  </div>
                  <div className="flex justify-end space-x-2 ml-4">
                    <button
                      onClick={() => onEdit(index)}
                      className="text-blue-600 hover:text-blue-900 flex items-center gap-1 text-sm"
                    >
                      <FiEdit2 className="h-4 w-4" />
                      Edit
                    </button>
                    <button
                      onClick={() => onDelete(index)}
                      className="text-red-600 hover:text-red-900 flex items-center gap-1 text-sm"
                    >
                      <FiTrash2 className="h-4 w-4" />
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
