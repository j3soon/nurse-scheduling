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

// The Save and Load page for Tab "10. Save and Load"
'use client';

import { translator, type Translator } from '@/i18n/messages';
import { useI18n } from '@/i18n/I18nProvider';
import { useState, useRef, useEffect } from 'react';
import { FiDownload, FiSave, FiX, FiCopy, FiCheck, FiAlertCircle, FiUpload } from 'react-icons/fi';
import yaml from 'js-yaml';
import { useScheduleSpec } from '@/hooks/useScheduleSpec';
import ToggleButton from '@/components/ToggleButton';
import UploadButton from '@/components/UploadButton';
import PageDocumentationLink from '@/components/PageDocumentationLink';
import StarRepoNudge from '@/components/StarRepoNudge';
import { DOCUMENTATION_URLS } from '@/constants/urls';
import { CURRENT_APP_VERSION } from '@/utils/version';
import { generateYamlFromState } from '@/utils/yamlGenerator';
import { anonymizeScheduleSpecState } from '@/utils/anonymizeScheduleSpecState';
import { getMissingPreferredScatterDateGroups, randomizeConcreteDateShiftRequests } from '@/utils/randomizeShiftRequests';
import { useTabSwitchWarning } from '@/utils/unsavedEditingState';

const API_VERSION_KEY = 'apiVersion';
const BOM_MOJIBAKE_API_VERSION_PREFIXES = [
  'ï»¿apiVersion',
  '嚜瘸piVersion',
  '锘縜piVersion',
];

interface YamlImportSummary {
  filename: string;
  versionWarning: string | null;
  counts: { dates: number; people: number; shiftTypes: number; preferences: number };
  warnings: string[];
}

function formatCount(count: number, singular: string, plural = `${singular}s`, t: Translator = translator('en')): string {
  return `${count.toLocaleString()} ${t(count === 1 ? singular : plural)}`;
}

function summarizeYamlImport(data: unknown, filename: string, versionWarning: string | null, t: Translator = translator('en')): YamlImportSummary {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error(t("The YAML must contain a Schedule Spec object."));
  }
  const spec = data as Record<string, unknown>;
  for (const key of ['dates', 'people', 'shiftTypes']) {
    const section = spec[key];
    if (section !== undefined && (!section || typeof section !== 'object' || Array.isArray(section))) {
      throw new Error(t("The {value0} section must be an object.", { value0: key }));
    }
  }
  if (spec.preferences !== undefined && !Array.isArray(spec.preferences)) {
    throw new Error(t("The preferences section must be a list."));
  }
  const itemCount = (section: unknown): number => {
    if (!section || typeof section !== 'object' || Array.isArray(section)) return 0;
    const items = (section as Record<string, unknown>).items;
    return Array.isArray(items) ? items.length : 0;
  };
  const dateCount = (): number => {
    const explicitCount = itemCount(spec.dates);
    if (explicitCount > 0) return explicitCount;
    if (!spec.dates || typeof spec.dates !== 'object' || Array.isArray(spec.dates)) return 0;
    const range = (spec.dates as Record<string, unknown>).range;
    if (!range || typeof range !== 'object' || Array.isArray(range)) return 0;
    const { startDate, endDate } = range as Record<string, unknown>;
    const timestamp = (value: unknown): number => value instanceof Date
      ? value.getTime()
      : typeof value === 'string' ? Date.parse(value) : NaN;
    const start = timestamp(startDate);
    const end = timestamp(endDate);
    return Number.isFinite(start) && Number.isFinite(end) && end >= start
      ? Math.floor((end - start) / 86_400_000) + 1
      : 0;
  };
  const counts = {
    dates: dateCount(),
    people: itemCount(spec.people),
    shiftTypes: itemCount(spec.shiftTypes),
    preferences: Array.isArray(spec.preferences) ? spec.preferences.length : 0,
  };
  const missingSections = (['dates', 'people', 'shiftTypes', 'preferences'] as const)
    .filter(key => !spec[key])
    .map(key => key === 'shiftTypes' ? t("shift types") : key);
  const warnings = missingSections.length > 0
    ? [t("Missing sections: {value0}.", { value0: missingSections.join(', ') })]
    : [];
  return { filename, versionWarning, counts, warnings };
}

