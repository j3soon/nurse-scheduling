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

'use client';

import { useState } from 'react';
import { FiLock, FiUnlock } from 'react-icons/fi';

interface BackendTokenFieldProps {
  endpoint: string;
  token: string | null;
  rememberToken: boolean;
  isEditing: boolean;
  disabled?: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: (token: string, rememberToken: boolean) => void;
  onClear: () => void;
}

interface BackendTokenEditorProps {
  endpoint: string;
  initialToken: string;
  rememberToken: boolean;
  disabled: boolean;
  onCancel: () => void;
  onSave: (token: string, rememberToken: boolean) => void;
}

const CONTROL_CLASSES = 'rounded border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400';

function BackendTokenEditor({
  endpoint,
  initialToken,
  rememberToken,
  disabled,
  onCancel,
  onSave,
}: BackendTokenEditorProps) {
  const [tokenDraft, setTokenDraft] = useState(initialToken);
  const [remember, setRemember] = useState(rememberToken);
  const trimmedToken = tokenDraft.trim();

  const submitToken = () => {
    if (trimmedToken) {
      onSave(trimmedToken, remember);
    }
  };

  return (
    <div className="mt-1 space-y-2">
      <input
        type="password"
        value={tokenDraft}
        autoComplete="off"
        autoFocus
        spellCheck={false}
        placeholder="Backend token"
        aria-label={`Token for ${endpoint}`}
        onChange={(event) => setTokenDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            submitToken();
          } else if (event.key === 'Escape') {
            event.preventDefault();
            onCancel();
          }
        }}
        className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-sm text-gray-900 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
      />
      <label className="flex items-center gap-2 text-xs text-gray-600">
        <input
          type="checkbox"
          checked={remember}
          onChange={(event) => setRemember(event.target.checked)}
          className="h-3.5 w-3.5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
        />
        Remember on this device (stored unencrypted)
      </label>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={submitToken}
          disabled={disabled || trimmedToken.length === 0}
          aria-label={`Save token for ${endpoint}`}
          className="rounded border border-blue-600 bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:border-gray-300 disabled:bg-gray-100 disabled:text-gray-400"
        >
          Save
        </button>
        <button
          type="button"
          onClick={onCancel}
          aria-label={`Cancel token for ${endpoint}`}
          className={CONTROL_CLASSES}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export default function BackendTokenField({
  endpoint,
  token,
  rememberToken,
  isEditing,
  disabled = false,
  onEdit,
  onCancel,
  onSave,
  onClear,
}: BackendTokenFieldProps) {
  // A remembered token is already readable in this browser, so editing prefills it for a
  // quick correction. A session-only token is not stored anywhere, so it starts blank.
  if (isEditing) {
    return (
      <BackendTokenEditor
        endpoint={endpoint}
        initialToken={rememberToken && token ? token : ''}
        rememberToken={rememberToken}
        disabled={disabled}
        onCancel={onCancel}
        onSave={onSave}
      />
    );
  }

  return (
    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
      <span className={`inline-flex items-center gap-1 ${token ? 'text-gray-600' : 'text-amber-700'}`}>
        {token ? <FiUnlock className="h-3 w-3" /> : <FiLock className="h-3 w-3" />}
        {token
          ? rememberToken ? 'Token saved on this device' : 'Token set for this session'
          : 'Token required'}
      </span>
      <button
        type="button"
        onClick={onEdit}
        disabled={disabled}
        aria-label={`${token ? 'Change' : 'Enter'} token for ${endpoint}`}
        className={CONTROL_CLASSES}
      >
        {token ? 'Change' : 'Enter token'}
      </button>
      {token && (
        <button
          type="button"
          onClick={onClear}
          disabled={disabled}
          aria-label={`Forget token for ${endpoint}`}
          className={CONTROL_CLASSES}
        >
          Forget
        </button>
      )}
    </div>
  );
}
