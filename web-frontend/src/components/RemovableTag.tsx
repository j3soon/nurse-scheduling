/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2025 Johnson Sun
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

// A tag component that can be removed by clicking a button.
interface RemovableTagProps {
  id: string;
  description?: string;
  onRemove: () => void;
  variant?: 'blue' | 'gray';
  className?: string;
  readOnly?: boolean;
  // Optional drag and drop functionality
  draggable?: boolean;
  index?: number;
  onDragStart?: (index: number) => void;
  onDragOver?: (index: number, e?: React.DragEvent) => void;
  onDragLeave?: () => void;
  onDrop?: (index: number, e?: React.DragEvent) => void;
  onDragEnd?: () => void;
  isDragging?: boolean;
  isDragOver?: boolean;
}

export function RemovableTag({
  id,
  description,
  onRemove,
  variant = 'blue',
  className = '',
  readOnly = false,
  draggable = false,
  index = 0,
  onDragStart,
  onDragOver,
  onDragLeave,
  onDrop,
  onDragEnd,
  isDragging = false,
  isDragOver = false,
}: RemovableTagProps) {
  const baseClasses = "inline-flex items-center text-xs rounded";
  const variantClasses = variant === 'blue'
    ? "bg-blue-100 text-blue-800"
    : "bg-gray-100 text-gray-800";

  const dragClasses = draggable
    ? "cursor-move transition-all"
    : "cursor-default";

  const stateClasses = isDragging
    ? "opacity-50 scale-95"
    : isDragOver
      ? "ring-2 ring-blue-500 bg-blue-200"
      : "";

  const handleDragStart = (e: React.DragEvent) => {
    if (onDragStart) {
      e.dataTransfer.effectAllowed = 'move';
      onDragStart(index);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    if (onDragOver) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      onDragOver(index, e);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    if (onDrop) {
      e.preventDefault();
      onDrop(index, e);
    }
  };

  return (
    <span
      className={`${baseClasses} ${variantClasses} ${dragClasses} ${stateClasses} ${className}`}
      title={description}
      draggable={draggable}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragLeave={onDragLeave}
      onDrop={handleDrop}
      onDragEnd={onDragEnd}
    >
      {!readOnly && (
        <button
          onClick={onRemove}
          className="flex items-center justify-center w-5 py-1 text-blue-600 hover:text-red-600 hover:bg-red-100 rounded-l transition-colors"
          title={`Remove "${id}"`}
        >
          ×
        </button>
      )}
      <span className="px-2 py-1 select-none">
        {id}
      </span>
    </span>
  );
}
