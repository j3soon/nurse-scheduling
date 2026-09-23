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

// The home page for Tab "0. Home"
'use client';

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { useRouter } from 'next/navigation';
import { FiChevronDown, FiCheck } from 'react-icons/fi';
import yaml from 'js-yaml';
import PageDocumentationLink from '@/components/PageDocumentationLink';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { DOCUMENTATION_URLS, STATIC_BUILD_URLS } from '@/constants/urls';
import {
  areBuildOriginsEquivalent,
  BuildEntry,
  CURRENT_APP_VERSION,
  fetchReleaseBranches,
  isStableReleaseVersion,
} from '@/utils/version';

export default function Home() {
  const router = useRouter();
  const { createNewState, loadFromYaml } = useSchedulingData();
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [newScheduleKind, setNewScheduleKind] = useState<'empty' | 'example'>('empty');
  const [isNewScheduleMenuOpen, setIsNewScheduleMenuOpen] = useState(false);
  const [isCreatingSchedule, setIsCreatingSchedule] = useState(false);
  const [newScheduleError, setNewScheduleError] = useState<string | null>(null);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const currentOrigin = useSyncExternalStore(
    () => () => {},
    () => window.location.origin,
    () => ''
  );
  const [releaseBranches, setReleaseBranches] = useState<BuildEntry[]>([]);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const newScheduleDropdownRef = useRef<HTMLDivElement>(null);

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
      if (newScheduleDropdownRef.current && !newScheduleDropdownRef.current.contains(event.target as Node)) {
        setIsNewScheduleMenuOpen(false);
      }
    };
    if (isDropdownOpen || isNewScheduleMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isDropdownOpen, isNewScheduleMenuOpen]);

  const buildUrls = useMemo(() => [...STATIC_BUILD_URLS, ...releaseBranches], [releaseBranches]);

  const currentBuild = useMemo<BuildEntry | null>(() => {
    if (!currentOrigin) return null;
    const found = buildUrls.find((build) => areBuildOriginsEquivalent(build.url, currentOrigin));
    if (found) return found;
    return { label: 'unknown', url: currentOrigin };
  }, [currentOrigin, buildUrls]);

  const handleBuildSelect = (url: string) => {
    setIsDropdownOpen(false);
    if (!areBuildOriginsEquivalent(url, currentOrigin)) {
      window.location.assign(url);
    }
  };

  const handleStartNew = (kind: 'empty' | 'example') => {
    setNewScheduleKind(kind);
    setNewScheduleError(null);
    setIsNewScheduleMenuOpen(false);
    setShowConfirmDialog(true);
  };

  const confirmStartNew = async () => {
    setIsCreatingSchedule(true);
    setNewScheduleError(null);
    try {
      if (newScheduleKind === 'empty') {
        createNewState();
      } else {
        const response = await fetch('/examples/large-ward-with-87-people-2025-11.yaml');
        if (!response.ok) throw new Error('The example schedule could not be loaded.');
        loadFromYaml(yaml.load(await response.text()));
      }
      setShowConfirmDialog(false);
    } catch (error) {
      setNewScheduleError(error instanceof Error ? error.message : 'The schedule could not be created.');
    } finally {
      setIsCreatingSchedule(false);
    }
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
        <div className="mb-8 flex items-center justify-center gap-3">
          <h1 className="text-4xl font-bold text-gray-800">Nurse Scheduling System</h1>
          <PageDocumentationLink href={DOCUMENTATION_URLS.home} label="Home" />
        </div>
        <p className="text-lg text-gray-600 mb-8">
          Welcome to the Nurse Scheduling System. Use the tabs above to navigate.
        </p>
        {!isStableReleaseVersion(CURRENT_APP_VERSION) && (
          <div className="mb-8 p-4 bg-blue-50 border border-blue-200 rounded-lg">
            <p className="text-sm text-blue-800">
              This is a development build. For best compatibility with saved YAML, use a versioned release.
            </p>
          </div>
        )}
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <div ref={newScheduleDropdownRef} className="relative inline-flex">
            <button
              onClick={() => handleStartNew('empty')}
              className="rounded-l-lg bg-blue-600 px-6 py-3 text-white transition-colors hover:bg-blue-700"
            >
              New Schedule
            </button>
            <button
              type="button"
              onClick={() => setIsNewScheduleMenuOpen(previous => !previous)}
              aria-label="Choose new schedule type"
              aria-expanded={isNewScheduleMenuOpen}
              className="rounded-r-lg border-l border-blue-500 bg-blue-600 px-3 py-3 text-white transition-colors hover:bg-blue-700"
            >
              <FiChevronDown className={`h-5 w-5 transition-transform ${isNewScheduleMenuOpen ? 'rotate-180' : ''}`} />
            </button>
            {isNewScheduleMenuOpen && (
              <div className="absolute left-0 top-full z-20 mt-2 w-64 overflow-hidden rounded-lg border border-gray-200 bg-white text-left shadow-lg">
                <button
                  type="button"
                  onClick={() => handleStartNew('empty')}
                  className="block w-full px-4 py-3 text-sm text-gray-700 hover:bg-gray-50"
                >
                  <span className="block font-medium">Empty schedule</span>
                  <span className="block text-xs text-gray-500">Start without people or shift types.</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleStartNew('example')}
                  className="block w-full border-t border-gray-100 px-4 py-3 text-sm text-gray-700 hover:bg-gray-50"
                >
                  <span className="block font-medium">87-person example</span>
                  <span className="block text-xs text-gray-500">Load the realistic November 2025 testcase.</span>
                </button>
              </div>
            )}
          </div>
          <button
            onClick={() => router.push('/dates')}
            className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
          >
            Continue
          </button>
        </div>
      </div>

      {/* Build Selector Dropdown */}
      <div ref={dropdownRef} className="fixed bottom-20 right-8 z-20">
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
              {newScheduleKind === 'empty'
                ? 'Start an empty schedule? This will reset all your current data.'
                : 'Load the 87-person example? This will reset all your current data.'}
            </p>
            {newScheduleError && <p className="mb-4 text-sm text-red-700" role="alert">{newScheduleError}</p>}
            <div className="flex justify-end gap-4">
              <button
                onClick={() => setShowConfirmDialog(false)}
                disabled={isCreatingSchedule}
                className="px-4 py-2 text-gray-600 hover:text-gray-800 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmStartNew}
                disabled={isCreatingSchedule}
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:cursor-wait disabled:opacity-50"
              >
                {isCreatingSchedule ? 'Loading…' : newScheduleKind === 'empty' ? 'Create empty schedule' : 'Load example'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
