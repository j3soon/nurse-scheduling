// A tag component that can be removed by clicking a button.
interface RemovableTagProps {
  id: string;
  description?: string;
  onRemove: () => void;
  variant?: 'blue' | 'gray';
  className?: string;
  readOnly?: boolean;
}

export function RemovableTag({
  id,
  description,
  onRemove,
  variant = 'blue',
  className = '',
  readOnly = false
}: RemovableTagProps) {
  const baseClasses = "inline-flex items-center text-xs px-2 py-1 rounded cursor-default";
  const variantClasses = variant === 'blue'
    ? "bg-blue-100 text-blue-800"
    : "bg-gray-100 text-gray-800";
  const buttonClasses = variant === 'blue'
    ? "mr-1 text-blue-600 hover:text-blue-900"
    : "mr-1 text-gray-600 hover:text-gray-900";

  return (
    <span
      className={`${baseClasses} ${variantClasses} ${className}`}
      title={description}
    >
      {!readOnly && (
        <button
          onClick={onRemove}
          className={buttonClasses}
          title={`Remove "${id}"`}
        >
          ×
        </button>
      )}
      {id}
    </span>
  );
}
