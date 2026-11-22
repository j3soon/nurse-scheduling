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

// A component for inline editing of a item value.
import { useEffect, useRef } from 'react';
import { isImeCompositionKeyEvent } from '@/utils/keyboardEvents';

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
  tapToEdit?: boolean; // Start editing on a single touch or pen tap
  multiline?: boolean;
  ariaLabel?: string;
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
  emptyClassName = 'text-gray-300 italic',
  tapToEdit = true,
  multiline = false,
  ariaLabel,
}: InlineEditProps) {
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus({ preventScroll: multiline });
      inputRef.current.select();
    }
  }, [isEditing, multiline]);

  const handleSave = () => {
    const draft = inputRef.current?.value ?? value;
    onSave(multiline ? draft : draft.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !(multiline && e.shiftKey) && !isImeCompositionKeyEvent(e)) {
      e.preventDefault();
      handleSave();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
    }
  };

  if (isEditing) {
    const editorProps = {
      ref: (element: HTMLInputElement | HTMLTextAreaElement | null) => { inputRef.current = element; },
      defaultValue: value,
      onKeyDown: handleKeyDown,
      onBlur: handleSave,
      placeholder,
      'aria-label': ariaLabel,
      className: `px-2 py-1 border rounded ${error ? 'border-red-500' : ''} ${editClassName}`,
    };
    return multiline
      ? <textarea key={value} rows={2} {...editorProps} />
      : <input key={value} type="text" {...editorProps} />;
  }

  const valueToDisplay = displayValue || value;
  const hasValue = valueToDisplay.trim().length > 0;
  const isReadOnly = !onDoubleClick;
  const keyboardEditable = !isReadOnly && Boolean(ariaLabel);

  return (
    <div
      role={keyboardEditable ? 'button' : undefined}
      tabIndex={keyboardEditable ? 0 : undefined}
      aria-label={ariaLabel}
      onKeyDown={keyboardEditable ? event => {
        if ((event.key === 'Enter' || event.key === ' ') && !isImeCompositionKeyEvent(event)) {
          event.preventDefault();
          onDoubleClick?.();
        }
      } : undefined}
      onDoubleClick={onDoubleClick}
      onPointerUp={event => {
        if (onDoubleClick && tapToEdit && (event.pointerType === 'touch' || event.pointerType === 'pen')) {
          onDoubleClick();
        }
      }}
      className={`${isReadOnly ? '' : 'cursor-pointer'} ${className} ${!hasValue ? emptyClassName : ''}`}
      title={valueToDisplay}
    >
      {hasValue ? valueToDisplay : (emptyText || 'Add...')}
    </div>
  );
}
