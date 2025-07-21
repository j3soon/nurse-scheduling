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
  onDragOver?: (index: number) => void;
  onDragLeave?: () => void;
  onDrop?: (index: number) => void;
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
      onDragOver(index);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    if (onDrop) {
      e.preventDefault();
      onDrop(index);
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
          className="flex items-center justify-center w-5 h-full text-blue-600 hover:text-red-600 hover:bg-red-100 rounded-l transition-colors"
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
