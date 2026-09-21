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

'use client';

import Image from 'next/image';
import { ChangeEvent, DragEvent, FormEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { FiArrowDown, FiArrowUp, FiChevronDown, FiDownload, FiMic, FiPlus, FiSquare } from 'react-icons/fi';
import AppVersionText from '@/components/AppVersionText';
import BackendTokenField, { isValidBackendToken } from '@/components/BackendTokenField';
import PageDocumentationLink from '@/components/PageDocumentationLink';
import {
  DOCUMENTATION_URLS,
  FIREFOX_NIGHTLY_URL,
  FIREFOX_SPEECH_RECOGNITION_STATUS_URL,
  GITHUB_AI_BETA_ACCESS_URL,
  GITHUB_PRIVACY_URL,
  GITHUB_TAGS_URL,
} from '@/constants/urls';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { useTabSwitchWarning } from '@/utils/unsavedEditingState';
import { CURRENT_APP_VERSION } from '@/utils/version';
import { generateYamlFromState } from '@/utils/yamlGenerator';
import yaml from 'js-yaml';
import { ActivityEntry, AssistantActivity } from './AssistantActivity';
import { ChatExportMessage, downloadChatExport } from './chatExport';
import {
  AiCapabilities,
  AiHttpError,
  AiStaleTurnError,
  DEFAULT_SESSION_RETENTION_SECONDS,
  LOCAL_AI_API_URL,
  OptimizationActivity,
  PRODUCTION_AI_API_URL,
  ToolActivity,
  approveProposal,
  createSession,
  downloadOptimization,
  getAiBaseUrl,
  getCapabilities,
  getSessionStatus,
  isOfficialAiEndpoint,
  normalizeAiEndpoint,
  queueMessage,
  rejectProposal,
  streamMessage,
  streamSessionEvents,
  stopSession,
  updateSessionSchedule,
} from './aiClient';

interface ChatMessage extends ChatExportMessage {
  id: string;
  retry?: {
    question: string;
    requiresAttachments: boolean;
  };
  optimizerJob?: Pick<OptimizationActivity, 'jobId' | 'downloadable'>;
}

const AI_STORAGE_KEY = 'nurse-scheduling-ai-data';
const AI_AUTH_STORAGE_KEY = 'nurse-scheduling-ai-auth';
const AI_SERVER_STORAGE_KEY = 'nurse-scheduling-ai-server';
const AI_CONVERSATION_STORAGE_KEY = 'nurse-scheduling-ai-conversation';
const FIREFOX_ON_DEVICE_SPEECH_VERSION = 157;
const SPEECH_LANGUAGES = [
  { value: '', label: 'Browser default' },
  { value: 'en-US', label: 'English (United States)' },
  { value: 'en-GB', label: 'English (United Kingdom)' },
  { value: 'zh-TW', label: 'Mandarin (Taiwan)' },
  { value: 'zh-CN', label: 'Mandarin (China)' },
  { value: 'yue-Hant-HK', label: 'Cantonese (Hong Kong)' },
  { value: 'ja-JP', label: 'Japanese' },
  { value: 'ko-KR', label: 'Korean' },
  { value: 'es-ES', label: 'Spanish' },
  { value: 'fr-FR', label: 'French' },
  { value: 'de-DE', label: 'German' },
] as const;

interface AiPreferences {
  showReasoning: boolean;
  showTools: boolean;
}

interface StoredAiAuth {
  endpoint?: unknown;
  token?: unknown;
  tokens?: unknown;
}

type AiServerStatus = 'checking' | 'online' | 'offline' | 'unauthorized';

interface BrowserSpeechRecognitionResult {
  readonly length: number;
  readonly [index: number]: { transcript: string };
}

interface BrowserSpeechRecognitionEvent {
  readonly results: {
    readonly length: number;
    readonly [index: number]: BrowserSpeechRecognitionResult;
  };
}

interface BrowserSpeechRecognitionErrorEvent {
  readonly error?: string;
}

// Silence and a deliberate stop both surface as errors, so only a real fault is reported.
const BENIGN_SPEECH_ERRORS = new Set(['no-speech', 'aborted']);

interface BrowserSpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  processLocally?: boolean;
  onresult: ((event: BrowserSpeechRecognitionEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: BrowserSpeechRecognitionErrorEvent) => void) | null;
  start(): void;
  stop(): void;
}

type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

declare global {
  interface Window {
    SpeechRecognition?: BrowserSpeechRecognitionConstructor;
    webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
  }
}

function readStoredAuthTokens(): Record<string, string> {
  try {
    const stored = window.localStorage.getItem(AI_AUTH_STORAGE_KEY);
    if (stored === null) return {};
    const parsed = JSON.parse(stored) as StoredAiAuth;
    const tokens = typeof parsed.tokens === 'object' && parsed.tokens !== null
      ? Object.fromEntries(Object.entries(parsed.tokens).filter((entry): entry is [string, string] => (
          typeof entry[1] === 'string' && isValidBackendToken(entry[1].trim())
        )))
      : {};
    if (
      typeof parsed.endpoint === 'string'
      && typeof parsed.token === 'string'
      && isValidBackendToken(parsed.token.trim())
    ) {
      tokens[parsed.endpoint] = parsed.token.trim();
    }
    return tokens;
  } catch {
    return {};
  }
}

function persistAuthTokens(tokens: Record<string, string>): void {
  if (Object.keys(tokens).length === 0) {
    window.localStorage.removeItem(AI_AUTH_STORAGE_KEY);
  } else {
    window.localStorage.setItem(AI_AUTH_STORAGE_KEY, JSON.stringify({ tokens }));
  }
}

interface SelectedAttachment {
  id: string;
  file: File;
  kind: 'image' | 'file';
  previewUrl?: string;
}

interface QueuedChatMessage {
  id: string;
  content: string;
}

interface StoredChatConversation {
  sessionId: string;
  endpoint: string;
  expiresAt: number;
  retentionSeconds: number;
  messages: ChatMessage[];
  syncedSchedule: string;
  proposalDiff: string | null;
  sessionEventId?: number;
  activeOptimization?: OptimizationActivity | null;
}

const DISABLED_FILE_CAPABILITY: AiCapabilities['file_attachments'] = {
  enabled: false,
  max_files: 1,
  max_bytes_per_file: 1,
};

function fileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf('.');
  return lastDot < 0 ? '' : filename.slice(lastDot).toLowerCase();
}

