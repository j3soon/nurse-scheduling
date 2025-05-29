import { ReactNode } from 'react';
import { ERROR_SHOULD_NOT_HAPPEN } from '../constants/errors';

interface Column<T> {
  header: string;
  accessor: ((item: T) => ReactNode) | keyof T;
  align?: 'left' | 'center' | 'right';
}

interface DataTableProps<T extends Record<string, any>> {
  title: string;
  columns: Column<T>[];
  data: T[];
  onReorder?: (newData: T[]) => void;
}

export function DataTable<T extends Record<string, any>>({ title, columns, data, onReorder }: DataTableProps<T>) {
  const handleDragStart = (e: React.DragEvent<HTMLTableRowElement>, index: number) => {
    e.dataTransfer.setData('text/plain', index.toString());
    e.currentTarget.classList.add('opacity-50');
  };

  const handleDragEnd = (e: React.DragEvent<HTMLTableRowElement>) => {
    e.currentTarget.classList.remove('opacity-50');
  };

  const handleDragOver = (e: React.DragEvent<HTMLTableRowElement>) => {
    e.preventDefault();
    e.currentTarget.classList.add('border-y-2', 'border-blue-500');
  };

  const handleDragLeave = (e: React.DragEvent<HTMLTableRowElement>) => {
    e.currentTarget.classList.remove('border-y-2', 'border-blue-500');
  };

  const handleDrop = (e: React.DragEvent<HTMLTableRowElement>, dropIndex: number) => {
    e.preventDefault();
    e.currentTarget.classList.remove('border-y-2', 'border-blue-500');
    
    const dragIndex = parseInt(e.dataTransfer.getData('text/plain'));
    if (!onReorder) {
      console.error(`onReorder is not defined. ${ERROR_SHOULD_NOT_HAPPEN}`);
      return;
    }

    // The dropIndex here is where the item should be placed.
    const newData = [...data];
    const [draggedItem] = newData.splice(dragIndex, 1);
    newData.splice(dropIndex, 0, draggedItem);
    onReorder(newData);
  };

  return (
    <div className="bg-white shadow-md rounded-lg overflow-auto h-fit">
      <div className="px-6 py-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
      </div>
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            {columns.map((column, index) => (
              <th
                key={index}
                className={`px-6 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider ${
                  column.align === 'right' ? 'text-right' : column.align === 'center' ? 'text-center' : 'text-left'
                }`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {data.map((item, rowIndex) => (
            <tr 
              key={rowIndex}
              draggable={!!onReorder}
              onDragStart={(e) => handleDragStart(e, rowIndex)}
              onDragEnd={handleDragEnd}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, rowIndex)}
              className={`${onReorder ? 'cursor-move hover:bg-gray-50' : ''}`}
            >
              {columns.map((column, colIndex) => (
                <td
                  key={colIndex}
                  className={`px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 ${
                    column.align === 'right' ? 'text-right' : column.align === 'center' ? 'text-center' : 'text-left'
                  }`}
                >
                  {typeof column.accessor === 'function'
                    ? column.accessor(item)
                    : String(item[column.accessor])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
