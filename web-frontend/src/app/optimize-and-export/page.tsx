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

// The Optimize and Export page for Tab "11. Optimize and Export"
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { FiDownload, FiAlertCircle, FiCheckCircle, FiLoader, FiRefreshCw, FiWifi, FiWifiOff, FiActivity } from 'react-icons/fi';
import OptimizationProgressChart, { OptimizationProgressPoint } from '@/components/OptimizationProgressChart';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { generateYamlFromState } from '@/utils/yamlGenerator';
import { CURRENT_APP_VERSION } from '@/utils/version';

type ServerHealthStatus = 'checking' | 'online' | 'offline';

interface ServerHealthResponse {
  status: string;
  version: string;
  apiVersion?: string;
  appVersion: string;
}

interface OptimizeJobResponse {
  jobId: string;
  status: string;
  score: number | null;
  solverStatus: string | null;
  error: string | null;
  cancelRequested?: boolean;
  finishNowRequested?: boolean;
  xlsxReady: boolean;
  links: {
    status: string;
    events: string;
    xlsx: string;
  };
}

interface SseEventLogEntry {
  type: string;
  data: unknown;
  receivedAt: Date;
}

interface OptimizeProgressEvent {
  source?: string;
  currentBestScore?: number;
  elapsedSeconds?: number;
  solutionIndex?: number | null;
  commentCount?: number | null;
}

interface OptimizePhaseEvent {
  message?: string;
}

const TERMINAL_JOB_STATUSES = new Set(['optimal', 'feasible', 'infeasible', 'cancelled', 'failed']);

function normalizeEndpoint(endpoint: string): string {
  return endpoint.trim().replace(/\/+$/, '');
}

function buildApiUrl(endpoint: string, path: string): string {
  if (path.startsWith('http://') || path.startsWith('https://')) {
    return path;
  }
  return `${normalizeEndpoint(endpoint)}${path.startsWith('/') ? path : `/${path}`}`;
}

function getFilenameFromContentDisposition(contentDisposition: string | null): string {
  if (!contentDisposition) {
    return 'output.xlsx';
  }

  const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
  return filenameMatch ? filenameMatch[1] : 'output.xlsx';
}

function downloadFileFromUrl(url: string, filename: string): void {
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

async function getErrorDetail(response: Response): Promise<string> {
  const errorText = await response.text();
  try {
    const errorJson = JSON.parse(errorText);
    if (typeof errorJson.detail === 'string') {
      return errorJson.detail;
    }
    if (errorJson.detail !== undefined) {
      return JSON.stringify(errorJson.detail);
    }
  } catch {
    return errorText;
  }
  return errorText;
}

function formatCheckedTime(date: Date | null): string {
  if (!date) {
    return 'Never';
  }
  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function parseSseEventData(event: MessageEvent): unknown {
  if (!event.data) {
    return null;
  }

  try {
    return JSON.parse(event.data);
  } catch {
    return event.data;
  }
}

function formatSseEventData(data: unknown): string {
  if (typeof data === 'string') {
    return data;
  }
  return JSON.stringify(data);
}

function isProgressEventData(data: unknown): data is OptimizeProgressEvent {
  return typeof data === 'object' && data !== null && 'currentBestScore' in data;
}

function isPhaseEventData(data: unknown): data is OptimizePhaseEvent {
  return typeof data === 'object' && data !== null && 'message' in data;
}

function formatScore(score: number): string {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
  }).format(score);
}

function formatElapsedSeconds(value: number): string {
  if (value < 60) {
    return `${Math.round(value)}s`;
  }
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return `${minutes}m ${seconds.toString().padStart(2, '0')}s`;
}