function messageId(): string {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`;
}

function isActivityEntry(value: unknown): value is ActivityEntry {
  if (typeof value !== 'object' || value === null || !('kind' in value)) return false;
  if (value.kind === 'response' || value.kind === 'reasoning') {
    return 'text' in value && typeof value.text === 'string';
  }
  if (value.kind === 'schedule-change') {
    return 'before' in value && typeof value.before === 'string'
      && 'after' in value && typeof value.after === 'string';
  }
  return value.kind === 'tool'
    && 'name' in value && typeof value.name === 'string'
    && 'arguments' in value && typeof value.arguments === 'string'
    && 'result' in value && typeof value.result === 'string'
    && 'ok' in value && typeof value.ok === 'boolean';
}

function isChatMessage(value: unknown): value is ChatMessage {
  if (typeof value !== 'object' || value === null) return false;
  const message = value as Partial<ChatMessage>;
  return typeof message.id === 'string'
    && (message.role === 'user' || message.role === 'assistant' || message.role === 'optimizer')
    && typeof message.content === 'string'
    && (message.attachmentNames === undefined
      || (Array.isArray(message.attachmentNames) && message.attachmentNames.every(name => typeof name === 'string')))
    && (message.activity === undefined
      || (Array.isArray(message.activity) && message.activity.every(isActivityEntry)))
    && (message.status === undefined || message.status === 'pending' || message.status === 'failed')
    && (message.responseStartedAt === undefined || Number.isFinite(message.responseStartedAt))
    && (message.responseCompletedAt === undefined || Number.isFinite(message.responseCompletedAt))
    && (message.retry === undefined || (
      typeof message.retry === 'object'
      && message.retry !== null
      && typeof message.retry.question === 'string'
      && typeof message.retry.requiresAttachments === 'boolean'
    ))
    && (message.optimizerJob === undefined || (message.optimizerJob !== null
      && typeof message.optimizerJob.jobId === 'string'
      && typeof message.optimizerJob.downloadable === 'boolean'
    ));
}

function readStoredConversation(): StoredChatConversation | null {
  try {
    const raw = window.sessionStorage.getItem(AI_CONVERSATION_STORAGE_KEY);
    if (raw === null) return null;
    const value = JSON.parse(raw) as Partial<StoredChatConversation>;
    if (
      typeof value.sessionId !== 'string'
      || !value.sessionId
      || typeof value.endpoint !== 'string'
      || !(value.endpoint === '/ai' || normalizeAiEndpoint(value.endpoint))
      || !Number.isFinite(value.expiresAt)
      || !Number.isInteger(value.retentionSeconds)
      || (value.retentionSeconds ?? 0) <= 0
      || !Array.isArray(value.messages)
      || !value.messages.every(isChatMessage)
      || (value.sessionEventId !== undefined
        && (!Number.isSafeInteger(value.sessionEventId) || value.sessionEventId < 0))
      || (value.activeOptimization !== undefined && value.activeOptimization !== null && (
        typeof value.activeOptimization.jobId !== 'string'
        || typeof value.activeOptimization.state !== 'string'
        || typeof value.activeOptimization.terminal !== 'boolean'
        || typeof value.activeOptimization.downloadable !== 'boolean'
      ))
      || typeof value.syncedSchedule !== 'string'
      || (value.proposalDiff !== null && typeof value.proposalDiff !== 'string')
    ) return null;
    return {
      ...value,
      endpoint: value.endpoint === '/ai' ? value.endpoint : normalizeAiEndpoint(value.endpoint),
    } as StoredChatConversation;
  } catch {
    return null;
  }
}

function retentionLabel(seconds: number): string {
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return `${hours} ${hours === 1 ? 'hour' : 'hours'}`;
  }
  return `${seconds.toLocaleString()} seconds`;
}

function formatSessionExpiration(timestamp: number): string {
  return new Date(timestamp).toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  });
}

function formatResponseDuration(startedAt: number, completedAt: number): string {
  const seconds = Math.max(0, completedAt - startedAt) / 1000;
  if (seconds < 1) return '<1s';
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function formatResponseTime(timestamp: number): string {
  const completed = new Date(timestamp);
  const now = new Date();
  const sameDate = completed.getFullYear() === now.getFullYear()
    && completed.getMonth() === now.getMonth()
    && completed.getDate() === now.getDate();
  return completed.toLocaleString([], sameDate
    ? { hour: 'numeric', minute: '2-digit' }
    : { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function isAuthenticationError(error: unknown): boolean {
  return typeof error === 'object'
    && error !== null
    && 'status' in error
    && error.status === 401;
}

function finishToolActivity(entries: ActivityEntry[], result: ToolActivity): ActivityEntry[] {
  let runningIndex = -1;
  entries.forEach((entry, index) => {
    if (entry.kind === 'tool' && entry.state === 'running') runningIndex = index;
  });
  const completed = { kind: 'tool' as const, ...result };
  if (runningIndex < 0) return [...entries, completed];
  return entries.map((entry, index) => (index === runningIndex ? completed : entry));
}

function interruptRunningTools(entries: ActivityEntry[]): ActivityEntry[] {
  return entries.map(entry => (
    entry.kind === 'tool' && entry.state === 'running'
      ? { ...entry, state: 'interrupted' as const }
      : entry
  ));
}

function appendResponseActivity(entries: ActivityEntry[], text: string): ActivityEntry[] {
  const last = entries[entries.length - 1];
  if (last?.kind === 'response') {
    return [...entries.slice(0, -1), { ...last, text: last.text + text }];
  }
  return [...entries, { kind: 'response', text }];
}

function ThinkingIndicator() {
  return (
    <span role="status" aria-label="Thinking" className="inline-flex items-center gap-2 text-gray-600">
      <span>Thinking</span>
      <span aria-hidden="true" className="inline-flex gap-1">
        {[0, 1, 2].map(index => (
          <span
            key={index}
            className="h-1.5 w-1.5 rounded-full bg-current motion-safe:animate-pulse"
            style={{ animationDelay: `${index * 160}ms` }}
          />
        ))}
      </span>
    </span>
  );
}

export default function ExperimentalAiPage() {
  const {
    apiVersionData,
    descriptionData,
    dateData,
    peopleData,
    shiftTypeData,
    preferences,
    exportData,
    filterAutoGeneratedState,
    loadFromYaml,
  } = useSchedulingData();
  const scheduleYaml = useMemo(() => generateYamlFromState(filterAutoGeneratedState({
    apiVersion: apiVersionData,
    description: descriptionData,
    dates: dateData,
    people: peopleData,
    shiftTypes: shiftTypeData,
    preferences,
    ...(exportData ? { export: exportData } : {}),
  })), [
    apiVersionData,
    dateData,
    descriptionData,
    exportData,
    filterAutoGeneratedState,
    peopleData,
    preferences,
    shiftTypeData,
  ]);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionExpiresAt, setSessionExpiresAt] = useState<number | null>(null);
  const [sessionRetentionSeconds, setSessionRetentionSeconds] = useState(DEFAULT_SESSION_RETENTION_SECONDS);
  const [conversationUnavailable, setConversationUnavailable] = useState(false);
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [activeOptimization, setActiveOptimization] = useState<OptimizationActivity | null>(null);
  const [downloadingOptimizationId, setDownloadingOptimizationId] = useState<string | null>(null);
  const [isClientReady, setIsClientReady] = useState(false);
  const [aiEndpoint, setAiEndpoint] = useState(getAiBaseUrl);
  const [serverStatus, setServerStatus] = useState<AiServerStatus>('checking');
  const [isEditingServer, setIsEditingServer] = useState(false);
  const [customEndpoint, setCustomEndpoint] = useState('');
  const [serverError, setServerError] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [authToken, setAuthToken] = useState<string | null>(null);
  const [rememberAuthToken, setRememberAuthToken] = useState(false);
  const [isEditingAuthToken, setIsEditingAuthToken] = useState(false);
  const [authRejected, setAuthRejected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [capabilitiesError, setCapabilitiesError] = useState<string | null>(null);
  const [fileCapability, setFileCapability] = useState(DISABLED_FILE_CAPABILITY);
  const [selectedAttachments, setSelectedAttachments] = useState<SelectedAttachment[]>([]);
  const [isDraggingFiles, setIsDraggingFiles] = useState(false);
  const [queuedMessages, setQueuedMessages] = useState<QueuedChatMessage[]>([]);
  const [steeringAssistantId, setSteeringAssistantId] = useState<string | null>(null);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [firefoxVersion, setFirefoxVersion] = useState<number | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [speechLanguage, setSpeechLanguage] = useState('');
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [showReasoning, setShowReasoning] = useState(true);
  const [showTools, setShowTools] = useState(true);
  const [proposalDiff, setProposalDiff] = useState<string | null>(null);
  const [proposalNotice, setProposalNotice] = useState<string | null>(null);
  const [isApplyingProposal, setIsApplyingProposal] = useState(false);
  const syncedScheduleRef = useRef<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const sessionEndpointRef = useRef<string | null>(null);
  const authTokensRef = useRef<Record<string, string>>({});
  const abortControllerRef = useRef<AbortController | null>(null);
  const sessionEventsControllerRef = useRef<AbortController | null>(null);
  const lastSessionEventIdRef = useRef(0);
  const backgroundAssistantIdRef = useRef<string | null>(null);
  const backgroundTurnActiveRef = useRef(false);
  const scheduleYamlRef = useRef(scheduleYaml);
  const sandboxScheduleRef = useRef<string | null>(null);
  const selectedAttachmentsRef = useRef<SelectedAttachment[]>([]);
  const followPageBottomRef = useRef(true);
  const hasMessagesRef = useRef(false);
  const composerRef = useRef<HTMLFormElement | null>(null);
  const draftInputRef = useRef<HTMLTextAreaElement | null>(null);
  const composerDragDepthRef = useRef(0);
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const queuedMessagesRef = useRef<QueuedChatMessage[]>([]);
  const optimizationDownloadUrlRef = useRef<string | null>(null);
  const conversationStorageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const persistConversationRef = useRef<(() => void) | null>(null);
  const checkedSessionRef = useRef<string | null>(null);
  const reportRequestError = useCallback((requestError: unknown, fallback: string) => {
    if (isAuthenticationError(requestError)) {
      setAuthRequired(true);
      setAuthRejected(true);
      setIsEditingAuthToken(true);
      setError('AI credentials were rejected. Enter the current AI token and try again.');
      return;
    }
    setError(requestError instanceof Error ? requestError.message : fallback);
  }, []);
  hasMessagesRef.current = messages.length > 0;
  scheduleYamlRef.current = scheduleYaml;
  useTabSwitchWarning(isStreaming || draft.trim().length > 0 || selectedAttachments.length > 0);

  useEffect(() => {
    // Reading the stored preferences here keeps the server-rendered markup stable.
    try {
      const stored = window.localStorage.getItem(AI_STORAGE_KEY);
      if (stored !== null) {
        const preferences = JSON.parse(stored) as Partial<AiPreferences>;
        if (typeof preferences.showReasoning === 'boolean') setShowReasoning(preferences.showReasoning);
        if (typeof preferences.showTools === 'boolean') setShowTools(preferences.showTools);
      }
    } catch {
      // Unreadable storage keeps the defaults rather than blocking the page.
    }
    let endpoint = getAiBaseUrl();
    try {
      const storedEndpoint = window.localStorage.getItem(AI_SERVER_STORAGE_KEY);
      const normalizedEndpoint = storedEndpoint === '/ai' ? storedEndpoint : normalizeAiEndpoint(storedEndpoint ?? '');
      if (normalizedEndpoint) endpoint = normalizedEndpoint;
    } catch {
      // Unreadable storage keeps the configured default.
    }
    const storedConversation = readStoredConversation();
    if (storedConversation !== null) {
      endpoint = storedConversation.endpoint;
      setMessages(storedConversation.messages.map(message => (
        message.status === 'pending' ? { ...message, status: 'failed' as const } : message
      )));
      setProposalDiff(storedConversation.proposalDiff);
      setSessionRetentionSeconds(storedConversation.retentionSeconds);
      lastSessionEventIdRef.current = storedConversation.sessionEventId ?? 0;
      setActiveOptimization(storedConversation.activeOptimization ?? null);
      syncedScheduleRef.current = storedConversation.syncedSchedule;
      sessionEndpointRef.current = storedConversation.endpoint;
      if (storedConversation.expiresAt <= Date.now()) {
        window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
        setConversationUnavailable(true);
        setSessionNotice(
          `This chat expired after ${retentionLabel(storedConversation.retentionSeconds)} of inactivity. Start a new chat to continue.`,
        );
      } else {
        sessionIdRef.current = storedConversation.sessionId;
        setActiveSessionId(storedConversation.sessionId);
        setSessionExpiresAt(storedConversation.expiresAt);
      }
    }
    const storedTokens = readStoredAuthTokens();
    const storedToken = storedTokens[endpoint] ?? null;
    authTokensRef.current = storedTokens;
    setAiEndpoint(endpoint);
    setAuthToken(storedToken);
    setRememberAuthToken(storedToken !== null);
    setIsClientReady(true);
    const firefoxVersionMatch = navigator.userAgent.match(/Firefox\/(\d+)/);
    const detectedFirefoxVersion = firefoxVersionMatch === null
      ? null
      : Number.parseInt(firefoxVersionMatch[1], 10);
    const hasSpeechRecognition = Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
    setFirefoxVersion(detectedFirefoxVersion);
    setSpeechSupported(hasSpeechRecognition && (
      detectedFirefoxVersion === null || detectedFirefoxVersion >= FIREFOX_ON_DEVICE_SPEECH_VERSION
    ));
  }, []);

  const rememberPreferences = (preferences: AiPreferences) => {
    setShowReasoning(preferences.showReasoning);
    setShowTools(preferences.showTools);
    try {
      window.localStorage.setItem(AI_STORAGE_KEY, JSON.stringify(preferences));
    } catch {
      // A browser that refuses storage still applies the choice for this visit.
    }
  };

  useEffect(() => {
    if (!isClientReady) return;
    const capabilitiesController = new AbortController();
    setServerStatus('checking');
    setCapabilitiesError(null);
    getCapabilities(capabilitiesController.signal, aiEndpoint)
      .then(capabilities => {
        setServerStatus('online');
        setAuthRequired(capabilities.auth?.required ?? false);
        setFileCapability(capabilities.file_attachments);
        setSessionRetentionSeconds(
          capabilities.session_retention_seconds ?? DEFAULT_SESSION_RETENTION_SECONDS,
        );
      })
      .catch((capabilityError: unknown) => {
        if (!capabilitiesController.signal.aborted) {
          const unauthorized = isAuthenticationError(capabilityError);
          setServerStatus(unauthorized ? 'unauthorized' : 'offline');
          if (unauthorized) setAuthRequired(true);
          setCapabilitiesError(
            `Could not load AI capabilities from ${aiEndpoint}. Check that the AI backend is reachable from this browser.`,
          );
        }
      });
    return () => capabilitiesController.abort();
  }, [aiEndpoint, isClientReady]);

  useEffect(() => {
    if (!isClientReady) return;
    if (conversationStorageTimerRef.current !== null) {
      clearTimeout(conversationStorageTimerRef.current);
    }
    const persistConversation = () => {
      try {
        if (
          activeSessionId === null
          || sessionExpiresAt === null
          || sessionIdRef.current !== activeSessionId
        ) {
          window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
          return;
        }
        const stored: StoredChatConversation = {
          sessionId: activeSessionId,
          endpoint: sessionEndpointRef.current ?? aiEndpoint,
          expiresAt: sessionExpiresAt,
          retentionSeconds: sessionRetentionSeconds,
          messages,
          syncedSchedule: syncedScheduleRef.current ?? scheduleYaml,
          proposalDiff,
          sessionEventId: lastSessionEventIdRef.current,
          activeOptimization,
        };
        window.sessionStorage.setItem(AI_CONVERSATION_STORAGE_KEY, JSON.stringify(stored));
      } catch {
        // The live conversation remains usable when tab storage is unavailable or full.
      }
    };
    persistConversationRef.current = persistConversation;
    const timer = setTimeout(persistConversation, 200);
    conversationStorageTimerRef.current = timer;
    return () => {
      clearTimeout(timer);
      if (conversationStorageTimerRef.current === timer) {
        conversationStorageTimerRef.current = null;
      }
    };
  }, [
    activeSessionId,
    activeOptimization,
    aiEndpoint,
    isClientReady,
    messages,
    proposalDiff,
    scheduleYaml,
    sessionExpiresAt,
    sessionRetentionSeconds,
  ]);

  useEffect(() => {
    const flushConversation = () => {
      if (conversationStorageTimerRef.current !== null) {
        clearTimeout(conversationStorageTimerRef.current);
        conversationStorageTimerRef.current = null;
      }
      persistConversationRef.current?.();
    };
    window.addEventListener('pagehide', flushConversation);
    return () => {
      window.removeEventListener('pagehide', flushConversation);
      flushConversation();
    };
  }, []);

  useEffect(() => {
    if (!isClientReady || activeSessionId === null || checkedSessionRef.current === activeSessionId) return;
    checkedSessionRef.current = activeSessionId;
    const endpoint = sessionEndpointRef.current ?? aiEndpoint;
    getSessionStatus(activeSessionId, authToken, endpoint)
      .then(expiresInSeconds => {
        setSessionExpiresAt(Date.now() + expiresInSeconds * 1000);
      })
      .catch((statusError: unknown) => {
        if (statusError instanceof AiHttpError && statusError.status === 404) {
          sessionEventsControllerRef.current?.abort();
          sessionEventsControllerRef.current = null;
          sessionIdRef.current = null;
          sessionEndpointRef.current = null;
          syncedScheduleRef.current = null;
          setActiveSessionId(null);
          setSessionExpiresAt(null);
          setProposalDiff(null);
          setActiveOptimization(null);
          setConversationUnavailable(true);
          setSessionNotice('This chat is no longer available on the AI server. Start a new chat to continue.');
          window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
        } else {
          checkedSessionRef.current = null;
          reportRequestError(statusError, 'The stored AI chat could not be checked.');
        }
      });
  }, [activeSessionId, aiEndpoint, authToken, isClientReady, reportRequestError]);

  useEffect(() => {
    if (activeSessionId === null || sessionExpiresAt === null) return;
    const delay = sessionExpiresAt - Date.now();
    if (delay <= 0) {
      sessionEventsControllerRef.current?.abort();
      sessionEventsControllerRef.current = null;
      sessionIdRef.current = null;
      setActiveSessionId(null);
      setSessionExpiresAt(null);
      setActiveOptimization(null);
      setConversationUnavailable(true);
      setSessionNotice(
        `This chat expired after ${retentionLabel(sessionRetentionSeconds)} of inactivity. Start a new chat to continue.`,
      );
      window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
      return;
    }
    const timeout = window.setTimeout(() => {
      sessionEventsControllerRef.current?.abort();
      sessionEventsControllerRef.current = null;
      sessionIdRef.current = null;
      setActiveSessionId(null);
      setSessionExpiresAt(null);
      setActiveOptimization(null);
      setConversationUnavailable(true);
      setSessionNotice(
        `This chat expired after ${retentionLabel(sessionRetentionSeconds)} of inactivity. Start a new chat to continue.`,
      );
      window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
    }, delay);
    return () => window.clearTimeout(timeout);
  }, [activeSessionId, sessionExpiresAt, sessionRetentionSeconds]);

  useEffect(() => () => {
      abortControllerRef.current?.abort();
      sessionEventsControllerRef.current?.abort();
      speechRecognitionRef.current?.stop();
      selectedAttachmentsRef.current.forEach(attachment => {
        if (attachment.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
      });
      if (optimizationDownloadUrlRef.current) URL.revokeObjectURL(optimizationDownloadUrlRef.current);
  }, []);

  useEffect(() => {
    selectedAttachmentsRef.current = selectedAttachments;
  }, [selectedAttachments]);

  useEffect(() => {
    const hasTransientInput = isStreaming || draft.trim().length > 0 || selectedAttachments.length > 0;
    if (!hasTransientInput) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => window.removeEventListener('beforeunload', warnBeforeUnload);
  }, [draft, isStreaming, selectedAttachments.length]);

  useEffect(() => {
    // Scroll events do not identify their source, so only user input may change the follow flag.
    let userScrollPending = false;
    let pointerScrollActive = false;
    let clearUserScrollTimer: ReturnType<typeof setTimeout> | undefined;
    const setFollowPageBottom = (followPageBottom: boolean) => {
      followPageBottomRef.current = followPageBottom;
      setShowScrollToBottom(hasMessagesRef.current && !followPageBottom);
    };
    const armUserScroll = () => {
      userScrollPending = true;
      clearTimeout(clearUserScrollTimer);
      clearUserScrollTimer = setTimeout(() => {
        userScrollPending = false;
      }, 200);
    };
    const handleScroll = () => {
      if (!userScrollPending && !pointerScrollActive) return;
      const pageBottom = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      setFollowPageBottom(window.scrollY >= pageBottom);
    };
    const handleScrollEnd = () => {
      if (!pointerScrollActive) userScrollPending = false;
    };
    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) armUserScroll();
    };
    const handlePointerDown = () => {
      pointerScrollActive = true;
    };
    const handlePointerUp = () => {
      pointerScrollActive = false;
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      const isEditable = target instanceof HTMLElement
        && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName));
      if (!isEditable && ['ArrowDown', 'ArrowUp', 'End', 'Home', 'PageDown', 'PageUp', ' '].includes(event.key)) {
        armUserScroll();
      }
    };

    const pageBottom = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    setFollowPageBottom(window.scrollY >= pageBottom);
    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('scrollend', handleScrollEnd, { passive: true });
    window.addEventListener('wheel', handleWheel, { passive: true });
    window.addEventListener('touchmove', armUserScroll, { passive: true });
    window.addEventListener('pointerdown', handlePointerDown, { passive: true });
    window.addEventListener('pointerup', handlePointerUp, { passive: true });
    window.addEventListener('pointercancel', handlePointerUp, { passive: true });
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      clearTimeout(clearUserScrollTimer);
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('scrollend', handleScrollEnd);
      window.removeEventListener('wheel', handleWheel);
      window.removeEventListener('touchmove', armUserScroll);
      window.removeEventListener('pointerdown', handlePointerDown);
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('pointercancel', handlePointerUp);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  useLayoutEffect(() => {
    if (followPageBottomRef.current) {
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
    }
  }, [messages]);

  useLayoutEffect(() => {
    const input = draftInputRef.current;
    if (input === null) return;
    input.style.height = 'auto';
    input.style.height = `${Math.min(Math.max(input.scrollHeight, 24), 160)}px`;
    input.style.overflowY = input.scrollHeight > 160 ? 'auto' : 'hidden';
  }, [draft]);

  const scrollToPageBottom = () => {
    followPageBottomRef.current = true;
    setShowScrollToBottom(false);
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
  };

  const saveAuthToken = (token: string, remember: boolean) => {
    setAuthToken(token);
    setRememberAuthToken(remember);
    setIsEditingAuthToken(false);
    setAuthRejected(false);
    setError(null);
    authTokensRef.current[aiEndpoint] = token;
    try {
      if (remember) {
        const storedTokens = readStoredAuthTokens();
        storedTokens[aiEndpoint] = token;
        persistAuthTokens(storedTokens);
      } else {
        const storedTokens = readStoredAuthTokens();
        delete storedTokens[aiEndpoint];
        persistAuthTokens(storedTokens);
      }
    } catch {
      // A browser that refuses storage still applies the token for this visit.
    }
  };

  const clearAuthToken = () => {
    setAuthToken(null);
    setRememberAuthToken(false);
    setIsEditingAuthToken(false);
    setAuthRejected(false);
    setError(null);
    delete authTokensRef.current[aiEndpoint];
    try {
      const storedTokens = readStoredAuthTokens();
      delete storedTokens[aiEndpoint];
      persistAuthTokens(storedTokens);
    } catch {
      // The in-memory token is still forgotten when storage is unavailable.
    }
  };

  const selectAiEndpoint = (requestedEndpoint: string) => {
    if (sessionIdRef.current !== null || messages.length > 0 || isStreaming) return;
    const endpoint = requestedEndpoint === '/ai' ? requestedEndpoint : normalizeAiEndpoint(requestedEndpoint);
    if (!endpoint) {
      setServerError('Enter a valid HTTP or HTTPS AI server URL.');
      return;
    }
    const token = authTokensRef.current[endpoint] ?? null;
    setAiEndpoint(endpoint);
    setAuthToken(token);
    setRememberAuthToken(readStoredAuthTokens()[endpoint] !== undefined);
    setAuthRequired(false);
    setAuthRejected(false);
    setFileCapability(DISABLED_FILE_CAPABILITY);
    setServerError(null);
    setCapabilitiesError(null);
    setIsEditingServer(false);
    try {
      window.localStorage.setItem(AI_SERVER_STORAGE_KEY, endpoint);
    } catch {
      // A browser that refuses storage still applies the server for this visit.
    }
  };

  const toggleServerEditor = () => {
    setIsEditingServer(previous => {
      if (!previous) setCustomEndpoint(aiEndpoint);
      return !previous;
    });
  };

  const renewSessionExpiration = () => {
    setSessionExpiresAt(Date.now() + sessionRetentionSeconds * 1000);
  };

  const markConversationUnavailable = (notice: string) => {
    queuedMessagesRef.current = [];
    sessionEventsControllerRef.current?.abort();
    sessionEventsControllerRef.current = null;
    lastSessionEventIdRef.current = 0;
    sessionIdRef.current = null;
    sessionEndpointRef.current = null;
    syncedScheduleRef.current = null;
    checkedSessionRef.current = null;
    setActiveSessionId(null);
    setSessionExpiresAt(null);
    setQueuedMessages([]);
    setActiveOptimization(null);
    setProposalDiff(null);
    setConversationUnavailable(true);
    setSessionNotice(notice);
    window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
  };

  const startNewConversation = () => {
    if (messages.length > 0 && !window.confirm('Start a new chat? The current transcript will be cleared.')) return;
    selectedAttachments.forEach(attachment => {
      if (attachment.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
    });
    if (optimizationDownloadUrlRef.current) URL.revokeObjectURL(optimizationDownloadUrlRef.current);
    optimizationDownloadUrlRef.current = null;
    sessionEventsControllerRef.current?.abort();
    sessionEventsControllerRef.current = null;
    lastSessionEventIdRef.current = 0;
    sessionIdRef.current = null;
    sessionEndpointRef.current = null;
    syncedScheduleRef.current = null;
    sandboxScheduleRef.current = null;
    checkedSessionRef.current = null;
    queuedMessagesRef.current = [];
    setActiveSessionId(null);
    setSessionExpiresAt(null);
    setMessages([]);
    setDraft('');
    setSelectedAttachments([]);
    setQueuedMessages([]);
    setActiveOptimization(null);
    setProposalDiff(null);
    setProposalNotice(null);
    setConversationUnavailable(false);
    setSessionNotice(null);
    setError(null);
    window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
  };

  const addAttachments = (files: File[]) => {
    if (files.length === 0) return;
    if (!fileCapability.enabled) {
      setError('File attachments are unavailable.');
      return;
    }
    if (selectedAttachments.length + files.length > fileCapability.max_files) {
      setError(`Attach at most ${fileCapability.max_files} files to one question.`);
      return;
    }
    if (files.some(file => file.size > fileCapability.max_bytes_per_file)) {
      const maxMegabytes = (fileCapability.max_bytes_per_file / 1_000_000).toLocaleString(undefined, {
        maximumFractionDigits: 1,
      });
      setError(`Each file must be ${maxMegabytes} MB or smaller.`);
      return;
    }

    setError(null);
    setSelectedAttachments(previous => [
      ...previous,
      ...files.map(file => ({
        file,
        kind: file.type.startsWith('image/') ? 'image' as const : 'file' as const,
        id: messageId(),
        ...(file.type.startsWith('image/') ? { previewUrl: URL.createObjectURL(file) } : {}),
      })),
    ]);
  };

  const selectAttachments = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    addAttachments(files);
  };

  const removeAttachment = (id: string) => {
    setSelectedAttachments(previous => {
      const removed = previous.find(attachment => attachment.id === id);
      if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl);
      return previous.filter(attachment => attachment.id !== id);
    });
  };

  const startBackgroundEventStream = useCallback((sessionId: string, endpoint: string) => {
    sessionEventsControllerRef.current?.abort();
    const controller = new AbortController();
    sessionEventsControllerRef.current = controller;
    const updateBackgroundMessage = (update: (message: ChatMessage) => ChatMessage) => {
      const activeId = backgroundAssistantIdRef.current;
      if (activeId === null) return;
      setMessages(previous => previous.map(message => message.id === activeId ? update(message) : message));
    };
    void streamSessionEvents(
      sessionId,
      {
        lastEventId: lastSessionEventIdRef.current,
        onEventId: id => { lastSessionEventIdRef.current = id; },
        onTurnStart: messageId => {
          backgroundAssistantIdRef.current = messageId;
          backgroundTurnActiveRef.current = true;
          sandboxScheduleRef.current = scheduleYamlRef.current;
          setIsStreaming(true);
          setMessages(previous => previous.some(message => message.id === messageId) ? previous : [
            ...previous,
            {
              id: messageId,
              role: 'assistant',
              content: '',
              status: 'pending',
              responseStartedAt: Date.now(),
            },
          ]);
        },
        onDelta: text => updateBackgroundMessage(message => ({
          ...message,
          content: message.content + text,
          activity: appendResponseActivity(message.activity ?? [], text),
        })),
        onReasoning: text => updateBackgroundMessage(message => {
          const activity = message.activity ?? [];
          const last = activity[activity.length - 1];
          if (last?.kind === 'reasoning') {
            return { ...message, activity: [...activity.slice(0, -1), { ...last, text: last.text + text }] };
          }
          return { ...message, activity: [...activity, { kind: 'reasoning', text }] };
        }),
        onToolStart: activity => updateBackgroundMessage(message => ({
          ...message,
          activity: [
            ...(message.activity ?? []),
            { kind: 'tool' as const, ...activity, result: '', ok: true, state: 'running' as const },
          ],
        })),
        onTool: activity => updateBackgroundMessage(message => ({
          ...message,
          activity: finishToolActivity(message.activity ?? [], activity),
        })),
        onScheduleChange: candidate => {
          const before = sandboxScheduleRef.current ?? scheduleYamlRef.current;
          sandboxScheduleRef.current = candidate;
          updateBackgroundMessage(message => ({
            ...message,
            activity: [
              ...(message.activity ?? []),
              { kind: 'schedule-change' as const, before, after: candidate },
            ],
          }));
        },
        onProposal: diff => setProposalDiff(diff),
        onOptimization: activity => {
          if (!activity.terminal) {
            setActiveOptimization(activity);
            return;
          }
          setActiveOptimization(current => current?.jobId === activity.jobId ? null : current);
          const content = activity.state === 'completed'
            ? activity.downloadable
              ? 'Optimization finished. Download the optimized schedule to review it.'
              : 'Optimization finished, but no result workbook is available to download.'
            : `Optimization ended with status: ${activity.state}.`;
          setMessages(previous => previous.some(message => message.id === `optimizer-${activity.jobId}`)
            ? previous
            : [
              ...previous,
              {
                id: `optimizer-${activity.jobId}`,
                role: 'optimizer',
                content,
                optimizerJob: { jobId: activity.jobId, downloadable: activity.downloadable },
              },
            ]);
        },
        onDone: () => {
          updateBackgroundMessage(message => ({
            ...message,
            status: undefined,
            responseCompletedAt: Date.now(),
          }));
          backgroundAssistantIdRef.current = null;
          backgroundTurnActiveRef.current = false;
          setIsStreaming(false);
        },
        onStopped: () => {
          updateBackgroundMessage(message => ({
            ...message,
            content: message.content || 'Stopped.',
            status: undefined,
            responseCompletedAt: Date.now(),
            activity: message.content
              ? interruptRunningTools(message.activity ?? [])
              : [...interruptRunningTools(message.activity ?? []), { kind: 'response', text: 'Stopped.' }],
          }));
          backgroundAssistantIdRef.current = null;
          backgroundTurnActiveRef.current = false;
          setIsStreaming(false);
          setIsStopping(false);
        },
        onError: message => {
          updateBackgroundMessage(entry => ({
            ...entry,
            content: entry.content || message,
            status: 'failed',
            responseCompletedAt: Date.now(),
            activity: interruptRunningTools(entry.activity ?? []),
          }));
          backgroundAssistantIdRef.current = null;
          backgroundTurnActiveRef.current = false;
          setIsStreaming(false);
          setError(message);
        },
      },
      controller.signal,
      authToken,
      endpoint,
    ).catch(streamError => {
      if (!controller.signal.aborted) {
        reportRequestError(streamError, 'The background AI event stream disconnected.');
      }
    });
  }, [authToken, reportRequestError]);

  useEffect(() => {
    if (!isClientReady || activeSessionId === null || conversationUnavailable) return;
    if (sessionEventsControllerRef.current === null) {
      startBackgroundEventStream(activeSessionId, sessionEndpointRef.current ?? aiEndpoint);
    }
  }, [activeSessionId, aiEndpoint, conversationUnavailable, isClientReady, startBackgroundEventStream]);

  const sendRequest = async (
    question: string,
    attachmentsForMessage: SelectedAttachment[],
    clearComposer: boolean,
  ) => {
    if (!question || isStreaming || conversationUnavailable || (authRequired && authToken === null)) return;

    const userMessage: ChatMessage = {
      id: messageId(),
      role: 'user',
      content: question,
      attachmentNames: attachmentsForMessage.map(attachment => attachment.file.name),
    };
    let activeAssistantId = messageId();
    let activeAssistantHasOutput = false;
    let activeQuestion = question;
    let activeQuestionRequiresAttachments = attachmentsForMessage.length > 0;
    const responseStartedAt = Date.now();
    followPageBottomRef.current = true;
    setShowScrollToBottom(false);
    setMessages(previous => [
      ...previous,
      userMessage,
      { id: activeAssistantId, role: 'assistant', content: '', status: 'pending', responseStartedAt },
    ]);
    if (clearComposer) {
      setDraft('');
      attachmentsForMessage.forEach(attachment => {
        if (attachment.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
      });
      setSelectedAttachments([]);
    }
    setError(null);
    setProposalDiff(null);
    setProposalNotice(null);
    setIsStreaming(true);
    sandboxScheduleRef.current = scheduleYaml;
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      let sessionId = sessionIdRef.current;
      const sessionEndpoint = sessionEndpointRef.current ?? aiEndpoint;
      if (sessionId === null) {
        sessionId = await createSession(scheduleYaml, authToken, sessionEndpoint);
        sessionIdRef.current = sessionId;
        sessionEndpointRef.current = sessionEndpoint;
        startBackgroundEventStream(sessionId, sessionEndpoint);
        checkedSessionRef.current = sessionId;
        setActiveSessionId(sessionId);
        setConversationUnavailable(false);
        setSessionNotice(null);
      } else if (syncedScheduleRef.current !== scheduleYaml) {
        // The schedule can change elsewhere in the app between questions.
        await updateSessionSchedule(sessionId, scheduleYaml, authToken, sessionEndpoint);
      }
      syncedScheduleRef.current = scheduleYaml;
      renewSessionExpiration();
      await streamMessage(
        sessionId,
        question,
        {
          onDelta: text => {
            if (text) {
              activeAssistantHasOutput = true;
              setSteeringAssistantId(null);
            }
            setMessages(previous => previous.map(message => (
              message.id === activeAssistantId
                ? {
                  ...message,
                  content: message.content + text,
                  activity: appendResponseActivity(message.activity ?? [], text),
                }
                : message
            )));
          },
          onReasoning: text => {
            if (text) {
              activeAssistantHasOutput = true;
              setSteeringAssistantId(null);
            }
            setMessages(previous => previous.map(message => {
              if (message.id !== activeAssistantId) return message;
              const activity = message.activity ?? [];
              const last = activity[activity.length - 1];
              // Consecutive reasoning belongs to one entry, so the order of work stays readable.
              if (last?.kind === 'reasoning') {
                return { ...message, activity: [...activity.slice(0, -1), { ...last, text: last.text + text }] };
              }
              return { ...message, activity: [...activity, { kind: 'reasoning', text }] };
            }));
          },
          onToolStart: activity => {
            activeAssistantHasOutput = true;
            setSteeringAssistantId(null);
            setMessages(previous => previous.map(message => (
              message.id === activeAssistantId
                ? {
                  ...message,
                  activity: [
                    ...(message.activity ?? []),
                    { kind: 'tool' as const, ...activity, result: '', ok: true, state: 'running' as const },
                  ],
                }
                : message
            )));
          },
          onTool: activity => setMessages(previous => previous.map(message => {
            if (message.id !== activeAssistantId) return message;
            return { ...message, activity: finishToolActivity(message.activity ?? [], activity) };
          })),
          onSteering: (queuedId, queuedMessage) => {
            queuedMessagesRef.current = queuedMessagesRef.current.filter(message => message.id !== queuedId);
            setQueuedMessages(queuedMessagesRef.current);
            const steeringStartedAt = Date.now();
            if (activeAssistantHasOutput) {
              const completedAssistantId = activeAssistantId;
              const nextAssistantId = messageId();
              setMessages(previous => [
                ...previous.map(message => (
                  message.id === completedAssistantId
                    ? { ...message, status: undefined, responseCompletedAt: steeringStartedAt }
                    : message
                )),
                { id: queuedId, role: 'user', content: queuedMessage },
                {
                  id: nextAssistantId,
                  role: 'assistant',
                  content: '',
                  status: 'pending',
                  responseStartedAt: steeringStartedAt,
                },
              ]);
              activeAssistantId = nextAssistantId;
              setSteeringAssistantId(nextAssistantId);
              activeAssistantHasOutput = false;
            } else {
              const pendingAssistantId = activeAssistantId;
              setMessages(previous => {
                const pendingIndex = previous.findIndex(message => message.id === pendingAssistantId);
                if (pendingIndex < 0) return [...previous, { id: queuedId, role: 'user', content: queuedMessage }];
                return [
                  ...previous.slice(0, pendingIndex),
                  { id: queuedId, role: 'user', content: queuedMessage },
                  ...previous.slice(pendingIndex),
                ];
              });
              setSteeringAssistantId(pendingAssistantId);
            }
            activeQuestion = queuedMessage;
            activeQuestionRequiresAttachments = false;
          },
          onScheduleChange: candidate => {
            const before = sandboxScheduleRef.current ?? scheduleYaml;
            sandboxScheduleRef.current = candidate;
            setMessages(previous => previous.map(message => (
              message.id === activeAssistantId
                ? {
                  ...message,
                  activity: [
                    ...(message.activity ?? []),
                    { kind: 'schedule-change' as const, before, after: candidate },
                  ],
                }
                : message
            )));
          },
          onProposal: diff => setProposalDiff(diff),
        },
        controller.signal,
        authToken,
        {
          files: attachmentsForMessage.map(attachment => attachment.file),
        },
        sessionEndpoint,
      );
      setMessages(previous => previous.map(message => (
        message.id === activeAssistantId
          ? { ...message, status: undefined, responseCompletedAt: Date.now() }
          : message
      )));
    } catch (streamError) {
      const staleTurnMessage = streamError instanceof AiStaleTurnError ? streamError.message : null;
      setMessages(previous => previous.map(message => {
        if (message.id !== activeAssistantId) return message;
        if (controller.signal.aborted) {
          return {
            ...message,
            content: message.content || 'Stopped.',
            status: undefined,
            responseCompletedAt: Date.now(),
            activity: message.content
              ? interruptRunningTools(message.activity ?? [])
              : [...interruptRunningTools(message.activity ?? []), { kind: 'response', text: 'Stopped.' }],
          };
        }
        return {
          ...message,
          content: staleTurnMessage ?? message.content,
          status: 'failed',
          responseCompletedAt: Date.now(),
          activity: staleTurnMessage === null
            ? interruptRunningTools(message.activity ?? [])
            : [{ kind: 'response' as const, text: staleTurnMessage }],
          retry: {
            question: activeQuestion,
            requiresAttachments: activeQuestionRequiresAttachments,
          },
        };
      }));
      if (streamError instanceof AiHttpError && streamError.status === 404) {
        markConversationUnavailable('This chat expired or is no longer available. Start a new chat to continue.');
      } else if (!controller.signal.aborted && staleTurnMessage === null) {
        reportRequestError(streamError, 'The AI request failed.');
      }
    } finally {
      setSteeringAssistantId(null);
      abortControllerRef.current = null;
      setIsStopping(false);
      setIsStreaming(backgroundTurnActiveRef.current);
      const nextMessage = queuedMessagesRef.current[0];
      if (nextMessage) {
        queuedMessagesRef.current = queuedMessagesRef.current.slice(1);
        setQueuedMessages(queuedMessagesRef.current);
        window.setTimeout(() => void sendRequest(nextMessage.content, [], false), 0);
      }
    }
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const question = draft.trim();
    if (!question || (authRequired && authToken === null)) return;
    if (isStreaming) {
      const queuedMessage = { id: messageId(), content: question };
      queuedMessagesRef.current = [...queuedMessagesRef.current, queuedMessage];
      setQueuedMessages(queuedMessagesRef.current);
      setDraft('');
      const sessionId = sessionIdRef.current;
      if (sessionId !== null) {
        try {
          await queueMessage(
            sessionId,
            queuedMessage.id,
            queuedMessage.content,
            authToken,
            sessionEndpointRef.current ?? aiEndpoint,
          );
          renewSessionExpiration();
        } catch (queueError) {
          const responseFinishing = typeof queueError === 'object'
            && queueError !== null
            && 'status' in queueError
            && queueError.status === 409;
          if (!responseFinishing) reportRequestError(queueError, 'The queued AI message could not be submitted yet.');
        }
      }
      return;
    }
    await sendRequest(question, selectedAttachments, true);
  };

  const retryMessage = (failedId: string, question: string) => {
    if (!question || isStreaming || (authRequired && authToken === null)) return;
    // The retried turn replaces the failed pair, so the question is not repeated.
    setMessages(previous => {
      const failedIndex = previous.findIndex(message => message.id === failedId);
      if (failedIndex < 0) return previous;
      const start = previous[failedIndex - 1]?.role === 'user' ? failedIndex - 1 : failedIndex;
      return [...previous.slice(0, start), ...previous.slice(failedIndex + 1)];
    });
    void sendRequest(question, [], false);
  };

  const prepareAttachmentRetry = (question: string) => {
    setDraft(question);
    setError(null);
  };

  const stop = () => {
    if (isStopping) return;
    setIsStopping(true);
    queuedMessagesRef.current = [];
    setQueuedMessages([]);
    abortControllerRef.current?.abort();
    const sessionId = sessionIdRef.current;
    if (sessionId === null) {
      setIsStopping(false);
      return;
    }
    void stopSession(sessionId, authToken, sessionEndpointRef.current ?? aiEndpoint)
      .catch(stopError => reportRequestError(stopError, 'The AI response could not be stopped.'))
      .finally(() => setIsStopping(false));
  };

  const downloadOptimizationResult = async (jobId: string) => {
    const sessionId = sessionIdRef.current;
    if (sessionId === null || downloadingOptimizationId !== null) return;
    setDownloadingOptimizationId(jobId);
    try {
      const blob = await downloadOptimization(
        sessionId,
        jobId,
        authToken,
        sessionEndpointRef.current ?? aiEndpoint,
      );
      const downloadUrl = URL.createObjectURL(blob);
      if (optimizationDownloadUrlRef.current) URL.revokeObjectURL(optimizationDownloadUrlRef.current);
      optimizationDownloadUrlRef.current = downloadUrl;
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `optimized-schedule-${jobId.slice(-8)}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (downloadError) {
      reportRequestError(downloadError, 'The optimized schedule could not be downloaded.');
    } finally {
      setDownloadingOptimizationId(null);
    }
  };
  const toggleDictation = () => {
    if (isListening) {
      speechRecognitionRef.current?.stop();
      return;
    }
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    if (firefoxVersion !== null && 'processLocally' in recognition) recognition.processLocally = true;
    if (speechLanguage) recognition.lang = speechLanguage;
    const originalDraft = draft.trimEnd();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = event => {
      // Continuous recognition reports one entry per utterance, and browsers differ on
      // whether a transcript carries its own leading space.
      const transcript = Array.from({ length: event.results.length }, (_, index) => (
        event.results[index][0]?.transcript ?? ''
      )).join(' ').replace(/\s+/g, ' ').trim();
      setDraft(`${originalDraft}${originalDraft && transcript ? ' ' : ''}${transcript}`);
    };
    recognition.onend = () => {
      if (speechRecognitionRef.current === recognition) speechRecognitionRef.current = null;
      setIsListening(false);
    };
    recognition.onerror = event => {
      if (!BENIGN_SPEECH_ERRORS.has(event?.error ?? '')) {
        setError('Speech recognition stopped before it could transcribe audio.');
      }
      setIsListening(false);
    };
    speechRecognitionRef.current = recognition;
    setError(null);
    setIsListening(true);
    try {
      recognition.start();
    } catch {
      speechRecognitionRef.current = null;
      setIsListening(false);
      setError('Speech recognition could not start in this browser.');
    }
  };
  const credentialsMissing = authRequired && authToken === null;
  const composerUnavailable = credentialsMissing || conversationUnavailable;
  const attachmentPickerDisabled = isStreaming
    || composerUnavailable
    || !fileCapability.enabled
    || selectedAttachments.length >= fileCapability.max_files;
  const isFileDrag = (event: DragEvent<HTMLElement>) => event.dataTransfer.types.includes('Files');
  const enterAttachmentDropZone = (event: DragEvent<HTMLFormElement>) => {
    if (attachmentPickerDisabled || !isFileDrag(event)) return;
    event.preventDefault();
    composerDragDepthRef.current += 1;
    setIsDraggingFiles(true);
  };
  const dragOverAttachmentDropZone = (event: DragEvent<HTMLFormElement>) => {
    if (attachmentPickerDisabled || !isFileDrag(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  };
  const leaveAttachmentDropZone = (event: DragEvent<HTMLFormElement>) => {
    if (!isFileDrag(event)) return;
    composerDragDepthRef.current = Math.max(0, composerDragDepthRef.current - 1);
    if (composerDragDepthRef.current === 0) setIsDraggingFiles(false);
  };
  const dropAttachments = (event: DragEvent<HTMLFormElement>) => {
    if (!isFileDrag(event)) return;
    event.preventDefault();
    composerDragDepthRef.current = 0;
    setIsDraggingFiles(false);
    if (!attachmentPickerDisabled) addAttachments(Array.from(event.dataTransfer.files));
  };
  const serverLocked = sessionIdRef.current !== null || messages.length > 0;
  const backgroundRunningTool = messages.find(message => message.id === backgroundAssistantIdRef.current)
    ?.activity?.find(entry => entry.kind === 'tool' && entry.state === 'running');

  const applyProposal = async () => {
    const sessionId = sessionIdRef.current;
    if (sessionId === null || proposalDiff === null) return;
    setIsApplyingProposal(true);
    setError(null);
    try {
      const approvedYaml = await approveProposal(
        sessionId,
        scheduleYaml,
        authToken,
        sessionEndpointRef.current ?? aiEndpoint,
      );
      // One import call is one history entry, so undo reverts the whole proposal.
      loadFromYaml(yaml.load(approvedYaml));
      syncedScheduleRef.current = approvedYaml;
      renewSessionExpiration();
      setProposalDiff(null);
      setProposalNotice('The proposed schedule was applied. Undo reverts it in one step.');
    } catch (approveError) {
      reportRequestError(approveError, 'The proposal could not be applied.');
    } finally {
      setIsApplyingProposal(false);
    }
  };

  const discardProposal = async () => {
    const sessionId = sessionIdRef.current;
    setProposalDiff(null);
    setProposalNotice(null);
    if (sessionId === null) return;
    try {
      await rejectProposal(sessionId, authToken, sessionEndpointRef.current ?? aiEndpoint);
      renewSessionExpiration();
    } catch (rejectError) {
      if (isAuthenticationError(rejectError)) {
        reportRequestError(rejectError, 'The proposal could not be rejected.');
      }
    }
  };

  return (
    <main className="mx-auto flex min-h-[calc(100dvh-3.5rem)] max-w-5xl flex-col px-4 pb-36 pt-8 sm:px-6">
      <div className="mb-6">
        <div className="mb-2 flex items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-900">Schedule AI Chat</h1>
          <PageDocumentationLink href={DOCUMENTATION_URLS.experimentalAi} label="Experimental AI" />
          <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">
            Experimental
          </span>
          <span className="text-xs text-gray-400">
            Frontend{' '}
            <AppVersionText
              version={CURRENT_APP_VERSION}
              versionHref={GITHUB_TAGS_URL}
              versionClassName="hover:text-gray-600"
              commitClassName="hover:text-gray-600"
            />
          </span>
        </div>
        <p className="text-sm text-gray-600">
          Ask questions about the schedule currently open in this browser, or request a change. You can attach files for the assistant to inspect in its temporary workspace. Proposed changes are applied only after you approve them.
        </p>
        <p className="mt-2 max-w-3xl rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          This beta is API-key gated by default.{' '}
          <a
            className="font-medium underline"
            href={GITHUB_AI_BETA_ACCESS_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            Request beta access
          </a>
          . All AI chats are logged and are not currently anonymized. Chat data may be retained and processed for the development, evaluation, and improvement of this product and the AI provider&apos;s products.{' '}
          <a
            className="font-medium underline"
            href={GITHUB_PRIVACY_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            Privacy details
          </a>
          .
        </p>
        <p className="mt-2 text-xs font-medium text-gray-500">
          Current snapshot: {peopleData.items.length} people, {dateData.items.length} dates. Captured when you send the first question.
        </p>
        <p className="mt-1 text-xs text-gray-500">
          Chat sessions expire after {retentionLabel(sessionRetentionSeconds)} of inactivity. Each new message renews this period.
        </p>
        {sessionNotice && (
          <p className="mt-2 max-w-3xl rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" role="status">
            {sessionNotice}
          </p>
        )}
        <div className="mt-3 max-w-2xl rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${
              serverStatus === 'online'
                ? 'bg-green-500'
                : serverStatus === 'checking'
                  ? 'animate-pulse bg-gray-400'
                  : serverStatus === 'unauthorized'
                    ? 'bg-amber-500'
                    : 'bg-red-500'
            }`} aria-hidden="true" />
            <span className="font-medium text-gray-700">AI server:</span>
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-gray-600" title={aiEndpoint}>
              {aiEndpoint}
            </span>
            <span className="text-xs capitalize text-gray-500">{serverStatus}</span>
            <button
              type="button"
              onClick={toggleServerEditor}
              disabled={isStreaming || serverLocked}
              title={serverLocked ? 'The AI server is locked for this conversation.' : undefined}
              className="rounded border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:bg-gray-100 disabled:text-gray-400"
            >
              {isEditingServer ? 'Close' : 'Change'}
            </button>
          </div>
          {serverLocked && (
            <p className="mt-1 text-xs text-gray-500">This server is locked for the current conversation.</p>
          )}
          {!isOfficialAiEndpoint(aiEndpoint) && (
            <p className="mt-1 text-xs text-amber-700">
              This server is unofficially hosted. Privacy and data retention practices may vary.
            </p>
          )}
          {isEditingServer && !serverLocked && (
            <form
              className="mt-3 space-y-2 border-t border-gray-100 pt-3"
              onSubmit={(event) => {
                event.preventDefault();
                selectAiEndpoint(customEndpoint);
              }}
            >
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => selectAiEndpoint(PRODUCTION_AI_API_URL)}
                  className="rounded border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                >
                  Use hosted
                </button>
                <button
                  type="button"
                  onClick={() => selectAiEndpoint(LOCAL_AI_API_URL)}
                  className="rounded border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50"
                >
                  Use localhost
                </button>
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={customEndpoint}
                  onChange={event => setCustomEndpoint(event.target.value)}
                  aria-label="Custom AI server URL"
                  placeholder="https://ai.example.com"
                  spellCheck={false}
                  className="min-w-0 flex-1 rounded border border-gray-300 px-2 py-1 text-xs text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
                />
                <button
                  type="submit"
                  className="rounded border border-blue-600 bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-700"
                >
                  Use custom
                </button>
              </div>
              {serverError && <p className="text-xs text-red-700">{serverError}</p>}
            </form>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-gray-500">
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={showReasoning}
                onChange={event => rememberPreferences({ showReasoning: event.target.checked, showTools })}
                className="h-3 w-3 accent-gray-400"
              />
              Show reasoning
            </label>
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={showTools}
                onChange={event => rememberPreferences({ showReasoning, showTools: event.target.checked })}
                className="h-3 w-3 accent-gray-400"
              />
              Show tool activity
            </label>
          </div>
          {messages.length > 0 && (
            <div className="ml-auto flex items-center gap-2">
              <FiDownload aria-hidden="true" className="h-3.5 w-3.5" />
              <span>Export chat:</span>
              <button
                type="button"
                onClick={() => downloadChatExport('html', messages, sessionEndpointRef.current ?? aiEndpoint)}
                className="font-medium text-gray-700 underline underline-offset-2 hover:text-gray-900"
              >
                HTML
              </button>
              <button
                type="button"
                onClick={() => downloadChatExport('markdown', messages, sessionEndpointRef.current ?? aiEndpoint)}
                className="font-medium text-gray-700 underline underline-offset-2 hover:text-gray-900"
              >
                Markdown
              </button>
              <span aria-hidden="true">·</span>
              <button
                type="button"
                onClick={startNewConversation}
                disabled={isStreaming}
                className="font-medium text-red-700 underline underline-offset-2 hover:text-red-900 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Start new chat
              </button>
            </div>
          )}
        </div>
        {(authRequired || authToken !== null) && (
          <div className="mt-3 max-w-md rounded-lg border border-gray-200 bg-white px-3 py-2">
            <BackendTokenField
              endpoint="AI assistant"
              token={authToken}
              rememberToken={rememberAuthToken}
              isEditing={isEditingAuthToken}
              disabled={isStreaming}
              onEdit={() => setIsEditingAuthToken(true)}
              onCancel={() => setIsEditingAuthToken(false)}
              onSave={saveAuthToken}
              onClear={clearAuthToken}
            />
            {authRejected && !isEditingAuthToken && (
              <p className="mt-1 text-xs text-red-700">The credentials were rejected.</p>
            )}
          </div>
        )}
      </div>

      <section
        aria-label="Chat messages"
        aria-live="polite"
        className="mb-4 min-h-80 space-y-4 rounded-xl border border-gray-200 bg-gray-50 p-4"
      >
        {messages.length === 0 && (
          <div className="flex min-h-72 items-center justify-center text-center text-gray-500">
            <p>Try asking “Who is available on the first date?”</p>
          </div>
        )}
        {messages.map(message => (
          <article
            key={message.id}
            className={`max-w-[85%] rounded-xl px-4 py-3 ${
              message.role === 'user'
                ? 'ml-auto bg-blue-600 text-white'
                : message.role === 'optimizer'
                  ? 'mr-auto border border-emerald-200 bg-emerald-50 text-emerald-950'
                  : 'mr-auto border border-gray-200 bg-white text-gray-900'
            }`}
          >
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide opacity-70">
              {message.role === 'user' ? 'You' : message.role === 'optimizer' ? 'Optimizer' : 'Assistant'}
            </p>
            {message.activity && (
              <AssistantActivity
                entries={message.activity.filter(entry => (
                  entry.kind === 'response' || (entry.kind === 'reasoning' ? showReasoning : showTools)
                ))}
              />
            )}
            {message.role === 'assistant' && !message.content && message.status === 'pending' ? (
              steeringAssistantId === message.id ? <p className="text-xs text-gray-500">Steering…</p> : <ThinkingIndicator />
            ) : message.role !== 'assistant' ? (
              <p className="whitespace-pre-wrap break-words">{message.content}</p>
            ) : null}
            {message.role === 'optimizer' && message.optimizerJob?.downloadable && (
              <button
                type="button"
                onClick={() => void downloadOptimizationResult(message.optimizerJob?.jobId ?? '')}
                disabled={downloadingOptimizationId !== null}
                className="mt-3 inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:bg-gray-400"
              >
                <FiDownload aria-hidden="true" className="h-4 w-4" />
                {downloadingOptimizationId === message.optimizerJob.jobId ? 'Downloading...' : 'Download result'}
              </button>
            )}
            {message.attachmentNames && message.attachmentNames.length > 0 && (
              <p className="mt-2 text-xs opacity-80">
                Attached: {message.attachmentNames.join(', ')}
              </p>
            )}
            {message.role === 'assistant'
              && message.responseStartedAt !== undefined
              && message.responseCompletedAt !== undefined && (
              <time
                dateTime={new Date(message.responseCompletedAt).toISOString()}
                className="mt-2 block text-[0.6875rem] text-gray-400"
              >
                {formatResponseTime(message.responseCompletedAt)} ·{' '}
                {formatResponseDuration(message.responseStartedAt, message.responseCompletedAt)}
              </time>
            )}
            {message.role === 'assistant' && message.status === 'failed' && message.retry && (
              <div className="mt-3 border-t border-red-200 pt-3 text-sm text-red-700">
                <p>This turn failed and was not saved to AI history.</p>
                {message.retry.requiresAttachments ? (
                  <>
                    <p className="mt-1 text-xs">Prepare the question, then reattach its files before sending.</p>
                    <button
                      type="button"
                      onClick={() => prepareAttachmentRetry(message.retry?.question ?? '')}
                      disabled={isStreaming}
                      className="mt-2 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Prepare retry
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => retryMessage(message.id, message.retry?.question ?? '')}
                    disabled={isStreaming}
                    className="mt-2 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Retry
                  </button>
                )}
              </div>
            )}
          </article>
        ))}
        {activeSessionId !== null && sessionExpiresAt !== null && (
          <p className="pt-1 text-center text-[0.6875rem] text-gray-400">
            Chat expires at{' '}
            <time
              dateTime={new Date(sessionExpiresAt).toISOString()}
              aria-label="Chat expiration"
              className="font-medium"
            >
              {formatSessionExpiration(sessionExpiresAt)}
            </time>
            {' '}· Each new message extends the chat for another {retentionLabel(sessionRetentionSeconds)}.
          </p>
        )}
      </section>

      {proposalDiff !== null && (
        <section
          aria-label="Proposed schedule change"
          className="mb-4 rounded-xl border border-blue-200 bg-blue-50 p-4"
        >
          <h2 className="text-sm font-semibold text-blue-900">Proposed schedule change</h2>
          <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-white p-3 text-xs text-gray-800">
            {proposalDiff}
          </pre>
          <p className="mt-2 text-xs text-blue-900">
            Approving replaces the current schedule in one step, which you can undo.
          </p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={applyProposal}
              disabled={isApplyingProposal}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
            >
              {isApplyingProposal ? 'Applying...' : 'Approve'}
            </button>
            <button
              type="button"
              onClick={discardProposal}
              disabled={isApplyingProposal}
              className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed"
            >
              Reject
            </button>
          </div>
        </section>
      )}

      {proposalNotice !== null && (
        <div role="status" className="mb-3 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {proposalNotice}
        </div>
      )}

      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {capabilitiesError && (
        <div role="alert" className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {capabilitiesError}
        </div>
      )}

      <form
        ref={composerRef}
        onSubmit={send}
        onDragEnter={enterAttachmentDropZone}
        onDragOver={dragOverAttachmentDropZone}
        onDragLeave={leaveAttachmentDropZone}
        onDrop={dropAttachments}
        aria-label="Message composer"
        className={`fixed inset-x-10 bottom-0 z-30 mx-auto max-w-5xl space-y-3 bg-gradient-to-t from-white via-white to-white/90 px-4 pb-4 pt-3 sm:px-6 ${
          isDraggingFiles ? 'rounded-xl ring-2 ring-blue-400 ring-offset-2' : ''
        }`}
      >
        {isDraggingFiles && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-xl border-2 border-dashed border-blue-500 bg-blue-50/90 text-sm font-semibold text-blue-800">
            Drop files to attach
          </div>
        )}
        {showScrollToBottom && (
          <button
            type="button"
            onClick={scrollToPageBottom}
            aria-label="Scroll to bottom"
            title="Scroll to bottom"
            className="absolute -top-10 left-1/2 -translate-x-1/2 rounded-full border border-gray-300 bg-white/95 p-2 text-gray-700 shadow-md backdrop-blur hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
          >
            <FiArrowDown aria-hidden="true" className="h-4 w-4" />
          </button>
        )}
        {activeOptimization !== null && (
          <div
            role="status"
            className="flex items-center gap-2 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-xs text-violet-900"
          >
            <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-violet-600" />
            <span>Optimizer running in the background · {activeOptimization.state}</span>
          </div>
        )}
        {backgroundRunningTool?.kind === 'tool' && (
          <div role="status" className="flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900">
            <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-blue-600" />
            <span>Background tool running · {backgroundRunningTool.name}</span>
          </div>
        )}
        {queuedMessages.length > 0 && (
          <div className="rounded-r-md border-l-2 border-gray-400 bg-gray-50 px-3 py-2 text-xs text-gray-700">
            <p className="font-semibold uppercase tracking-wide text-gray-500">Queued for steering</p>
            <div className="mt-1 space-y-1">
              {queuedMessages.map(message => (
                <p key={message.id} className="truncate">· {message.content}</p>
              ))}
            </div>
          </div>
        )}
        {selectedAttachments.length > 0 && (
          <div aria-label="Files attached to next message" className="flex flex-wrap gap-3 rounded-xl border border-gray-200 bg-white p-3">
            {selectedAttachments.map(attachment => (
              <div key={attachment.id} className="flex max-w-52 items-center gap-2 rounded-lg bg-gray-50 p-2">
                {attachment.previewUrl ? (
                  <Image
                    src={attachment.previewUrl}
                    alt={`Preview of ${attachment.file.name}`}
                    width={48}
                    height={48}
                    unoptimized
                    className="h-12 w-12 rounded-md object-cover"
                  />
                ) : (
                  <span className="flex h-12 w-12 items-center justify-center rounded-md bg-blue-50 text-xs font-semibold uppercase text-blue-700">
                    {fileExtension(attachment.file.name).slice(1)}
                  </span>
                )}
                <span className="min-w-0 flex-1 truncate text-xs text-gray-700">{attachment.file.name}</span>
                <button
                  type="button"
                  onClick={() => removeAttachment(attachment.id)}
                  aria-label={`Remove ${attachment.file.name}`}
                  className="rounded px-1.5 py-1 text-gray-500 hover:bg-gray-200 hover:text-gray-800"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex min-h-14 items-end gap-1 rounded-[1.75rem] border border-gray-300 bg-white p-2 shadow-sm transition focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-200">
          {fileCapability.enabled && (
            <label
              title="Attach files"
              className={`inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors ${
                attachmentPickerDisabled
                  ? 'cursor-not-allowed text-gray-300'
                  : 'cursor-pointer text-gray-700 hover:bg-gray-100'
              }`}
            >
              <input
                type="file"
                multiple
                disabled={attachmentPickerDisabled}
                onChange={selectAttachments}
                aria-label="Attach files"
                className="sr-only"
              />
              <FiPlus aria-hidden="true" className="h-6 w-6" />
            </label>
          )}
          <textarea
            ref={draftInputRef}
            value={draft}
            onChange={event => setDraft(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            disabled={!isClientReady || composerUnavailable}
            rows={1}
            maxLength={8000}
            aria-label="Ask about the current schedule"
            placeholder="Ask anything…"
            className="min-h-6 max-h-40 flex-1 resize-none bg-transparent px-2 py-2 text-base leading-6 text-gray-900 outline-none disabled:text-gray-400"
          />
          <div className="flex shrink-0 items-center gap-1">
            {isClientReady && firefoxVersion !== null && !speechSupported ? (
              <a
                href={firefoxVersion >= FIREFOX_ON_DEVICE_SPEECH_VERSION
                  ? FIREFOX_SPEECH_RECOGNITION_STATUS_URL
                  : FIREFOX_NIGHTLY_URL}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={firefoxVersion >= FIREFOX_ON_DEVICE_SPEECH_VERSION
                  ? 'Enable experimental dictation in Firefox'
                  : 'Firefox dictation compatibility'}
                className="group relative inline-flex h-10 w-10 items-center justify-center rounded-full text-amber-600 transition-colors hover:bg-amber-50 hover:text-amber-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
              >
                <FiMic aria-hidden="true" className="h-4 w-4" />
                <span className="pointer-events-none absolute bottom-10 right-0 z-10 hidden w-72 rounded-lg bg-gray-900 px-3 py-2 text-left text-xs font-normal leading-5 text-white shadow-lg group-hover:block group-focus-visible:block">
                  {firefoxVersion >= FIREFOX_ON_DEVICE_SPEECH_VERSION
                    ? 'Firefox dictation is experimental. In about:config, enable media.webspeech.recognition.enable, then reload this page.'
                    : 'Dictation is unavailable in this Firefox version. Try Firefox Nightly or another supported browser.'}
                </span>
              </a>
            ) : (
              <div className="relative">
                <button
                  type="button"
                  onClick={toggleDictation}
                  disabled={!isClientReady || composerUnavailable || !speechSupported}
                  aria-label={isListening ? 'Stop dictation' : 'Start dictation'}
                  aria-pressed={isListening}
                  title={speechSupported ? (isListening ? 'Stop dictation' : 'Dictate message') : 'Speech input is not supported by this browser'}
                  className={`inline-flex h-10 w-10 items-center justify-center rounded-full transition-colors disabled:cursor-not-allowed disabled:text-gray-300 ${
                    isListening ? 'bg-red-50 text-red-600' : 'text-gray-500 hover:bg-gray-100 hover:text-gray-800'
                  }`}
                >
                  <FiMic aria-hidden="true" className={`h-4 w-4 ${isListening ? 'animate-pulse' : ''}`} />
                </button>
                <span className="absolute -bottom-0.5 -right-0.5 h-4 w-4 rounded-full border border-gray-300 bg-white text-gray-600 shadow-sm focus-within:ring-2 focus-within:ring-blue-400">
                  <select
                    value={speechLanguage}
                    onChange={event => setSpeechLanguage(event.target.value)}
                    disabled={!isClientReady || composerUnavailable || !speechSupported || isListening}
                    aria-label="Dictation language"
                    title="Dictation language"
                    className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
                  >
                    {SPEECH_LANGUAGES.map(language => (
                      <option key={language.value} value={language.value}>{language.label}</option>
                    ))}
                  </select>
                  <FiChevronDown aria-hidden="true" className="pointer-events-none h-full w-full p-0.5" />
                </span>
              </div>
            )}
            {isStreaming ? (
              <>
                <button
                  type="submit"
                  disabled={!draft.trim()}
                  aria-label="Queue message"
                  title="Queue message"
                  className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
                >
                  <FiArrowUp aria-hidden="true" className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  onClick={stop}
                  disabled={isStopping}
                  aria-label="Stop"
                  title="Stop"
                  className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-gray-800 text-white transition-colors hover:bg-gray-900 disabled:cursor-wait disabled:bg-gray-500"
                >
                  <FiSquare aria-hidden="true" className="h-4 w-4 fill-current" />
                </button>
              </>
            ) : (
              <button
                type="submit"
                disabled={!isClientReady || composerUnavailable || !draft.trim()}
                aria-label="Send"
                title="Send"
                className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
              >
                <FiArrowUp aria-hidden="true" className="h-5 w-5" />
              </button>
            )}
          </div>
        </div>
      </form>
    </main>
  );
}
