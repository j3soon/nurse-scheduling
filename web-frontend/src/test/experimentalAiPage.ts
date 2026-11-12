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

// This code is mostly AI generated.

import { saveChatHistory } from '@/app/experimental-ai/chatHistory';
import type { StoredChatConversation } from '@/app/experimental-ai/chatConversation';
import type { SessionEvent, SessionStreamOptions } from '@/app/experimental-ai/sessionEvents';


const mockCompactSession = vi.hoisted(() => vi.fn());
const mockCreateSession = vi.hoisted(() => vi.fn());
const mockGetUploads = vi.hoisted(() => vi.fn());
const mockRemoveUpload = vi.hoisted(() => vi.fn());
const mockDownloadGeneratedZip = vi.hoisted(() => vi.fn());
const mockRemoveGeneratedZip = vi.hoisted(() => vi.fn());
const mockUploadFiles = vi.hoisted(() => vi.fn());
const mockUploadFile = vi.hoisted(() => vi.fn());
const mockDownloadOptimization = vi.hoisted(() => vi.fn());
const mockCancelOptimization = vi.hoisted(() => vi.fn());
const mockGetBackendVersion = vi.hoisted(() => vi.fn());
const mockGetChatExportUrl = vi.hoisted(() => vi.fn());
const mockGetCapabilities = vi.hoisted(() => vi.fn());
const mockGetModels = vi.hoisted(() => vi.fn());
const mockGetSessionModelSelection = vi.hoisted(() => vi.fn());
const mockUpdateSessionModelSelection = vi.hoisted(() => vi.fn());
const mockGetSessionStatus = vi.hoisted(() => vi.fn());
const mockRunEvents = vi.hoisted(() => vi.fn());
const mockSendMessage = vi.hoisted(() => vi.fn());
const mockStreamSessionEvents = vi.hoisted(() => vi.fn());
const mockStopSession = vi.hoisted(() => vi.fn());
const mockGenerateYaml = vi.hoisted(() => vi.fn(() => 'description: current Schedule Spec\n'));
const mockQueueMessage = vi.hoisted(() => vi.fn());
const mockUpdateSessionSchedule = vi.hoisted(() => vi.fn());
const mockLoadFromYaml = vi.hoisted(() => vi.fn());
const mockUseTabSwitchWarning = vi.hoisted(() => vi.fn());
const MockAiStaleRunError = vi.hoisted(() => class AiStaleRunError extends Error {});
const MockAiHttpError = vi.hoisted(() => class AiHttpError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
});
const mockNormalizeAiEndpoint = vi.hoisted(() => (endpoint: string) => {
  const trimmed = endpoint.trim().replace(/\/+$/, '');
  if (!trimmed) return '';
  return /^[a-z]+:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
});

vi.mock('@/app/experimental-ai/aiClient', async importOriginal => {
  const awaitClient = await importOriginal<typeof import('@/app/experimental-ai/aiClient')>();
  return ({
  AiHttpError: MockAiHttpError,
  AiStaleRunError: MockAiStaleRunError,
  DEFAULT_SESSION_RETENTION_SECONDS: 172800,
  LOCAL_AI_API_URL: 'http://localhost:8001',
  PRODUCTION_AI_API_URL: 'https://api.nursescheduling.org/ai',
  createSession: mockCreateSession,
  compactSession: mockCompactSession,
  downloadOptimization: mockDownloadOptimization,
  cancelOptimization: mockCancelOptimization,
  downloadGeneratedZip: mockDownloadGeneratedZip,
  removeGeneratedZip: mockRemoveGeneratedZip,
  getUploads: mockGetUploads,
  removeUpload: mockRemoveUpload,
  getAiBaseUrl: () => '/ai',
  getCapabilities: mockGetCapabilities,
  getModels: mockGetModels,
  getSessionModelSelection: mockGetSessionModelSelection,
  updateSessionModelSelection: mockUpdateSessionModelSelection,
  getChatExportUrl: mockGetChatExportUrl,
  getBackendVersion: mockGetBackendVersion,
  getSessionStatus: mockGetSessionStatus,
  normalizeAiEndpoint: mockNormalizeAiEndpoint,
  isAuthenticationError: awaitClient.isAuthenticationError,
  isOfficialAiEndpoint: (endpoint: string) => (
    endpoint === '/ai' || mockNormalizeAiEndpoint(endpoint) === 'https://api.nursescheduling.org/ai'
  ),
  queueMessage: mockQueueMessage,
  sendMessage: mockSendMessage,
  streamSessionEvents: mockStreamSessionEvents,
  stopSession: mockStopSession,
  updateSessionSchedule: mockUpdateSessionSchedule,
  uploadFile: mockUploadFile,
  uploadFiles: mockUploadFiles,
});
});

