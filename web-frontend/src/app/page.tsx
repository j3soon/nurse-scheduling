/*
 * This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
 *
 * Copyright (C) 2023-2025 Johnson Sun
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

// The home page for Tab "0. Home"
'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import { FiChevronDown, FiCheck } from 'react-icons/fi';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { STATIC_BUILD_URLS } from '@/constants/urls';
import { fetchReleaseBranches, BuildEntry } from '@/utils/version';

export default function Home() {
  const { createNewState } = useSchedulingData();
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [currentOrigin, setCurrentOrigin] = useState('');
  const [releaseBranches, setReleaseBranches] = useState<BuildEntry[]>([]);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setCurrentOrigin(window.location.origin);
  }, []);

  useEffect(() => {
    const loadReleaseBranches = async () => {
      const releases = await fetchReleaseBranches();
      setReleaseBranches(releases);
    };
    loadReleaseBranches();
  }, []);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    if (isDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isDropdownOpen]);

  const buildUrls = useMemo(() => [...STATIC_BUILD_URLS, ...releaseBranches], [releaseBranches]);

  const currentBuild = useMemo(() => {
    if (!currentOrigin) return null;
    const normalizedOrigin = currentOrigin.replace(/\/$/, '');
    const found = buildUrls.find(
      (build) => build.url.replace(/\/$/, '') === normalizedOrigin
    );
    if (found) return found;
    return { label: 'unknown', url: currentOrigin };
  }, [currentOrigin, buildUrls]);

  const handleBuildSelect = (url: string) => {
    setIsDropdownOpen(false);
    if (url !== currentOrigin && url !== currentOrigin + '/') {
      window.location.href = url;
    }
  };

  const handleStartNew = () => {
    setShowConfirmDialog(true);
  };

  const confirmStartNew = () => {
    createNewState();
    setShowConfirmDialog(false);
  };

  const getBuildLabelColor = (label: string) => {
    if (label === 'unknown') return 'text-orange-600';
    if (label === 'local') return 'text-yellow-600';
    if (label === 'dev') return 'text-blue-600';
    if (label === 'main') return 'text-green-600';
    if (label.startsWith('v')) return 'text-purple-600';
    return 'text-gray-400';
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center px-4 sm:px-6 lg:px-8">
      <div className="w-full max-w-3xl text-center">
        <h1 className="text-4xl font-bold mb-8 text-gray-800">
          Nurse Scheduling System
        </h1>
        <p className="text-lg text-gray-600 mb-4">
          Welcome to the Nurse Scheduling System. Use the tabs above to navigate.
        </p>
        <div className="mb-8 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
          <p className="text-sm text-yellow-800">
            ⚠️ This project is in active development. Breaking changes may occur without notice. Please proceed with caution.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <button
            onClick={handleStartNew}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            New Schedule
          </button>
          <button
            onClick={() => window.location.href = '/dates'}
            className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
          >
            Continue
          </button>
        </div>
      </div>

      {/* Build Selector Dropdown */}
      <div ref={dropdownRef} className="fixed bottom-4 right-4 z-20">
        <button
          onClick={() => setIsDropdownOpen(!isDropdownOpen)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-white border border-gray-200 rounded-full shadow-sm hover:shadow"
        >
          <span className="text-gray-400">Build:</span>
          <span className={`font-semibold ${getBuildLabelColor(currentBuild?.label || '')}`}>
            {currentBuild?.label || 'loading...'}
          </span>
          <FiChevronDown className={`w-3 h-3 transition-transform ${isDropdownOpen ? 'rotate-180' : ''}`} />
        </button>

        {isDropdownOpen && (
          <div className="absolute bottom-full mb-2 right-0 w-64 max-h-64 overflow-y-auto bg-white rounded-lg shadow-lg border border-gray-200">
            {buildUrls.map((build) => (
              <button
                key={build.label}
                onClick={() => handleBuildSelect(build.url)}
                className={`w-full px-3 py-2 text-sm flex items-center gap-2 hover:bg-gray-50 first:rounded-t-lg last:rounded-b-lg ${
                  currentBuild?.label === build.label ? 'bg-blue-50' : ''
                }`}
              >
                <span className={`font-medium w-14 text-left ${getBuildLabelColor(build.label)}`}>{build.label}</span>
                <span className="text-gray-400 text-xs truncate flex-1 text-left">{build.url}</span>
                {currentBuild?.label === build.label && <FiCheck className="w-4 h-4 text-blue-600" />}
              </button>
            ))}
            {currentBuild?.label === 'unknown' && (
              <div className="px-3 py-2 text-sm flex items-center gap-2 bg-orange-50 border-t border-gray-100 rounded-b-lg">
                <span className={`font-medium w-14 text-left ${getBuildLabelColor('unknown')}`}>unknown</span>
                <span className="text-gray-400 text-xs truncate flex-1 text-left">{currentOrigin}</span>
                <FiCheck className="w-4 h-4 text-orange-600" />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg p-6 max-w-md w-full">
            <h2 className="text-xl font-bold mb-4 text-gray-800">Confirm Reset</h2>
            <p className="text-gray-600 mb-6">
              Are you sure you want to start from a new state? This will reset all your current data.
            </p>
            <div className="flex justify-end gap-4">
              <button
                onClick={() => setShowConfirmDialog(false)}
                className="px-4 py-2 text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={confirmStartNew}
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
              >
                Reset Data
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
