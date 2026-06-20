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

// A checkbox list that allows quick multi-selection by dragging the mouse.
// Important interaction contract:
// - A plain click behaves like a normal checkbox: it toggles on mouse up if the pointer never leaves the initial checkbox.
// - Once the pointer leaves the initial checkbox, the gesture becomes drag-selection mode.
// - Entering drag-selection mode immediately toggles the initial checkbox as the pointer leaves it.
// - In drag-selection mode, toggles happen on mouse enter; mouse up only ends the gesture.
// - Re-entering a checkbox during the same drag gesture toggles it again, so one checkbox may be toggled multiple times.
// - Mouse up anywhere, including outside this component, ends the current gesture via the global mouseup listener.
// - Native checkbox onChange is intentionally suppressed so all toggles follow the custom mouse gesture rules.
import { CSSProperties, useCallback, useEffect, useId, useRef } from 'react';

interface CheckboxItem {
  id: string;
  description?: string;
}

interface CheckboxListProps {
  items: CheckboxItem[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  label: string;
  inputType?: 'checkbox' | 'radio';
  inputName?: string;
  itemsClassName?: string;
  inputClassName?: string;
  textClassName?: string;
  getItemClassName?: (item: CheckboxItem, isSelected: boolean) => string;
  getItemStyle?: (item: CheckboxItem, index: number) => CSSProperties | undefined;
}

export function CheckboxList({
  items,
  selectedIds,
  onToggle,
  label,
  inputType = 'checkbox',
  inputName,
  itemsClassName = 'flex flex-wrap',
  inputClassName,
  textClassName = 'ml-2 text-sm text-gray-700',
  getItemClassName,
  getItemStyle,
}: CheckboxListProps) {
  const mouseDownCheckboxIdRef = useRef('');
  const mouseEnteredCheckboxIdRef = useRef('');
  const isMultiSelectDragRef = useRef(false);

  const setUserSelectDisabled = () => {
    document.body.style.setProperty('user-select', 'none');
  };

  const clearUserSelectDisabled = () => {
    document.body.style.removeProperty('user-select');
  };

  const handleToggle = (id: string) => {
    onToggle(id);
  };
  const resolvedInputClassName = inputClassName ?? `form-${inputType} h-4 w-4 text-blue-600`;
  const generatedInputName = useId();
  const radioInputName = inputType === 'radio'
    ? inputName ?? `checkbox-list-${generatedInputName}`
    : undefined;

  const resetDragState = useCallback(() => {
    isMultiSelectDragRef.current = false;
    mouseDownCheckboxIdRef.current = '';
    clearUserSelectDisabled();
  }, []);

  const handleCheckboxMouseEnter = (id: string) => {
    mouseEnteredCheckboxIdRef.current = id;
    if (isMultiSelectDragRef.current) {
      handleToggle(id);
    }
  };

  const handleCheckboxMouseDown = (id: string, event: React.MouseEvent) => {
    if (event.button !== 0) return;

    if (id === mouseEnteredCheckboxIdRef.current && !isMultiSelectDragRef.current) {
      mouseDownCheckboxIdRef.current = id;
      setUserSelectDisabled();
    }
  };

  const handleCheckboxMouseLeave = () => {
    if (mouseDownCheckboxIdRef.current && mouseEnteredCheckboxIdRef.current === mouseDownCheckboxIdRef.current) {
      // Start multi-select drag
      isMultiSelectDragRef.current = true;
      // Toggle the initial checkbox when leaving it
      handleToggle(mouseDownCheckboxIdRef.current);
      mouseDownCheckboxIdRef.current = '';
    }
    mouseEnteredCheckboxIdRef.current = '';
  };

  const handleCheckboxMouseUp = (id: string, event: React.MouseEvent) => {
    if (event.button !== 0) return;

    if (!isMultiSelectDragRef.current) {
      // Normal checkbox click behavior
      handleToggle(id);
    }
    resetDragState();
  };

  // Add event listener for mouse up outside the component
  useEffect(() => {
    const handleGlobalMouseUp = () => {
      resetDragState();
    };

    window.addEventListener('mouseup', handleGlobalMouseUp);
    // Cleanup event listener
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp);
      clearUserSelectDisabled();
    };
  }, [resetDragState]);

  return (
    <div className="space-y-2">
      {label && label !== '' && (
        <h3 className="text-sm font-medium text-gray-700">{label}</h3>
      )}
      {/* Horizontal padding is used instead of margin to avoid gaps between checkboxes that could cause text selection when dragging */}
      <div className={itemsClassName}>
        {items.map((item, index) => (
          <label
            key={item.id}
            className={`inline-flex items-center px-1 py-1 ${getItemClassName?.(item, selectedIds.includes(item.id)) ?? ''}`}
            style={getItemStyle?.(item, index)}
            title={item.description}
            onMouseEnter={inputType === 'checkbox' ? () => handleCheckboxMouseEnter(item.id) : undefined}
            onMouseDown={inputType === 'checkbox' ? (e) => handleCheckboxMouseDown(item.id, e) : undefined}
            onMouseLeave={inputType === 'checkbox' ? () => handleCheckboxMouseLeave() : undefined}
            onMouseUp={inputType === 'checkbox' ? (e) => handleCheckboxMouseUp(item.id, e) : undefined}
          >
            <input
              type={inputType}
              name={radioInputName}
              checked={selectedIds.includes(item.id)}
              onChange={inputType === 'radio' ? () => handleToggle(item.id) : () => {}} // Keep native checkbox changes disabled so gesture logic stays fully in mouse handlers.
              className={resolvedInputClassName}
            />
            <span className={textClassName}>{item.id}</span>
          </label>
        ))}
      </div>
    </div>
  );
}