function formatProgressSummary(data: OptimizeProgressEvent): string {
  const parts = [`Score: ${typeof data.currentBestScore === 'number' ? formatScore(data.currentBestScore) : 'N/A'}`];
  if (data.commentCount !== undefined && data.commentCount !== null) {
    parts.push(`Comments: ${data.commentCount}`);
  }
  if (data.elapsedSeconds !== undefined) {
    parts.push(`Elapsed: ${data.elapsedSeconds}s`);
  }
  if (data.solutionIndex !== undefined && data.solutionIndex !== null) {
    parts.push(`Solution: #${data.solutionIndex}`);
  }
  if (data.source) {
    parts.push(`Source: ${data.source}`);
  }
  return parts.join(' · ');
}

function getEventBadgeClasses(type: string): string {
  if (type === 'complete') {
    return 'bg-green-50 text-green-700 ring-green-200';
  }
  if (type === 'error') {
    return 'bg-red-50 text-red-700 ring-red-200';
  }
  if (type === 'progress') {
    return 'bg-blue-50 text-blue-700 ring-blue-200';
  }
  if (type === 'phase') {
    return 'bg-amber-50 text-amber-700 ring-amber-200';
  }
  return 'bg-gray-100 text-gray-700 ring-gray-200';
}

export default function OptimizeAndExportPage() {
  const {
    apiVersionData,
    descriptionData,
    dateData,
    peopleData,
    shiftTypeData,
    preferences,
    effectiveExportData,
    filterAutoGeneratedState
  } = useSchedulingData();

  const [apiEndpoint, setApiEndpoint] = useState(process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000');
  const [prettifyArg, setPrettifyArg] = useState(true);
  const [timeoutArg, setTimeoutArg] = useState<number>(300);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [scheduleScore, setScheduleScore] = useState<number | null>(null);
  const [scheduleStatus, setScheduleStatus] = useState<string | null>(null);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [currentJob, setCurrentJob] = useState<OptimizeJobResponse | null>(null);
  const [incumbentResult, setIncumbentResult] = useState<OptimizeProgressEvent | null>(null);
  const [progressPoints, setProgressPoints] = useState<OptimizationProgressPoint[]>([]);
  const [savedDownload, setSavedDownload] = useState<{ url: string; filename: string } | null>(null);
  const [sseEvents, setSseEvents] = useState<SseEventLogEntry[]>([]);
  const [serverHealthStatus, setServerHealthStatus] = useState<ServerHealthStatus>('checking');
  const [lastHealthCheckedAt, setLastHealthCheckedAt] = useState<Date | null>(null);
  const [serverHealth, setServerHealth] = useState<ServerHealthResponse | null>(null);
  const eventLogRef = useRef<HTMLDivElement | null>(null);
  const savedDownloadUrlRef = useRef<string | null>(null);
  const shouldScrollEventLogToBottomRef = useRef(true);
  const hasVersionMismatch = Boolean(serverHealth && serverHealth.appVersion !== CURRENT_APP_VERSION);
  const isDateDataMissing = !dateData.range?.startDate || !dateData.range?.endDate || dateData.items.length === 0;
  const isPeopleDataMissing = peopleData.items.length === 0;
  const isShiftTypeDataMissing = shiftTypeData.items.length === 0 && shiftTypeData.groups.length === 0;
  const isRequiredDataMissing = isDateDataMissing || isPeopleDataMissing || isShiftTypeDataMissing;
  const isJobActive = Boolean(
    currentJobId &&
    isLoading &&
    scheduleStatus &&
    !TERMINAL_JOB_STATUSES.has(scheduleStatus.toLowerCase())
  );
  const isCancelling = scheduleStatus === 'cancelling';
  const isOptimizeDisabled = isLoading || isRequiredDataMissing || serverHealthStatus === 'offline';
  const optimizeDisabledReason = isRequiredDataMissing
    ? 'Complete the missing schedule configuration before optimizing.'
    : serverHealthStatus === 'offline'
      ? 'Backend unavailable. Check the endpoint or start the backend.'
      : null;

  // Create the current state object for YAML export (filtering out autogenerated items)
  const filteredState = filterAutoGeneratedState({
    apiVersion: apiVersionData,
    description: descriptionData,
    dates: dateData,
    people: peopleData,
    shiftTypes: shiftTypeData,
    preferences,
    export: effectiveExportData
  });

  // Convert current state to YAML
  const currentYaml = generateYamlFromState(filteredState);

  const clearSavedDownload = useCallback(() => {
    if (savedDownloadUrlRef.current) {
      URL.revokeObjectURL(savedDownloadUrlRef.current);
      savedDownloadUrlRef.current = null;
    }
    setSavedDownload(null);
  }, []);

  const appendSseEvent = useCallback((type: string, data: unknown) => {
    const eventLog = eventLogRef.current;
    shouldScrollEventLogToBottomRef.current = eventLog
      ? eventLog.scrollHeight - eventLog.scrollTop - eventLog.clientHeight <= 4
      : true;
    setSseEvents(currentEvents => [
      ...currentEvents,
      {
        type,
        data,
        receivedAt: new Date(),
      },
    ]);
  }, []);

  useEffect(() => {
    return () => {
      if (savedDownloadUrlRef.current) {
        URL.revokeObjectURL(savedDownloadUrlRef.current);
        savedDownloadUrlRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!shouldScrollEventLogToBottomRef.current) {
      return;
    }
    const eventLog = eventLogRef.current;
    if (eventLog) {
      eventLog.scrollTop = eventLog.scrollHeight;
    }
  }, [sseEvents.length]);

  const checkServerHealth = useCallback(async () => {
    const endpoint = normalizeEndpoint(apiEndpoint);

    if (!endpoint) {
      setServerHealthStatus('offline');
      setServerHealth(null);
      setLastHealthCheckedAt(new Date());
      return;
    }

    setServerHealthStatus(currentStatus => currentStatus === 'online' ? 'online' : 'checking');

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 3000);

    try {
      const response = await fetch(`${endpoint}/health`, {
        method: 'GET',
        cache: 'no-store',
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Health check failed with status ${response.status}`);
      }

      const health = await response.json() as ServerHealthResponse;
      if (health.status !== 'ok') {
        throw new Error(`Unexpected health status: ${health.status}`);
      }

      setServerHealthStatus('online');
      setServerHealth(health);
    } catch {
      setServerHealthStatus('offline');
      setServerHealth(null);
    } finally {
      window.clearTimeout(timeoutId);
      setLastHealthCheckedAt(new Date());
    }
  }, [apiEndpoint]);

  useEffect(() => {
    void checkServerHealth();
    const intervalId = window.setInterval(() => {
      void checkServerHealth();
    }, 30000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [checkServerHealth]);

  const getOptimizeJobStatus = useCallback(async (job: OptimizeJobResponse): Promise<OptimizeJobResponse> => {
    const response = await fetch(buildApiUrl(apiEndpoint, job.links.status), {
      method: 'GET',
      cache: 'no-store',
    });

    if (!response.ok) {
      throw new Error(`Server error (${response.status}): ${await getErrorDetail(response)}`);
    }

    return await response.json() as OptimizeJobResponse;
  }, [apiEndpoint]);

  const pollOptimizeJob = useCallback((job: OptimizeJobResponse): Promise<OptimizeJobResponse> => {
    return new Promise((resolve, reject) => {
      const poll = async () => {
        try {
          const updatedJob = await getOptimizeJobStatus(job);
          setScheduleStatus(updatedJob.status);

          if (TERMINAL_JOB_STATUSES.has(updatedJob.status)) {
            resolve(updatedJob);
            return;
          }

          window.setTimeout(() => void poll(), 1000);
        } catch (error) {
          reject(error);
        }
      };

      void poll();
    });
  }, [getOptimizeJobStatus]);

  const waitForOptimizeJob = useCallback((job: OptimizeJobResponse): Promise<OptimizeJobResponse> => {
    if (TERMINAL_JOB_STATUSES.has(job.status)) {
      return Promise.resolve(job);
    }

    if (typeof EventSource !== 'undefined') {
      return new Promise((resolve, reject) => {
        const eventSource = new EventSource(buildApiUrl(apiEndpoint, job.links.events));

        eventSource.addEventListener('status', (event) => {
          const parsedData = parseSseEventData(event);
          appendSseEvent('status', parsedData);
          const updatedJob = parsedData as Partial<OptimizeJobResponse>;
          if (updatedJob.status) {
            setScheduleStatus(updatedJob.status);
          }
        });

        eventSource.addEventListener('progress', (event) => {
          const parsedData = parseSseEventData(event);
          appendSseEvent('progress', parsedData);
          if (isProgressEventData(parsedData)) {
            setIncumbentResult(parsedData);
            if (typeof parsedData.currentBestScore === 'number') {
              setScheduleScore(parsedData.currentBestScore);
            }
            if (typeof parsedData.currentBestScore === 'number' && typeof parsedData.elapsedSeconds === 'number') {
              setProgressPoints(currentPoints => [...currentPoints, {
                currentBestScore: parsedData.currentBestScore as number,
                elapsedSeconds: parsedData.elapsedSeconds as number,
                commentCount: parsedData.commentCount,
                solutionIndex: parsedData.solutionIndex,
                source: parsedData.source,
              }]);
            }
          }
        });

        eventSource.addEventListener('phase', (event) => {
          const parsedData = parseSseEventData(event);
          appendSseEvent('phase', parsedData);
        });

        eventSource.addEventListener('complete', (event) => {
          eventSource.close();
          const parsedData = parseSseEventData(event);
          appendSseEvent('complete', parsedData);
          const completedJob = parsedData as OptimizeJobResponse;
          setCurrentJob(completedJob);
          resolve(completedJob);
        });

        eventSource.addEventListener('error', (event) => {
          eventSource.close();
          if ('data' in event && typeof event.data === 'string' && event.data) {
            const parsedData = parseSseEventData(event as MessageEvent);
            appendSseEvent('error', parsedData);
            reject(new Error((parsedData as OptimizeJobResponse).error ?? 'Optimization failed'));
          } else {
            appendSseEvent('error', 'Optimization event stream failed');
            void pollOptimizeJob(job).then(resolve, reject);
          }
        });
      });
    }

    return pollOptimizeJob(job);
  }, [apiEndpoint, appendSseEvent, pollOptimizeJob]);

  const handleOptimizeAndDownload = async () => {
    if (isRequiredDataMissing) {
      setErrorMessage(null);
      setSuccessMessage(null);
      setScheduleScore(null);
      setScheduleStatus(null);
      setCurrentJobId(null);
      setCurrentJob(null);
      setIncumbentResult(null);
      setProgressPoints([]);
      clearSavedDownload();
      setSseEvents([]);
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    setScheduleScore(null);
    setScheduleStatus(null);
    setCurrentJobId(null);
    setCurrentJob(null);
    setIncumbentResult(null);
    setProgressPoints([]);
    clearSavedDownload();
    setSseEvents([]);

    try {
      // Prepare form data
      const formData = new FormData();
      formData.append('yaml_content', currentYaml);

      if (prettifyArg !== null && prettifyArg !== undefined) {
        formData.append('prettify', String(prettifyArg));
      }

      if (timeoutArg !== null && timeoutArg !== undefined) {
        formData.append('timeout', String(timeoutArg));
      }

      const createResponse = await fetch(`${normalizeEndpoint(apiEndpoint)}/optimize`, {
        method: 'POST',
        body: formData,
      });

      if (!createResponse.ok) {
        throw new Error(`Server error (${createResponse.status}): ${await getErrorDetail(createResponse)}`);
      }

      const createdJob = await createResponse.json() as OptimizeJobResponse;
      setCurrentJobId(createdJob.jobId);
      setCurrentJob(createdJob);
      setScheduleStatus(createdJob.status);

      const completedJob = await waitForOptimizeJob(createdJob);
      setCurrentJob(completedJob);
      setScheduleStatus(completedJob.status);

      if (completedJob.score !== null) {
        setScheduleScore(completedJob.score);
      }
      if (completedJob.solverStatus) {
        setScheduleStatus(completedJob.solverStatus);
      }

      if (completedJob.error) {
        throw new Error(completedJob.error);
      }
      if (!completedJob.xlsxReady) {
        throw new Error(`No downloadable schedule is available. Job status: ${completedJob.status}`);
      }

      const xlsxResponse = await fetch(buildApiUrl(apiEndpoint, completedJob.links.xlsx), {
        method: 'GET',
      });

      if (!xlsxResponse.ok) {
        throw new Error(`Server error (${xlsxResponse.status}): ${await getErrorDetail(xlsxResponse)}`);
      }

      // Get the blob data (XLSX file)
      const blob = await xlsxResponse.blob();

      const url = URL.createObjectURL(blob);
      const filename = getFilenameFromContentDisposition(xlsxResponse.headers.get('Content-Disposition'));
      savedDownloadUrlRef.current = url;
      setSavedDownload({ url, filename });
      downloadFileFromUrl(url, filename);

      void fetch(buildApiUrl(apiEndpoint, `/optimize/${completedJob.jobId}`), {
        method: 'DELETE',
      });

      setSuccessMessage('Schedule optimized and downloaded successfully!');
    } catch (error) {
      console.error('Error during optimization:', error);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'An unexpected error occurred during optimization'
      );
    } finally {
      setIsLoading(false);
    }
  };

  const requestJobControl = async (action: 'cancel' | 'finish-now') => {
    if (!currentJobId) {
      return;
    }

    try {
      const response = await fetch(buildApiUrl(apiEndpoint, `/optimize/${currentJobId}/${action}`), {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error(`Server error (${response.status}): ${await getErrorDetail(response)}`);
      }

      const updatedJob = await response.json() as OptimizeJobResponse;
      setCurrentJob(updatedJob);
      setScheduleStatus(updatedJob.status);
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : `Unable to ${action === 'cancel' ? 'cancel optimization' : 'request current results'}`
      );
    }
  };

  const handleDownloadAgain = () => {
    if (!savedDownload) {
      return;
    }
    downloadFileFromUrl(savedDownload.url, savedDownload.filename);
  };

  const serverStatusClasses = serverHealthStatus === 'online'
    ? 'border-green-200 bg-green-50 text-green-700'
    : serverHealthStatus === 'offline'
      ? 'border-red-200 bg-red-50 text-red-700'
      : 'border-gray-200 bg-gray-50 text-gray-600';

  const runStatus = scheduleStatus ?? (isLoading ? 'Starting' : 'Idle');
  const runStatusClasses = isLoading
    ? 'bg-blue-50 text-blue-700 ring-blue-200'
    : errorMessage
      ? 'bg-red-50 text-red-700 ring-red-200'
      : successMessage
        ? 'bg-green-50 text-green-700 ring-green-200'
        : 'bg-gray-50 text-gray-700 ring-gray-200';

  return (
    <div className="container mx-auto px-4 py-6 lg:py-8">
      <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <h1 className="text-3xl font-bold text-gray-900">Optimize and Export</h1>
          <p className="mt-1 text-sm text-gray-600">
            Send the current schedule configuration to the backend and download the generated XLSX result.
          </p>
        </div>

        <div className={`inline-flex items-center gap-2.5 rounded-md border px-3 py-2 ${serverStatusClasses}`}>
          <span className="shrink-0">
            {serverHealthStatus === 'offline' ? (
              <FiWifiOff className="h-4 w-4" />
            ) : serverHealthStatus === 'checking' ? (
              <FiLoader className="h-4 w-4 animate-spin" />
            ) : (
              <FiWifi className="h-4 w-4" />
            )}
          </span>
          <span>
            <span className="block text-sm font-medium">
              Server: {serverHealthStatus === 'online' ? 'Online' : serverHealthStatus === 'offline' ? 'Offline' : 'Checking'}
            </span>
            <span className="mt-0.5 block text-xs opacity-75">Last checked: {formatCheckedTime(lastHealthCheckedAt)}</span>
          </span>
        </div>
      </div>

      {isRequiredDataMissing && (
        <div className="mb-5">
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            {isDateDataMissing ? (
              <>
                Please set up your dates first by visiting the{' '}
                <Link href="/dates" className="text-blue-600 underline hover:text-blue-800">
                  Dates
                </Link>{' '}
                tab.
              </>
            ) : isPeopleDataMissing ? (
              <>
                Please set up your people first by visiting the{' '}
                <Link href="/people" className="text-blue-600 underline hover:text-blue-800">
                  People
                </Link>{' '}
                tab.
              </>
            ) : (
              <>
                Please set up your shift types first by visiting the{' '}
                <Link href="/shift-types" className="text-blue-600 underline hover:text-blue-800">
                  Shift Types
                </Link>{' '}
                tab.
              </>
            )}
          </div>
        </div>
      )}

      <div className="mb-6 grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(380px,1.05fr)]">
        <section className="order-2 rounded-lg border border-gray-200 bg-white xl:order-1">
          <div className="border-b border-gray-200 px-5 py-4">
            <h2 className="text-base font-semibold text-gray-900">Configuration</h2>
            <p className="mt-0.5 text-sm text-gray-600">Solver and connection settings.</p>
          </div>
          <div className="space-y-5 p-5">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="flex min-h-20 cursor-pointer items-start gap-3 rounded-md border border-gray-200 bg-gray-50 p-3">
                <input
                  type="checkbox"
                  checked={prettifyArg}
                  onChange={(e) => setPrettifyArg(e.target.checked)}
                  className="mt-1 h-4 w-4 rounded text-blue-600 focus:ring-blue-500"
                />
                <span>
                  <span className="block text-sm font-medium text-gray-800">Prettify XLSX</span>
                  <span className="mt-1 block text-xs text-gray-500">Apply formatting to the generated workbook.</span>
                </span>
              </label>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Solver Timeout
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={timeoutArg}
                    onChange={(e) => setTimeoutArg(parseInt(e.target.value) || 300)}
                    min="1"
                    max="3600"
                    className="block w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm transition-colors focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                    placeholder="300"
                  />
                  <span className="text-sm text-gray-500">sec</span>
                </div>
              </div>
            </div>

            <details open className="rounded-md border border-gray-200 bg-gray-50">
              <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-gray-700">
                Backend settings
              </summary>
              <div className="space-y-4 border-t border-gray-200 p-3">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  API Endpoint
                </label>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <input
                    type="text"
                    value={apiEndpoint}
                    onChange={(e) => {
                      setApiEndpoint(e.target.value);
                      setServerHealth(null);
                      setServerHealthStatus('checking');
                      setLastHealthCheckedAt(null);
                    }}
                    className="block min-w-0 flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm transition-colors focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                    placeholder="http://localhost:8000"
                  />
                  <button
                    type="button"
                    onClick={() => void checkServerHealth()}
                    className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                  >
                    <FiRefreshCw className="h-4 w-4" />
                    Check Backend
                  </button>
                </div>

                {serverHealth && (
                  <div className="rounded-md border border-gray-200 bg-white px-3 py-2 text-xs text-gray-600">
                    <p>
                      API version: {serverHealth.apiVersion ?? serverHealth.version} · Frontend version: {CURRENT_APP_VERSION} · Backend version: {serverHealth.appVersion}
                    </p>
                    {hasVersionMismatch && (
                      <p className="mt-1 font-medium text-amber-700">
                        Frontend and backend versions do not match. If nothing breaks, you can continue.
                      </p>
                    )}
                  </div>
                )}

                {serverHealthStatus === 'offline' && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                    <div className="flex gap-2">
                      <FiAlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                      <span>Backend is not responding at the configured endpoint.</span>
                    </div>
                  </div>
                )}
              </div>
            </details>

            <div className="border-t border-gray-200 pt-5">
              <button
                onClick={handleOptimizeAndDownload}
                disabled={isOptimizeDisabled}
                className={`inline-flex w-full items-center justify-center gap-2 rounded-md px-4 py-2.5 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                  isOptimizeDisabled
                    ? 'cursor-not-allowed bg-gray-400 text-white'
                    : 'bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500'
                }`}
              >
                {isLoading ? (
                  <>
                    <FiLoader className="h-5 w-5 animate-spin" />
                    Optimizing...
                  </>
                ) : (
                  <>
                    <FiDownload className="h-5 w-5" />
                    Optimize and Download
                  </>
                )}
              </button>
              {optimizeDisabledReason && (
                <p className="mt-2 text-sm text-amber-700">{optimizeDisabledReason}</p>
              )}
            </div>
          </div>
        </section>

        <section className="order-1 rounded-lg border border-gray-200 bg-white xl:order-2">
          <div className="border-b border-gray-200 px-5 py-4">
            <h2 className="text-base font-semibold text-gray-900">Live Result</h2>
            <p className="mt-0.5 text-sm text-gray-600">Current job, incumbent score, and downloadable file.</p>
          </div>
          <div className="space-y-4 p-5">
            <div className="flex flex-col gap-3 border-b border-gray-200 pb-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-medium uppercase text-gray-500">
                  {isLoading ? 'Live Incumbent Score' : scheduleScore !== null ? 'Final Score' : 'Score'}
                </p>
                <p className="mt-1 text-4xl font-bold text-gray-900">
                  {scheduleScore !== null ? formatScore(scheduleScore) : 'No incumbent yet'}
                </p>
                <p className="mt-1 text-xs text-gray-500">Higher scores are better.</p>
              </div>
              <span className={`inline-flex w-fit items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold ring-1 ${runStatusClasses}`}>
                {isLoading ? <FiLoader className="h-4 w-4 animate-spin" /> : successMessage ? <FiCheckCircle className="h-4 w-4" /> : errorMessage ? <FiAlertCircle className="h-4 w-4" /> : <FiActivity className="h-4 w-4" />}
                {runStatus}
              </span>
            </div>

            <div className="text-sm text-gray-600">
              {!currentJobId ? (
                <p>No optimization has been started.</p>
              ) : isLoading && !incumbentResult ? (
                <p>Waiting for first feasible solution...</p>
              ) : incumbentResult ? (
                <p>
                  {incumbentResult.solutionIndex !== undefined && incumbentResult.solutionIndex !== null ? `Solution #${incumbentResult.solutionIndex}` : 'Incumbent'}
                  {' · '}
                  {incumbentResult.elapsedSeconds !== undefined ? formatElapsedSeconds(incumbentResult.elapsedSeconds) : 'time unavailable'}
                  {' · '}
                  {incumbentResult.commentCount !== undefined && incumbentResult.commentCount !== null ? `${incumbentResult.commentCount} comments` : 'comments unavailable'}
                  {incumbentResult.source ? ` · ${incumbentResult.source}` : ''}
                </p>
              ) : (
                <p>Job {currentJobId}</p>
              )}
              {currentJobId && <p className="mt-1 break-all text-xs text-gray-400">Job ID: {currentJobId}</p>}
            </div>

            {progressPoints.length >= 2 && (
              <OptimizationProgressChart points={progressPoints} isActive={isJobActive} />
            )}

            {(savedDownload || isJobActive) && (
              <div className={`flex flex-col gap-2 sm:flex-row ${isJobActive ? 'sticky bottom-3 z-10 rounded-lg border border-blue-100 bg-white/95 p-2 shadow-lg backdrop-blur-sm' : ''}`}>
                {savedDownload && (
                  <button
                    type="button"
                    onClick={handleDownloadAgain}
                    className="inline-flex flex-1 items-center justify-center gap-2 rounded-md border border-green-300 bg-white px-3 py-2 text-sm font-medium text-green-700 transition-colors hover:bg-green-50 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2"
                  >
                    <FiDownload className="h-4 w-4" />
                    Download Again
                    <span className="truncate text-xs font-normal text-green-600">{savedDownload.filename}</span>
                  </button>
                )}

                {isJobActive && (
                  <>
                    <button
                      type="button"
                      onClick={() => void requestJobControl('finish-now')}
                      disabled={Boolean(currentJob?.finishNowRequested) || isCancelling}
                      title="Finish with the current incumbent result"
                      className="inline-flex flex-1 items-center justify-center gap-2 rounded-md border border-blue-300 bg-white px-3 py-2 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:text-gray-400"
                    >
                      <FiDownload className="h-4 w-4" />
                      Get Results Now
                    </button>
                    <button
                      type="button"
                      onClick={() => void requestJobControl('cancel')}
                      disabled={isCancelling}
                      title="Stop the active optimization job"
                      className="inline-flex items-center justify-center gap-2 rounded-md border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-700 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:border-gray-200 disabled:text-gray-400"
                    >
                      <FiAlertCircle className="h-4 w-4" />
                      {isCancelling ? 'Cancelling...' : 'Cancel'}
                    </button>
                  </>
                )}
              </div>
            )}

            {successMessage && (
              <div className="rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
                <div className="flex gap-2">
                  <FiCheckCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{successMessage}</span>
                </div>
              </div>
            )}

            {errorMessage && (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                <div className="flex gap-2">
                  <FiAlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <p>{errorMessage}</p>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>

      <details open={isLoading || Boolean(errorMessage) || !successMessage} className="rounded-lg border border-gray-200 bg-white">
        <summary className="flex cursor-pointer list-none items-center gap-2 border-b border-gray-200 px-5 py-4">
          <FiActivity className="h-4 w-4 text-gray-500" />
          <h2 className="text-base font-semibold text-gray-900">Optimization Events</h2>
          <span className="ml-auto text-xs text-gray-500">{sseEvents.length} events</span>
        </summary>
        <div ref={eventLogRef} data-testid="optimization-events-log" className="max-h-[28rem] overflow-auto bg-gray-50">
          {sseEvents.length === 0 ? (
            <div className="px-5 py-6 text-sm text-gray-500">
              <p>{isLoading ? 'Waiting for optimization events...' : 'No optimization events yet.'}</p>
            </div>
          ) : (
            <ul className="space-y-0 p-5">
              {sseEvents.map((event, index) => (
                <li key={`${event.type}-${index}`} className="relative grid gap-3 border-l border-gray-200 pb-5 pl-5 last:pb-0 lg:grid-cols-[10rem_minmax(0,1fr)]">
                  <span className="absolute -left-1.5 top-1.5 h-3 w-3 rounded-full bg-white ring-4 ring-gray-200" />
                  <div className="flex flex-row items-baseline gap-3 lg:flex-col lg:gap-1">
                    <span className={`w-fit rounded-full px-2 py-0.5 text-xs font-semibold uppercase ring-1 ${getEventBadgeClasses(event.type)}`}>{event.type}</span>
                    <span className="text-xs text-gray-500">{formatCheckedTime(event.receivedAt)}</span>
                  </div>
                  <div className="min-w-0 rounded-md border border-gray-200 bg-white p-3 text-xs text-gray-700">
                    {isProgressEventData(event.data) && (
                      <p className="font-semibold text-gray-900">{formatProgressSummary(event.data)}</p>
                    )}
                    {event.type === 'phase' && isPhaseEventData(event.data) && event.data.message && (
                      <p className="font-semibold text-gray-900">{event.data.message}</p>
                    )}
                    <details className={isProgressEventData(event.data) || event.type === 'phase' ? 'mt-2' : ''}>
                      <summary className="cursor-pointer text-gray-500">Raw event data</summary>
                      <pre className="mt-2 whitespace-pre-wrap break-words">{formatSseEventData(event.data)}</pre>
                    </details>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>

    </div>
  );
}
