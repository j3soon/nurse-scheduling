// A checkbox list that allows quick multi-selection by dragging the mouse.
import { useEffect, useRef } from 'react';

interface CheckboxItem {
  id: string;
  description?: string;
}

interface CheckboxListProps {
  items: CheckboxItem[];
  selectedIds: string[];
  onToggle: (id: string) => void;
  label: string;
}

export function CheckboxList({
  items,
  selectedIds,
  onToggle,
  label,
}: CheckboxListProps) {
  const mouseDownCheckboxIdRef = useRef('');
  const mouseEnteredCheckboxIdRef = useRef('');
  const isMultiSelectDragRef = useRef(false);

  const handleToggle = (id: string) => {
    onToggle(id);
  };

  const handleCheckboxMouseEnter = (id: string) => {
    mouseEnteredCheckboxIdRef.current = id;
    if (isMultiSelectDragRef.current) {
      handleToggle(id);
    }
  };

  const handleCheckboxMouseDown = (id: string) => {
    if (id === mouseEnteredCheckboxIdRef.current && !isMultiSelectDragRef.current) {
      mouseDownCheckboxIdRef.current = id;
      document.body.style.userSelect = 'none';
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

  const handleCheckboxMouseUp = (id: string) => {
    if (!isMultiSelectDragRef.current) {
      // Normal checkbox click behavior
      handleToggle(id);
    }
    // End multi-select drag
    isMultiSelectDragRef.current = false;
    mouseDownCheckboxIdRef.current = '';
    document.body.style.userSelect = '';
  };

  // Add event listener for mouse up outside the component
  useEffect(() => {
    const handleGlobalMouseUp = () => {
      // End multi-select drag
      isMultiSelectDragRef.current = false;
      mouseDownCheckboxIdRef.current = '';
      document.body.style.userSelect = '';
    };

    window.addEventListener('mouseup', handleGlobalMouseUp);
    // Cleanup event listener
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp);
      document.body.style.userSelect = '';
    };
  }, []);

  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-gray-700">{label}</h3>
      {/* Horizontal padding is used instead of margin to avoid gaps between checkboxes that could cause text selection when dragging */}
      <div className="flex flex-wrap">
        {items.map(item => (
          <label
            key={item.id}
            className="inline-flex items-center px-1 py-1"
            title={item.description}
            onMouseEnter={() => handleCheckboxMouseEnter(item.id)}
            onMouseDown={() => handleCheckboxMouseDown(item.id)}
            onMouseLeave={() => handleCheckboxMouseLeave()}
            onMouseUp={() => handleCheckboxMouseUp(item.id)}
          >
            <input
              type="checkbox"
              checked={selectedIds.includes(item.id)}
              onChange={() => {}} // Prevent default onChange to handle it in mouseUp
              className="form-checkbox h-4 w-4 text-blue-600"
            />
            <span className="ml-2 text-sm text-gray-700">{item.id}</span>
          </label>
        ))}
      </div>
    </div>
  );
}
