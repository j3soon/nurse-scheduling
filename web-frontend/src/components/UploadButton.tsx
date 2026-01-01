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

import { useState, useRef } from 'react';
import { FiUpload } from 'react-icons/fi';

interface UploadButtonProps {
  onFileUpload: (file: File) => void;
  acceptedFileTypes: string[];
  buttonText: string;
  tooltipText: string;
  className?: string;
  disabled?: boolean;
  icon?: React.ReactNode;
}

export default function UploadButton({
  onFileUpload,
  acceptedFileTypes,
  buttonText,
  tooltipText,
  className = '',
  disabled = false,
  icon = <FiUpload className="h-4 w-4" />
}: UploadButtonProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): boolean => {
    const fileExtension = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!acceptedFileTypes.includes(fileExtension)) {
      alert(`Please upload a file with one of these extensions: ${acceptedFileTypes.join(', ')}`);
      return false;
    }
    return true;
  };

  const handleFileSelection = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (validateFile(file)) {
      onFileUpload(file);
    }

    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    if (!disabled) {
      setIsDragOver(true);
    }
  };

  const handleDragLeave = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragOver(false);

    if (disabled) return;

    const files = Array.from(event.dataTransfer.files);
    const file = files[0];

    if (!file) {
      alert('No file was dropped.');
      return;
    }

    if (validateFile(file)) {
      onFileUpload(file);
    }
  };

  const baseClassName = "flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2";

  const getButtonClassName = () => {
    if (disabled) {
      return `${baseClassName} bg-gray-400 text-gray-200 cursor-not-allowed focus:ring-gray-500`;
    }

    if (isDragOver) {
      // If custom className is provided, use it but override with drag-over styles
      if (className.trim()) {
        return `${baseClassName} border-2 border-blue-300 border-dashed ${className.replace('hover:', '').replace('focus:', '')}`;
      }
      return `${baseClassName} bg-blue-700 text-white border-2 border-blue-300 border-dashed focus:ring-blue-500`;
    }

    // If custom className is provided, use it instead of default blue styling
    if (className.trim()) {
      return `${baseClassName} ${className}`;
    }

    return `${baseClassName} bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500`;
  };

  return (
    <div className="relative">
      <input
        ref={fileInputRef}
        type="file"
        accept={acceptedFileTypes.join(',')}
        onChange={handleFileSelection}
        className="hidden"
        disabled={disabled}
      />
      <button
        onClick={() => fileInputRef.current?.click()}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={getButtonClassName()}
        title={tooltipText}
        disabled={disabled}
      >
        {icon}
        {buttonText}
      </button>
    </div>
  );
}