function recoverYamlTextPrefixWithConfirmation(content: string, t: Translator = translator('en')): string | null {
  // Mojibake prefixes mean the original UTF-8 BOM bytes were decoded using
  // another encoding before this app received the YAML text. Real UTF-8 BOM
  // input is handled by FileReader/js-yaml and does not need repair here:
  // - ï»¿apiVersion: UTF-8 BOM decoded as Latin-1/Windows-1252.
  // - 嚜瘸piVersion: UTF-8 BOM plus the "a" from apiVersion decoded as Big5/CP950.
  // - 锘縜piVersion: UTF-8 BOM plus the "a" from apiVersion decoded as GBK/GB18030.
  const corruptedPrefix = BOM_MOJIBAKE_API_VERSION_PREFIXES.find(prefix => content.startsWith(prefix));
  if (!corruptedPrefix) {
    return content;
  }

  const proceed = confirm(
    t("Corrupted YAML header detected.\n\nThe file starts with \"{value0}\" instead of \"{value1}\". This can happen when a UTF-8 BOM YAML file is decoded with the wrong text encoding before being saved or uploaded.\n\nDo you want to automatically recover this header before loading the file?", { value0: corruptedPrefix, value1: API_VERSION_KEY })
  );
  if (!proceed) {
    return null;
  }

  return API_VERSION_KEY + content.slice(corruptedPrefix.length);
}

