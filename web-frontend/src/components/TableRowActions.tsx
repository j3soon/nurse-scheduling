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

// A component for the edit, duplicate, and delete actions of a table row.
import { FiCopy, FiEdit2, FiTrash2 } from 'react-icons/fi';

interface TableRowActionsProps {
  onEdit?: () => void;
  onDuplicate?: () => void;
  onDelete?: () => void;
}

export function TableRowActions({ onEdit, onDuplicate, onDelete }: TableRowActionsProps) {
  if (!onEdit && !onDuplicate && !onDelete) {
    return null;
  }

  const editClassName = 'inline-flex h-8 w-8 items-center justify-center rounded text-blue-600 hover:text-blue-900';
  const duplicateClassName = 'inline-flex h-8 w-8 items-center justify-center rounded text-indigo-600 hover:text-indigo-800';
  const deleteClassName = 'inline-flex h-8 w-8 items-center justify-center rounded text-red-600 hover:text-red-900';

  return (
    <div className="flex flex-nowrap justify-start gap-1">
      {onEdit && (
        <button
          type="button"
          aria-label="Edit"
          title="Edit"
          onClick={onEdit}
          className={editClassName}
        >
          <FiEdit2 className="h-4 w-4" />
        </button>
      )}
      {onDuplicate && (
        <button
          type="button"
          aria-label="Duplicate"
          title="Duplicate"
          onClick={onDuplicate}
          className={duplicateClassName}
        >
          <FiCopy className="h-4 w-4" />
        </button>
      )}
      {onDelete && (
        <button
          type="button"
          aria-label="Delete"
          title="Delete"
          onClick={onDelete}
          className={deleteClassName}
        >
          <FiTrash2 className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
