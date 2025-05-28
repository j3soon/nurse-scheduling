import { FiEdit2, FiTrash2 } from 'react-icons/fi';

interface TableRowActionsProps {
  onEdit: () => void;
  onDelete: () => void;
}

export function TableRowActions({ onEdit, onDelete }: TableRowActionsProps) {
  return (
    <div className="flex justify-end space-x-2">
      <button
        onClick={onEdit}
        className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
      >
        <FiEdit2 className="h-4 w-4" />
        Edit
      </button>
      <button
        onClick={onDelete}
        className="text-red-600 hover:text-red-900 flex items-center gap-1"
      >
        <FiTrash2 className="h-4 w-4" />
        Delete
      </button>
    </div>
  );
} 