export default function SaveAndLoadPage() {
  const { t } = useI18n();
  const {
    dateData,
    loadFromYaml,
    savedState: filteredState,
  } = useScheduleSpec();

  const [isEditing, setIsEditing] = useState(false);
  const [editedYaml, setEditedYaml] = useState('');
  const [yamlError, setYamlError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [anonymizePeopleItems, setAnonymizePeopleItems] = useState(true);
  const [anonymizePeopleGroups, setAnonymizePeopleGroups] = useState(false);
  const [scatterShiftRequests, setScatterShiftRequests] = useState(false);
  const [notice, setNotice] = useState<YamlImportSummary | 'download' | null>(null);
  const importSummary = notice === 'download' ? null : notice;
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const copiedResetTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (copiedResetTimeoutRef.current) {
        clearTimeout(copiedResetTimeoutRef.current);
      }
    };
  }, []);
  useTabSwitchWarning(isEditing);

  // Convert current state to YAML with custom flow style for leaf arrays
  const currentYaml = generateYamlFromState(filteredState);
  const missingPreferredScatterDateGroups = getMissingPreferredScatterDateGroups(dateData.groups);

  const downloadYaml = (yamlContent: string, filenameSuffix = '') => {
    const blob = new Blob([yamlContent], { type: 'application/x-yaml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `nurse-scheduling${filenameSuffix}-${new Date().toISOString().split('T')[0]}.yaml`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setNotice('download');
  };

  const handleDownload = () => {
    downloadYaml(currentYaml);
  };

  const handleDownloadAnonymized = () => {
    try {
      const exportState = scatterShiftRequests
        ? randomizeConcreteDateShiftRequests(filteredState, dateData.items, dateData.groups)
        : filteredState;
      const anonymizedState = anonymizeScheduleSpecState(exportState, {
        anonymizePeopleItems,
        anonymizePeopleGroups
      });
      downloadYaml(generateYamlFromState(anonymizedState), '-anonymized');
    } catch (error) {
      alert(t("Unable to randomize shift requests: {value0}", { value0: error instanceof Error ? error.message : 'Unknown error' }));
    }
  };

  const handleCopyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(currentYaml);
      setCopied(true);
      if (copiedResetTimeoutRef.current) {
        clearTimeout(copiedResetTimeoutRef.current);
      }
      copiedResetTimeoutRef.current = setTimeout(() => {
        setCopied(false);
        copiedResetTimeoutRef.current = null;
      }, 2000);
    } catch (err) {
      console.error('Failed to copy to clipboard:', err);
    }
  };

  const handleStartEdit = () => {
    setEditedYaml(currentYaml);
    setIsEditing(true);
    setYamlError(null);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditedYaml('');
    setYamlError(null);
  };

  // Helper function to check app version mismatch and get warning message
  const getVersionWarning = (parsedData: unknown, compact = false): string | null => {
    const data = parsedData as { appVersion?: string };
    const fileVersion = data?.appVersion;

    if (!fileVersion) {
      if (compact) return t("App version missing (current {value0}).", { value0: CURRENT_APP_VERSION });
      return t("The loaded file does not contain app version information. It may have been created with an older version of the application. Current app version: {value0}", { value0: CURRENT_APP_VERSION });
    }

    if (fileVersion.endsWith('-dirty')) {
      if (compact) return t("Dirty app version detected ({value0}).", { value0: fileVersion });
      return t("Dirty app version detected.\n\nFile app version: {value0}\nCurrent app version: {value1}\n\nThis YAML was created by a development build with uncommitted changes. It may not match a reproducible application version. If nothing breaks, you can continue.", { value0: fileVersion, value1: CURRENT_APP_VERSION });
    }

    if (fileVersion !== CURRENT_APP_VERSION) {
      if (compact) return t("App version mismatch detected (file {value0}, current {value1}).", { value0: fileVersion, value1: CURRENT_APP_VERSION });
      return t("App version mismatch detected.\n\nFile app version: {value0}\nCurrent app version: {value1}\n\nOlder YAML may not work after breaking changes, though we try to preserve compatibility. If nothing breaks, you can continue.", { value0: fileVersion, value1: CURRENT_APP_VERSION });
    }

    return null;
  };

  const handleSaveEdit = () => {
    try {
      const recoveredYaml = recoverYamlTextPrefixWithConfirmation(editedYaml, t);
      if (recoveredYaml === null) {
        return;
      }

      // Validate YAML by parsing it
      const parsedData = yaml.load(recoveredYaml);

      // Check for version mismatch and warn user
      const versionWarning = getVersionWarning(parsedData);
      if (versionWarning) {
        const proceed = confirm(t("{value0}\n\nDo you want to continue applying the changes?", { value0: versionWarning }));
        if (!proceed) {
          return;
        }
      }

      // Load the parsed data directly without validation, this willl create a new history state
      loadFromYaml(parsedData);
      setNotice(null);

      // Close the editor
      setIsEditing(false);
      setEditedYaml('');
      setYamlError(null);
    } catch (error) {
      setYamlError(error instanceof Error ? error.message : t("Invalid YAML format"));
    }
  };

  const processYamlFile = (file: File) => {
    setNotice(null);
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      if (!content) {
        alert(t("No content found in the uploaded file."));
        return;
      }

      try {
        const recoveredYaml = recoverYamlTextPrefixWithConfirmation(content, t);
        if (recoveredYaml === null) {
          return;
        }

        // Validate YAML by parsing it
        const parsedData = yaml.load(recoveredYaml);

        const summary = summarizeYamlImport(parsedData, file.name, getVersionWarning(parsedData, true), t);
        const versionWarning = getVersionWarning(parsedData);
        if (versionWarning && !confirm(t("{value0}\n\nDo you want to continue replacing the current Schedule Spec?", { value0: versionWarning }))) {
          return;
        }
        loadFromYaml(parsedData);
        setNotice(summary);
      } catch (error) {
        alert(t("Error loading YAML file: {value0}", { value0: error instanceof Error ? error.message : 'Invalid YAML format' }));
        console.error('Error processing YAML file:', error);
      }
    };

    reader.readAsText(file, 'utf-8');
  };

  return (
    <div
      className="container mx-auto px-4 py-8"
      onClickCapture={(event) => {
        if (event.target instanceof Element && event.target.closest('button')) {
          setNotice(null);
        }
      }}
    >
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6 gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-800">{t("Save and Load")}</h1>
          <PageDocumentationLink href={DOCUMENTATION_URLS.saveAndLoad} label={t("Save and Load")} />
        </div>
        <div className="flex flex-wrap gap-3 sm:gap-4">
          <button
            onClick={handleDownload}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500"
          >
            <FiDownload className="h-4 w-4" />
            {t("Download")}</button>
          <UploadButton
            onFileUpload={processYamlFile}
            acceptedFileTypes={['.yaml', '.yml']}
            buttonText={t("Upload")}
            tooltipText={t("Upload Schedule Spec YAML. Click to select a file or drag and drop it here.")}
            className="bg-green-600 text-white hover:bg-green-700 focus:ring-green-500"
            icon={<FiUpload className="h-4 w-4" />}
          />
          <button
            onClick={handleCopyToClipboard}
            className={`flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 ${
              copied
                ? 'bg-indigo-700 text-white focus:ring-indigo-500'
                : 'bg-indigo-600 text-white hover:bg-indigo-700 focus:ring-indigo-500'
            }`}
          >
            {copied ? <FiCheck className="h-4 w-4" /> : <FiCopy className="h-4 w-4" />}
            {copied ? t("Copied!") : t("Copy")}
          </button>
          <ToggleButton
            label={t("Edit YAML")}
            isToggled={isEditing}
            onToggle={() => {
              if (isEditing) {
                handleCancelEdit();
              } else {
                handleStartEdit();
              }
            }}
          />
        </div>
      </div>

      {notice === 'download' && <div className="mb-6"><StarRepoNudge /></div>}

      {importSummary && (
        <section role="status" aria-label={t("YAML import summary")} className="mb-6 rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm">
          <p className="text-green-900">
            <strong>{t("Schedule Spec uploaded:")}</strong> {importSummary.filename}.{' '}
            {formatCount(importSummary.counts.dates, 'date', 'dates', t)},{' '}
            {formatCount(importSummary.counts.people, 'person', 'people', t)},{' '}
            {formatCount(importSummary.counts.shiftTypes, 'shift type', 'shift types', t)},{' '}
            {formatCount(importSummary.counts.preferences, 'preference', 'preferences', t)}.{' '}
            {t("Use Undo in the tab bar or Ctrl+Z (Cmd+Z) to undo.")}</p>
          {(importSummary.versionWarning || importSummary.warnings.length > 0) && (
            <p className="mt-1 text-amber-800">
              <strong>{t("Warning:")}</strong> {[importSummary.versionWarning, ...importSummary.warnings].filter(Boolean).join(' ')}
            </p>
          )}
        </section>
      )}

      {/* Warning Section */}
      <div className="mb-6 bg-amber-50 border border-amber-200 rounded-lg p-4">
        <h3 className="text-lg font-medium text-amber-800 mb-3 flex items-center gap-2">
          <FiAlertCircle className="h-5 w-5" />
          {t("Warning")}</h3>
        <div className="space-y-2 text-sm text-amber-700">
          <p>
            {t("Please note that the ")}<strong>{t("Edit YAML")}</strong>{t(" feature only supports YAML files generated by this web UI version. Manual YAML editing is not recommended unless you are 100% confident in what you are doing. The web UI expects a specific YAML structure that differs from the more flexible format accepted by the CLI. During import, the app may break if the YAML is not in the expected format.")}</p>
        </div>
      </div>

      <details className="mb-6 bg-gray-50 border border-gray-200 rounded-lg p-4">
        <summary className="cursor-pointer text-lg font-medium text-gray-800">
          {t("Anonymize YAML")}</summary>
        <div className="mt-4 space-y-3">
          <p className="text-sm text-gray-600">
            {t("Download a temporary YAML snapshot with selected people identifiers replaced. Your current Schedule Spec is not modified. Free-text descriptions are not changed.")}</p>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={anonymizePeopleItems}
                onChange={(e) => setAnonymizePeopleItems(e.target.checked)}
                className="h-4 w-4"
              />
              {t("Replace people item IDs")}</label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={anonymizePeopleGroups}
                onChange={(e) => setAnonymizePeopleGroups(e.target.checked)}
                className="h-4 w-4"
              />
              {t("Replace people group IDs")}</label>
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={scatterShiftRequests}
                onChange={(e) => setScatterShiftRequests(e.target.checked)}
                className="h-4 w-4"
              />
              {t("Scatter shift requests (developer only)")}</label>
          </div>
          <button
            onClick={handleDownloadAnonymized}
            disabled={!anonymizePeopleItems && !anonymizePeopleGroups && !scatterShiftRequests}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 bg-gray-700 text-white hover:bg-gray-800 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <FiDownload className="h-4 w-4" />
            {t("Download Anonymized")}</button>
          <p className="text-sm text-gray-600">
            {t("Developer only: scattering preserves preferred WORKDAY/FREEDAY counts and consecutive runs. Date-group requests are unchanged.")}</p>
          {scatterShiftRequests && missingPreferredScatterDateGroups.length > 0 && (
            <p className="text-sm text-amber-700">
              {t("Warning: ")}{missingPreferredScatterDateGroups.join(t(" and "))} {missingPreferredScatterDateGroups.length === 1 ? t("group is") : t("groups are")}{t(" missing. Scattering will fall back to WEEKDAY and WEEKEND groups.")}</p>
          )}
        </div>
      </details>

      {/* YAML Display/Editor */}
      <div className="bg-white shadow-md rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
          <h3 className="text-lg font-semibold text-gray-800">
            {isEditing ? t("Edit Schedule Spec YAML") : t("Current Schedule Spec YAML")}
          </h3>
          {isEditing && (
            <div className="flex gap-2">
              <button
                onClick={handleCancelEdit}
                className="px-3 py-1 text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors flex items-center gap-1 text-sm"
              >
                <FiX className="h-4 w-4" />
                {t("Cancel")}</button>
              <button
                onClick={handleSaveEdit}
                className="px-3 py-1 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors flex items-center gap-1 text-sm"
              >
                <FiSave className="h-4 w-4" />
                {t("Save")}</button>
            </div>
          )}
        </div>

        <div className="relative">
          {isEditing ? (
            <div>
              <textarea
                ref={textareaRef}
                value={editedYaml}
                onChange={(e) => {
                  setEditedYaml(e.target.value);
                  setYamlError(null);
                }}
                className="w-full h-96 p-4 font-mono text-sm border-none resize-none focus:outline-none focus:ring-0"
                style={{ fontFamily: 'ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,Liberation Mono,monospace' }}
                placeholder={t("Enter Schedule Spec YAML...")}
              />
              {yamlError && (
                <div className="px-4 py-2 bg-red-50 border-t border-red-200 text-red-700 text-sm">
                  <p className="text-sm text-red-600 flex items-center gap-1">
                    <FiAlertCircle className="h-4 w-4" />
                    {yamlError}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <pre
              className="w-full h-96 p-4 font-mono text-sm overflow-auto bg-gray-50 whitespace-pre-wrap"
              style={{ fontFamily: 'ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,Liberation Mono,monospace' }}
            >
              {currentYaml}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