// The Node build of Sentry has no feedback widget.
vi.mock('@sentry/nextjs', async importOriginal => ({ ...await importOriginal<object>(), getFeedback: () => undefined }));
vi.mock('@/utils/yamlGenerator', () => ({
  generateYamlFromState: mockGenerateYaml,
}));

vi.mock('@/hooks/useScheduleSpec', () => ({
  useScheduleSpec: () => ({
    apiVersionData: 'alpha',
    descriptionData: 'current Schedule Spec',
    dateData: { items: [], groups: [], range: {} },
    peopleData: { items: [], groups: [] },
    shiftTypeData: { items: [], groups: [] },
    preferences: [],
    exportData: undefined,
    savedState: {
      apiVersion: 'alpha', description: 'current Schedule Spec',
      dates: { items: [], groups: [], range: {} },
      people: { items: [], groups: [] }, shiftTypes: { items: [], groups: [] }, preferences: [],
    },
    effectiveExportData: { formatting: [{ type: 'row', people: ['ALL'], backgroundColor: '#fefce8' }] },
    filterAutoGeneratedState: (state: unknown) => state,
    loadFromYaml: mockLoadFromYaml,
  }),
}));

vi.mock('@/utils/unsavedEditingState', () => ({
  useTabSwitchWarning: mockUseTabSwitchWarning,
}));

const defaultCapabilities = {
  app_version: 'v0.4.3',
  session_retention_seconds: 172800,
  file_attachments: {
    enabled: true,
    max_files: 8,
    max_bytes_per_file: 5_000_000,
    max_bytes_per_session: 200_000_000,
  },
};

function runEvents(stream: SessionStreamOptions | undefined, runId: string): SessionStreamOptions | undefined {
  if (!stream) return undefined;
  return {
    onEvent: (event: SessionEvent) => {
      if (event.type !== 'session_reset') stream.onEvent({ type: 'run_context', runId });
      stream.onEvent({ ...event, runId });
    },
  };
}

