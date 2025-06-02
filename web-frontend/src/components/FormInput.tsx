// A form input component for adding and editing item values and descriptions.
import { FiAlertCircle } from 'react-icons/fi';

interface FormInputProps {
  itemValue: string;
  itemPlaceholder?: string;
  onItemChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  descriptionValue: string;
  descriptionPlaceholder?: string;
  onDescriptionChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  error?: string;
  onAction: () => void;
  onCancel: () => void;
  actionText: string;
  children?: React.ReactNode;
}

export function FormInput({
  itemValue,
  itemPlaceholder,
  onItemChange,
  descriptionValue,
  descriptionPlaceholder,
  onDescriptionChange,
  onKeyDown,
  error,
  onAction,
  onCancel,
  actionText,
  children
}: FormInputProps) {
  return (
    <div className="space-y-4">
      <div>
        <input
          type="text"
          value={itemValue}
          onChange={onItemChange}
          onKeyDown={onKeyDown}
          autoFocus
          placeholder={itemPlaceholder}
          className={`block w-full px-4 py-2 text-sm text-gray-900 bg-white border rounded-lg shadow-sm transition-colors duration-200 ease-in-out
            ${error
              ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
              : 'border-gray-300 focus:border-blue-500 focus:ring-blue-200'
            }
            placeholder-gray-400
            focus:outline-none focus:ring-2
            hover:border-gray-400`}
        />
        {error && (
          <p className="mt-2 text-sm text-red-600 flex items-center gap-1">
            <FiAlertCircle className="h-4 w-4" />
            {error}
          </p>
        )}
      </div>
      <div>
        <input
          type="text"
          value={descriptionValue}
          placeholder={descriptionPlaceholder}
          onChange={onDescriptionChange}
          className="block w-full px-4 py-2 text-sm text-gray-900 bg-white border border-gray-300 rounded-lg shadow-sm transition-colors duration-200 ease-in-out
            focus:border-blue-500 focus:ring-blue-200 placeholder-gray-400 focus:outline-none focus:ring-2 hover:border-gray-400"
        />
      </div>
      {children}
      <div className="flex justify-end gap-3 pt-4">
        <button
          onClick={onCancel}
          className="px-4 py-2 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={onAction}
          className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
        >
          {actionText}
        </button>
      </div>
    </div>
  );
}
