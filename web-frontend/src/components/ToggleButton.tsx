import { FiPlus, FiMinus } from 'react-icons/fi';

interface ToggleButtonProps {
  label: string;
  isToggled: boolean;
  onToggle: () => void;
}

export default function ToggleButton({ 
  label, 
  isToggled, 
  onToggle: onClick, 
}: ToggleButtonProps) {
  return (
    <button
      onClick={onClick}
      className="text-blue-600 hover:text-blue-900 flex items-center gap-1"
    >
      {isToggled ? (
        <FiMinus className="h-4 w-4" />
      ) : (
        <FiPlus className="h-4 w-4" />
      )}
      {label}
    </button>
  );
} 