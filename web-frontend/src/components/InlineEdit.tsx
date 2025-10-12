// A component for inline editing of a item value.
import { useState, useEffect, useRef } from 'react';

interface InlineEditProps {
  value: string;
  isEditing: boolean;
  onSave: (value: string) => void;
  onCancel: () => void;
  onDoubleClick?: () => void;
  placeholder?: string;
  className?: string;
  editClassName?: string;
  error?: string;
  displayValue?: string; // For cases where display differs from edit value
  emptyText?: string; // Text to show when value is empty
  emptyClassName?: string;
}

export function InlineEdit({
  value,
  isEditing,
  onSave,
  onCancel,
  onDoubleClick,
  placeholder,
  className = '',
  editClassName = '',
  error,
  displayValue,
  emptyText,
  emptyClassName = 'text-gray-300 italic'
}: InlineEditProps) {
  const [editValue, setEditValue] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isEditing) {
      setEditValue(value);
    }
  }, [isEditing, value]);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleSave = () => {
    onSave(editValue.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSave();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setEditValue(e.target.value);
  };

  if (isEditing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={editValue}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onBlur={handleSave}
        placeholder={placeholder}
        className={`px-2 py-1 border rounded ${error ? 'border-red-500' : ''} ${editClassName}`}
      />
    );
  }

  const valueToDisplay = displayValue || value;
  const hasValue = valueToDisplay.trim().length > 0;
  const isReadOnly = !onDoubleClick;

  return (
    <div
      onDoubleClick={onDoubleClick}
      className={`${isReadOnly ? '' : 'cursor-pointer'} ${className} ${!hasValue ? emptyClassName : ''}`}
      title={valueToDisplay}
    >
      {hasValue ? valueToDisplay : (emptyText || 'Add...')}
    </div>
  );
}
