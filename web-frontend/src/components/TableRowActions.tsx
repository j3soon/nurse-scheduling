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

// A component for the edit and delete actions of a table row.
import { FiEdit2, FiTrash2 } from 'react-icons/fi';

interface TableRowActionsProps {
  onEdit?: () => void;
  onDelete?: () => void;
}

export function TableRowActions({ onEdit, onDelete }: TableRowActionsProps) {
  if (!onEdit && !onDelete) {
    return null;
  }

  return (
    <div className="flex flex-wrap justify-start gap-2">
      {onEdit && (
        <button
          onClick={onEdit}
          className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
        >
          <FiEdit2 className="h-4 w-4" />
          Edit
        </button>
      )}
      {onDelete && (
        <button
          onClick={onDelete}
          className="text-red-600 hover:text-red-900 flex items-center gap-1"
        >
          <FiTrash2 className="h-4 w-4" />
          Delete
        </button>
      )}
    </div>
  );
}