export function setupExperimentalAiPageTests() {
  let pendingForegroundRunId: string | null = null;
  beforeEach(() => {
    pendingForegroundRunId = null;
    vi.restoreAllMocks();
    vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
    mockGetChatExportUrl.mockReset().mockResolvedValue('/ai/v1/sessions/session-id/export?token=temporary');
    mockCreateSession.mockReset().mockResolvedValue('session-id');
    mockGetUploads.mockReset().mockResolvedValue([]);
    mockRemoveUpload.mockReset().mockResolvedValue(undefined);
    mockDownloadGeneratedZip.mockReset().mockResolvedValue(new Blob(['zip']));
    mockRemoveGeneratedZip.mockReset().mockResolvedValue(undefined);
    let uploadIndex = 0;
    mockUploadFiles.mockReset().mockImplementation(async (_sessionId: string, files: File[]) => files.map(file => ({
      id: `upload-${++uploadIndex}`, filename: file.name, media_type: file.type || 'application/octet-stream', bytes: file.size,
    })));
    // uploadFile retries inside the client, so page tests see one upload request per file.
    mockUploadFile.mockReset().mockImplementation((sessionId: string, file: File, signal: AbortSignal, authToken: string | null,
      endpoint: string) => mockUploadFiles(sessionId, [file], authToken, endpoint, signal));
    mockDownloadOptimization.mockReset().mockResolvedValue(new Blob(['workbook']));
    mockGetCapabilities.mockReset().mockResolvedValue(defaultCapabilities);
    mockGetModels.mockReset();
    mockGetSessionModelSelection.mockReset();
    mockUpdateSessionModelSelection.mockReset();
    mockGetBackendVersion.mockReset().mockResolvedValue('v0.4.3');
    mockCancelOptimization.mockReset().mockResolvedValue(undefined);
    mockGetSessionStatus.mockReset().mockResolvedValue(172800);
    mockRunEvents.mockReset().mockImplementation(async (
      _sessionId: string,
      _message: string,
      callbacks: SessionStreamOptions,
    ) => {
      callbacks.onEvent({ type: 'delta', text: 'Alice' });
      callbacks.onEvent({ type: 'delta', text: ' works Monday.' });
    });
    mockCompactSession.mockReset().mockResolvedValue('compact-run');
    mockStreamSessionEvents.mockReset().mockImplementation(() => new Promise<void>(() => {}));
    // Run fixtures publish normalized events while POST returns only its acknowledgement.
    mockSendMessage.mockReset().mockImplementation(async (id, message, signal, token, endpoint) => {
      const stream = mockStreamSessionEvents.mock.calls.at(-1)?.[1] as SessionStreamOptions;
      const runId = `user-run-${mockSendMessage.mock.calls.length}`;
      pendingForegroundRunId = runId;
      const callbacks = runEvents(stream, runId)!;
      void Promise.resolve(mockRunEvents(id, message, callbacks, signal, token, endpoint))
        .then(() => {
          if (pendingForegroundRunId === runId) pendingForegroundRunId = null;
          if (signal.aborted) return;
          callbacks.onEvent({ type: 'done', runId });
        }, (error: Error) => {
          if (pendingForegroundRunId === runId) pendingForegroundRunId = null;
          if (signal.aborted) return;
          if (error instanceof MockAiStaleRunError) callbacks.onEvent({ type: 'stale', message: error.message });
          else callbacks.onEvent({ type: 'error', message: error.message });
        });
      return runId;
    });
    mockStopSession.mockReset().mockImplementation(async () => {
      const stream = mockStreamSessionEvents.mock.calls.at(-1)?.[1] as SessionStreamOptions | undefined;
      if (pendingForegroundRunId) runEvents(stream, pendingForegroundRunId)?.onEvent({ type: 'stopped' });
    });
    mockGenerateYaml.mockClear().mockReturnValue('description: current Schedule Spec\n');
    mockQueueMessage.mockReset().mockResolvedValue(undefined);
    mockUpdateSessionSchedule.mockReset().mockResolvedValue(undefined);
    mockLoadFromYaml.mockReset();
    mockUseTabSwitchWarning.mockReset();
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
}

export const seedRecentChat = (sessionId = 'older-session', endpoint = '/ai'): StoredChatConversation => {
  const conversation: StoredChatConversation = {
    sessionId, endpoint, lastActivityAt: Date.now() - 1000,
    expiresAt: Date.now() + 86400_000, retentionSeconds: 30 * 86400,
    syncedScheduleSpec: 'description: older schedule\n', sessionEventId: 5,
    messages: [{ id: 'old-question', role: 'user', content: `Review ${sessionId}` },
      { id: 'old-answer', role: 'assistant', content: 'An earlier answer.', activity: [{ kind: 'response', text: 'An earlier answer.' }] }],
  };
  saveChatHistory(conversation, true);
  return conversation;
};

export {
  mockCompactSession,
  mockCreateSession,
  mockGetUploads,
  mockRemoveUpload,
  mockDownloadGeneratedZip,
  mockRemoveGeneratedZip,
  mockUploadFiles,
  mockUploadFile,
  mockDownloadOptimization,
  mockCancelOptimization,
  mockGetBackendVersion,
  mockGetChatExportUrl,
  mockGetCapabilities,
  mockGetModels,
  mockGetSessionModelSelection,
  mockUpdateSessionModelSelection,
  mockGetSessionStatus,
  mockRunEvents,
  mockSendMessage,
  mockStreamSessionEvents,
  mockStopSession,
  mockGenerateYaml,
  mockQueueMessage,
  mockUpdateSessionSchedule,
  mockLoadFromYaml,
  mockUseTabSwitchWarning,
  MockAiStaleRunError,
  MockAiHttpError,
  mockNormalizeAiEndpoint,
  defaultCapabilities,
  runEvents,
};
