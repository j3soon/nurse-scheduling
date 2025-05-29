import { FiAlertCircle, FiPlus, FiX } from 'react-icons/fi';

interface FormInputProps {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLInputElement>) => void;
  error?: string;
  placeholder?: string;
  onPrimary: () => void;
  onCancel: () => void;
  primaryText: string;
  children?: React.ReactNode;
}

export function FormInput({
  value,
  onChange,
  onKeyDown,
  error,
  placeholder,
  onPrimary,
  onCancel,
  primaryText,
  children
}: FormInputProps) {
  return (
    <div className="space-y-4">
      <div>
        <input
          type="text"
          value={value}
          onChange={onChange}
          onKeyDown={onKeyDown}
          autoFocus
          placeholder={placeholder}
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
      {children}
      <div className="flex space-x-2">
        <button
          onClick={onPrimary}
          className="text-sm text-blue-600 hover:text-blue-900 flex items-center gap-1"
        >
          <FiPlus className="h-4 w-4" />
          {primaryText}
        </button>
        <button
          onClick={onCancel}
          className="text-sm text-gray-600 hover:text-gray-900 flex items-center gap-1"
        >
          <FiX className="h-4 w-4" />
          Cancel
        </button>
      </div>
    </div>
  );
}
