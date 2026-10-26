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

import * as Sentry from '@sentry/nextjs';
import Image from 'next/image';
import { MobileDetails } from '@/components/MobileDetails';
import { ChatTranscriptView } from './ChatTranscriptView';
import { useAiChat } from './useAiChat';
import { ModelControls } from './ModelControls';
import { costLabel } from './costs';
import type { ModelSelection } from './aiClient';
import { readStoredConversation } from './chatConversation';
import { isAuthenticationError } from './aiClient';

import { ChangeEvent, DragEvent, FormEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { FiArrowDown, FiArrowUp, FiChevronDown, FiDownload, FiMic, FiPlus, FiSquare } from 'react-icons/fi';
import AppVersionText from '@/components/AppVersionText';
import BackendTokenField, { isValidBackendToken } from '@/components/BackendTokenField';
import type { OptimizationProgressPoint } from '@/components/OptimizationProgressChart';
import PageDocumentationLink from '@/components/PageDocumentationLink';
import { DOCUMENTATION_URLS, FIREFOX_NIGHTLY_URL, FIREFOX_SPEECH_RECOGNITION_STATUS_URL, GITHUB_AI_BETA_ACCESS_URL, GITHUB_PRIVACY_URL, GITHUB_TAGS_URL } from '@/constants/urls';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { isImeCompositionKeyEvent } from '@/utils/keyboardEvents';
import { clipboardHtmlToMarkdown } from '@/utils/clipboardMarkdown';
import { useTabSwitchWarning } from '@/utils/unsavedEditingState';
import { CURRENT_APP_VERSION, hasAppVersionMismatch } from '@/utils/version';
import { generateYamlFromState } from '@/utils/yamlGenerator';
import yaml from 'js-yaml';

import { retentionLabel } from './chatPresentation';

import { AiCapabilities, DEFAULT_SESSION_RETENTION_SECONDS, LOCAL_AI_API_URL, PRODUCTION_AI_API_URL, cancelOptimization, getChatExportUrl, downloadOptimization, downloadGeneratedZip, getAiBaseUrl, getCapabilities, getBackendVersion, isOfficialAiEndpoint, normalizeAiEndpoint } from './aiClient';

import { messageId } from './assistantEvents';

const AI_STORAGE_KEY = 'nurse-scheduling-ai-data';
const AI_AUTH_STORAGE_KEY = 'nurse-scheduling-ai-auth';
const AI_SERVER_STORAGE_KEY = 'nurse-scheduling-ai-server';
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
  showCosts: boolean;
  showModels: boolean;
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

const DISABLED_FILE_CAPABILITY: AiCapabilities['file_attachments'] = {
  enabled: false,
  max_files: 1,
  max_bytes_per_file: 1,
  max_bytes_per_session: 1,
};

// Phone keyboards have no Shift+Enter, so Enter adds a new line there. A tablet with a
// trackpad or mouse also reports a fine pointer and keeps Enter to send.
function isTouchOnlyPointer(): boolean {
  return Boolean(window.matchMedia?.('(pointer: coarse)').matches && !window.matchMedia('(any-pointer: fine)').matches);
}

// A module-level callback ref keeps the Sentry form attached across rerenders, so
// streaming output does not close an open form. React runs the returned cleanup.
function attachFeedbackForm(element: HTMLButtonElement | null) {
  return element ? Sentry.getFeedback()?.attachTo(element) : undefined;
}

function fileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf('.');
  return lastDot < 0 ? '' : filename.slice(lastDot).toLowerCase();
}

function OptimizationSparkline({ points }: { points: OptimizationProgressPoint[] }) {
  const firstTime = points[0].elapsedSeconds;
  const lastTime = points[points.length - 1].elapsedSeconds;
  let minimum = points[0].currentBestScore;
  let maximum = minimum;
  for (const point of points) {
    minimum = Math.min(minimum, point.currentBestScore);
    maximum = Math.max(maximum, point.currentBestScore);
  }
  const path = points.map((point, index) => {
    const x = lastTime === firstTime ? 2 + index * 108 / Math.max(points.length - 1, 1)
      : 2 + (point.elapsedSeconds - firstTime) * 108 / (lastTime - firstTime);
    const y = maximum === minimum ? 14 : 26 - (point.currentBestScore - minimum) * 24 / (maximum - minimum);
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg role="img" aria-label="Optimization score trend" viewBox="0 0 112 28" className="h-7 w-28 shrink-0">
      <polyline points={path} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

export default function ExperimentalAiPage() {
  const {
    dateData,
    peopleData,
    savedState,
    loadFromYaml,
    filterAutoGeneratedState,
  } = useSchedulingData();
  const scheduleYaml = useMemo(() => generateYamlFromState(savedState), [savedState]);

  const [backendVersion, setBackendVersion] = useState<string | undefined>();

  // A turn's first report has no provider call yet, so keep the latest token figures until a new call reports.

  const [draft, setDraft] = useState('');
  const [composerHeight, setComposerHeight] = useState(144);
  const [keyboardInset, setKeyboardInset] = useState(0);
  const [downloadingOptimizationId, setDownloadingOptimizationId] = useState<string | null>(null);
  const [cancellingOptimizationId, setCancellingOptimizationId] = useState<string | null>(null);
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
  const [modelSelectionEnabled, setModelSelectionEnabled] = useState(false);
  const [selection, setSelection] = useState<ModelSelection>();
  const [savedChatExportEnabled, setSavedChatExportEnabled] = useState(false);
  const [isExportingChat, setIsExportingChat] = useState(false);
  const [chatExportNotice, setChatExportNotice] = useState<string | null>(null);
  const chatExportFrameRef = useRef<HTMLIFrameElement | null>(null);
  const [fileCapability, setFileCapability] = useState(DISABLED_FILE_CAPABILITY);
  const [selectedAttachments, setSelectedAttachments] = useState<SelectedAttachment[]>([]);
  const [isDraggingFiles, setIsDraggingFiles] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [firefoxVersion, setFirefoxVersion] = useState<number | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [speechLanguage, setSpeechLanguage] = useState('');
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [showScrollToTop, setShowScrollToTop] = useState(false);
  const [showReasoning, setShowReasoning] = useState(true);
  const [showTools, setShowTools] = useState(true);
  const [showCosts, setShowCosts] = useState(true);
  const [showModels, setShowModels] = useState(true);
  const authTokensRef = useRef<Record<string, string>>({});
  const selectedAttachmentsRef = useRef<SelectedAttachment[]>([]);
  const followPageBottomRef = useRef(true);
  const hasMessagesRef = useRef(false);
  const composerRef = useRef<HTMLFormElement | null>(null);
  const draftInputRef = useRef<HTMLTextAreaElement | null>(null);
  const composerDragDepthRef = useRef(0);
  const speechRecognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const optimizationDownloadUrlRef = useRef<string | null>(null);
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

  const resetChatUi = useCallback(() => {
    setDownloadingOptimizationId(null);
    setCancellingOptimizationId(null);
    setIsExportingChat(false);
    setChatExportNotice(null);
    chatExportFrameRef.current?.remove();
    chatExportFrameRef.current = null;
  }, []);
  const {
    messages, uploadedFiles, removingUploadId, removingDownloadId, contextUsage, costSummary, activeSessionId,
    sessionExpiresAt, sessionRetentionSeconds, conversationUnavailable, sessionNotice, trimmedHistoryCount,
    isStreaming, isStopping, isReconnecting, activeOptimization, queuedMessages, steeringAssistantId,
    setSessionRetentionSeconds, restoreConversation,
    captureSession, newConversation, submitMessage, stop, removeUploadedFile,
    removeGeneratedFiles, compactContext, isCompacting,
  } = useAiChat({
    scheduleYaml, aiEndpoint, authRequired, authToken, isClientReady, serverStatus, selection, modelSelectionEnabled,
    retainsUploads: fileCapability.retained ?? false, backendVersion, setError, reportRequestError,
    onReset: resetChatUi,
    onApplySchedule: appliedYaml => {
      const imported = loadFromYaml(yaml.load(appliedYaml));
      return generateYamlFromState(filterAutoGeneratedState(imported));
    },
    onSendStart: kind => {
      if (kind !== 'queue') {
        followPageBottomRef.current = true;
        setShowScrollToBottom(false);
      }
      if (kind !== 'retry') {
        setDraft('');
        draftInputRef.current?.focus({ preventScroll: true });
      }
      if (kind === 'send') {
        selectedAttachments.forEach(attachment => {
          if (attachment.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
        });
        setSelectedAttachments([]);
      }
    },
  });
  const send = async (event: FormEvent) => {
    event.preventDefault();
    if (!isClientReady || composerUnavailable) return;
    await submitMessage(draft.trim(), selectedAttachments.map(attachment => attachment.file));
  };
  useEffect(() => {
    hasMessagesRef.current = messages.length > 0;
  }, [messages.length]);

  useEffect(() => {
    // Reset the pending request when the server reports a different optimizer job.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCancellingOptimizationId(current => current === activeOptimization?.jobId ? current : null);
  }, [activeOptimization?.jobId]);

  useTabSwitchWarning(draft.trim().length > 0 || selectedAttachments.length > 0);

  useEffect(() => {
    // Reading the stored preferences here keeps the server-rendered markup stable.
    try {
      const stored = window.localStorage.getItem(AI_STORAGE_KEY);
      if (stored !== null) {
        const preferences = JSON.parse(stored) as Partial<AiPreferences>;
        // Restore browser preferences after hydration.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        if (typeof preferences.showReasoning === 'boolean') setShowReasoning(preferences.showReasoning);
        if (typeof preferences.showTools === 'boolean') setShowTools(preferences.showTools);
        if (typeof preferences.showCosts === 'boolean') setShowCosts(preferences.showCosts);
        if (typeof preferences.showModels === 'boolean') setShowModels(preferences.showModels);
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
      restoreConversation(storedConversation);
      setBackendVersion(storedConversation.backendVersion);
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
  }, [restoreConversation]);

  const rememberPreferences = (updates: Partial<AiPreferences>) => {
    const preferences = { showReasoning, showTools, showCosts, showModels, ...updates };
    setShowReasoning(preferences.showReasoning);
    setShowTools(preferences.showTools);
    setShowCosts(preferences.showCosts);
    setShowModels(preferences.showModels);
    try {
      window.localStorage.setItem(AI_STORAGE_KEY, JSON.stringify(preferences));
    } catch {
      // A browser that refuses storage still applies the choice for this visit.
    }
  };

  useEffect(() => {
    if (!isClientReady) return;
    const capabilitiesController = new AbortController();
    // Reset the displayed status before checking the selected external service.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setServerStatus('checking');
    setBackendVersion(undefined);
    setCapabilitiesError(null);
    getCapabilities(capabilitiesController.signal, aiEndpoint)
      .then(async capabilities => {
        if (capabilitiesController.signal.aborted) return;
        setServerStatus('online');
        setAuthRequired(capabilities.auth?.required ?? false);
        setModelSelectionEnabled(capabilities.model_selection === true);
        setFileCapability(capabilities.file_attachments);
        setSavedChatExportEnabled(capabilities.saved_chat_export === true);
        setSessionRetentionSeconds(
          capabilities.session_retention_seconds ?? DEFAULT_SESSION_RETENTION_SECONDS,
        );
        const version = capabilities.app_version ?? await getBackendVersion(capabilitiesController.signal, aiEndpoint);
        if (!capabilitiesController.signal.aborted) setBackendVersion(version);
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
  }, [aiEndpoint, isClientReady, setSessionRetentionSeconds]);

  useEffect(() => () => {
      speechRecognitionRef.current?.stop();
      selectedAttachmentsRef.current.forEach(attachment => {
        if (attachment.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
      });
      if (optimizationDownloadUrlRef.current) URL.revokeObjectURL(optimizationDownloadUrlRef.current);
      chatExportFrameRef.current?.remove();
  }, []);

  useEffect(() => {
    selectedAttachmentsRef.current = selectedAttachments;
  }, [selectedAttachments]);

  useEffect(() => {
    const hasTransientInput = draft.trim().length > 0 || selectedAttachments.length > 0;
    if (!hasTransientInput) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => window.removeEventListener('beforeunload', warnBeforeUnload);
  }, [draft, selectedAttachments.length]);

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
      setShowScrollToTop(window.scrollY > 128);
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
    // Initialize the scroll subscription from the current browser position.
    setFollowPageBottom(window.scrollY >= pageBottom);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setShowScrollToTop(window.scrollY > 128);
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

  useEffect(() => {
    const composer = composerRef.current;
    if (!composer || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => setComposerHeight(composer.getBoundingClientRect().height));
    observer.observe(composer);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const updateViewport = () => {
      const inputFocused = composerRef.current?.contains(document.activeElement);
      setKeyboardInset(inputFocused && viewport.scale === 1
        ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop)
        : 0);
    };
    viewport.addEventListener('resize', updateViewport);
    viewport.addEventListener('scroll', updateViewport);
    document.addEventListener('focusin', updateViewport);
    document.addEventListener('focusout', updateViewport);
    return () => {
      viewport.removeEventListener('resize', updateViewport);
      viewport.removeEventListener('scroll', updateViewport);
      document.removeEventListener('focusin', updateViewport);
      document.removeEventListener('focusout', updateViewport);
    };
  }, []);

  const scrollToPageBottom = () => {
    followPageBottomRef.current = true;
    setShowScrollToBottom(false);
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' });
  };

  const scrollToPageTop = () => {
    followPageBottomRef.current = false;
    setShowScrollToBottom(hasMessagesRef.current);
    setShowScrollToTop(false);
    window.scrollTo({ top: 0, behavior: 'instant' });
  };

  const saveAuthToken = (token: string, remember: boolean) => {
    if (token !== authToken) setSelection(undefined);
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
    if (activeSessionId !== null || messages.length > 0 || isStreaming) return;
    const endpoint = requestedEndpoint === '/ai' ? requestedEndpoint : normalizeAiEndpoint(requestedEndpoint);
    if (!endpoint) {
      setServerError('Enter a valid HTTP or HTTPS AI server URL.');
      return;
    }
    const token = authTokensRef.current[endpoint] ?? null;
    setAiEndpoint(endpoint);
    if (endpoint !== aiEndpoint) setSelection(undefined);
    setAuthToken(token);
    setRememberAuthToken(readStoredAuthTokens()[endpoint] !== undefined);
    setAuthRequired(false);
    setAuthRejected(false);
    setFileCapability(DISABLED_FILE_CAPABILITY);
    setBackendVersion(undefined);
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

  const startNewConversation = () => {
    if (messages.length > 0 && !window.confirm('Start a new chat? The current transcript will be cleared.')) return;
    selectedAttachments.forEach(attachment => {
      if (attachment.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
    });
    if (optimizationDownloadUrlRef.current) URL.revokeObjectURL(optimizationDownloadUrlRef.current);
    optimizationDownloadUrlRef.current = null;
    newConversation();
    setDraft('');
    setSelectedAttachments([]);
  };

  const addAttachments = (files: File[]) => {
    if (files.length === 0) return;
    if (!fileCapability.enabled) {
      setError('File attachments are unavailable.');
      return;
    }
    if (uploadedFiles.length + selectedAttachments.length + files.length > fileCapability.max_files) {
      setError(`Keep at most ${fileCapability.max_files} files in this chat. Remove unused uploads first.`);
      return;
    }
    const megabytes = (bytes: number) => (bytes / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 });
    const maxFileBytes = fileCapability.max_bytes_per_file;
    if (files.some(file => file.size > maxFileBytes)) {
      setError(`Each file must be ${megabytes(maxFileBytes)} MB or smaller.`);
      return;
    }

    const totalBytes = uploadedFiles.reduce((total, file) => total + file.bytes, 0)
      + selectedAttachments.reduce((total, attachment) => total + attachment.file.size, 0)
      + files.reduce((total, file) => total + file.size, 0);
    if (totalBytes > fileCapability.max_bytes_per_session) {
      setError(`Files in this chat must total ${megabytes(fileCapability.max_bytes_per_session)} MB or less. Remove unused uploads first.`);
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

  const downloadGeneratedFiles = async (downloadId: string) => {
    const session = captureSession();
    const sessionId = session?.id;
    if (!sessionId) return;
    try {
      const blob = await downloadGeneratedZip(sessionId, downloadId, authToken, session!.endpoint);
      const url = URL.createObjectURL(blob);
      if (optimizationDownloadUrlRef.current) URL.revokeObjectURL(optimizationDownloadUrlRef.current);
      optimizationDownloadUrlRef.current = url;
      const link = document.createElement('a');
      link.href = url;
      link.download = 'download.zip';
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (downloadError) {
      reportRequestError(downloadError, 'The generated files could not be downloaded.');
    }
  };

  const exportChat = async () => {
    if (isExportingChat || !savedChatExportEnabled) return;
    const session = captureSession();
    if (session === null) return;
    setIsExportingChat(true);
    setError(null);
    setChatExportNotice(null);
    try {
      const url = await getChatExportUrl(session.id, authToken, session.endpoint);
      if (!session.ownsConversation()) return;
      chatExportFrameRef.current?.remove();
      const frame = document.createElement('iframe');
      frame.hidden = true;
      frame.title = 'Chat export download';
      let initialized = false;
      const failed = () => {
        if (chatExportFrameRef.current !== frame || !session.ownsConversation()) return;
        setChatExportNotice(null);
        reportRequestError(new Error('The chat download could not start. Please try Export Chat again.'), 'The chat could not be exported.');
      };
      frame.onload = () => {
        if (!initialized) {
          initialized = true;
          frame.src = url;
        } else {
          // An attachment starts a native download. A loaded document is an error,
          // including errors from another origin whose body the browser cannot read.
          failed();
        }
      };
      frame.onerror = failed;
      frame.src = 'about:blank';
      chatExportFrameRef.current = frame;
      document.body.appendChild(frame);
      setChatExportNotice('Chat download requested. Check your browser’s downloads.');
    } catch (exportError) {
      if (session.ownsConversation()) reportRequestError(exportError, 'The chat could not be exported.');
    } finally {
      if (session.ownsConversation()) setIsExportingChat(false);
    }
  };

  const downloadOptimizationResult = async (jobId: string) => {
    const session = captureSession();
    const sessionId = session?.id;
    if (!sessionId || downloadingOptimizationId !== null) return;
    const ownsConversation = session!.ownsConversation;
    setDownloadingOptimizationId(jobId);
    try {
      const blob = await downloadOptimization(
        sessionId,
        jobId,
        authToken,
        session!.endpoint,
      );
      if (!ownsConversation()) return;
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
      if (ownsConversation()) reportRequestError(downloadError, 'The optimized schedule could not be downloaded.');
    } finally {
      if (ownsConversation()) setDownloadingOptimizationId(null);
    }
  };

  const cancelActiveOptimization = async () => {
    const session = captureSession();
    if (session === null || activeOptimization === null || cancellingOptimizationId !== null) return;
    const jobId = activeOptimization.jobId;
    setCancellingOptimizationId(jobId);
    try {
      await cancelOptimization(session.id, jobId, authToken, session.endpoint);
    } catch (cancelError) {
      if (session.ownsConversation()) {
        setCancellingOptimizationId(current => current === jobId ? null : current);
        reportRequestError(cancelError, 'The optimizer could not be cancelled.');
      }
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
  const composerUnavailable = isCompacting || credentialsMissing || conversationUnavailable || (modelSelectionEnabled && !selection);
  const attachmentPickerDisabled = isStreaming
    || composerUnavailable
    || !fileCapability.enabled
    || uploadedFiles.length + selectedAttachments.length >= fileCapability.max_files;
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
  const hasVersionMismatch = backendVersion !== undefined && hasAppVersionMismatch(CURRENT_APP_VERSION, backendVersion);
  const serverLocked = activeSessionId !== null || messages.length > 0;

  const tokenDescription = `${contextUsage?.estimated !== false ? 'Estimated current' : 'Current'} LLM context tokens / model context limit. Includes system instructions, tools, and conversation messages.`;
  const contextDescription = contextUsage?.usedTokens !== undefined
    ? tokenDescription
    : 'The AI server has not reported context tokens.';

  // The Session files panel is fixed on the right at xl, so the chat and composer reserve
  // equal space on both sides to stay centered without overlapping it.
  return (
    <main className={`mx-auto flex min-h-[calc(100dvh-3.5rem)] max-w-5xl min-w-0 flex-col px-2 pt-4 sm:px-6 sm:pt-8 ${fileCapability.retained ? 'xl:max-w-[min(64rem,calc(100vw-36rem))]' : ''}`} style={{ paddingBottom: composerHeight + keyboardInset + 56 }}>
      <div className="mb-6">
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h1 className="text-3xl font-bold text-gray-900">Schedule AI Chat</h1>
          <PageDocumentationLink href={DOCUMENTATION_URLS.experimentalAi} label="Experimental AI" />
          <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800">
            Experimental
          </span>
        </div>
        <p className="text-sm text-gray-600">
          Ask questions about the schedule currently open in this browser, or request a change. You can attach files for the assistant to inspect in its temporary workspace.
        </p>
        <p className="mt-2 max-w-3xl rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          When a response finishes, the assistant&apos;s valid schedule changes replace the schedule in this browser.
          Use Undo in the tab bar or Ctrl+Z (Cmd+Z) to undo them. This beta is API-key gated by default.{' '}
          <a
            className="font-medium underline"
            href={GITHUB_AI_BETA_ACCESS_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            Request beta access
          </a>
          . All AI chats are logged and are not currently anonymized. Chat data may be retained and processed for the development, evaluation, and improvement of this product and the AI provider&apos;s products. This chat is also stored unencrypted in this browser until it expires or you start a new chat.{' '}
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
        {trimmedHistoryCount > 0 && (
          <p className="mt-2 max-w-3xl rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" role="status">
            This conversation is long, so the {trimmedHistoryCount === 1 ? 'oldest message is' : `${trimmedHistoryCount} oldest messages are`}
            {' '}no longer sent to the assistant. The full transcript stays on this page.
          </p>
        )}
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
            <p className="mt-1 text-xs text-gray-500">This server is locked for the current conversation. Start a new chat to change servers.</p>
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
          {chatExportNotice && <span role="status">{chatExportNotice}</span>}
          {messages.length > 0 && (
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <FiDownload aria-hidden="true" className="h-3.5 w-3.5" />
              <button
                type="button"
                onClick={() => void exportChat()}
                disabled={isExportingChat || !savedChatExportEnabled}
                title={savedChatExportEnabled ? 'Download the complete chat and its files as a ZIP' : 'Chat export is unavailable on this server'}
                className="font-medium text-gray-700 underline underline-offset-2 hover:text-gray-900 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isExportingChat ? 'Preparing export…' : 'Export Chat'}
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
        <div className="mt-3">
          <MobileDetails label="Chat details and settings" openWhen={hasVersionMismatch}>
            <p className="mt-2 text-xs font-medium text-gray-500">
              Current snapshot: {peopleData.items.length} people, {dateData.items.length} dates. Captured when you send the first question.
            </p>
            <p className="mt-1 text-xs text-gray-500">
              Chat sessions expire after {retentionLabel(sessionRetentionSeconds)} of inactivity. Each new message renews this period.
            </p>
            <div className="flex flex-wrap gap-4">
              <label className="flex min-h-11 items-center gap-1.5 sm:min-h-0">
                <input
                  type="checkbox"
                  checked={showReasoning}
                  onChange={event => rememberPreferences({ showReasoning: event.target.checked })}
                  className="h-4 w-4 accent-gray-400 sm:h-3 sm:w-3"
                />
                Show reasoning
              </label>
              <label className="flex min-h-11 items-center gap-1.5 sm:min-h-0">
                <input
                  type="checkbox"
                  checked={showTools}
                  onChange={event => rememberPreferences({ showTools: event.target.checked })}
                  className="h-4 w-4 accent-gray-400 sm:h-3 sm:w-3"
                />
                Show tool activity
              </label>
              <label className="flex min-h-11 items-center gap-1.5 sm:min-h-0">
                <input type="checkbox" checked={showCosts}
                  onChange={event => rememberPreferences({ showCosts: event.target.checked })}
                  className="h-4 w-4 accent-gray-400 sm:h-3 sm:w-3" />
                Show turn costs
              </label>
              <label className="flex min-h-11 items-center gap-1.5 sm:min-h-0">
                <input type="checkbox" checked={showModels}
                  onChange={event => rememberPreferences({ showModels: event.target.checked })}
                  className="h-4 w-4 accent-gray-400 sm:h-3 sm:w-3" />
                Show models
              </label>
            </div>
            {process.env.NEXT_PUBLIC_DISABLE_SENTRY !== '1' && (
              // FeedbackWidget hides the floating Feedback button here on phones.
              <button
                type="button"
                ref={attachFeedbackForm}
                className="mt-1 flex min-h-11 items-center gap-1.5 text-xs text-blue-600 underline sm:hidden"
              >
                Send feedback
              </button>
            )}
            <div role="group" aria-label="AI versions" className={`mt-3 rounded-md border px-3 py-2 text-xs ${hasVersionMismatch ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-gray-200 bg-gray-50 text-gray-600'}`}>
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                <span>
                  Frontend{' '}
                  <AppVersionText
                    version={CURRENT_APP_VERSION}
                    versionHref={GITHUB_TAGS_URL}
                    versionClassName="hover:text-gray-600"
                    commitClassName="hover:text-gray-600"
                  />
                </span>
                <span>
                  Backend{' '}
                  <AppVersionText
                    version={backendVersion ?? 'unknown'}
                    versionHref={GITHUB_TAGS_URL}
                    versionClassName="hover:text-gray-600"
                    commitClassName="hover:text-gray-600"
                  />
                </span>
              </div>
              {hasVersionMismatch && (
                <p className="mt-1 font-medium text-amber-700">
                  Frontend and backend versions do not match. If nothing breaks, you can continue.
                </p>
              )}
            </div>
          </MobileDetails>
        </div>
      </div>

      {fileCapability.retained && (
        <aside aria-label="Session files" className="mb-4 rounded-xl border border-gray-200 bg-white p-4 xl:fixed xl:right-4 xl:top-24 xl:z-10 xl:max-h-[calc(100dvh-8rem)] xl:w-64 xl:overflow-y-auto">
          <MobileDetails label={`Uploaded files (${uploadedFiles.length})`} desktopCollapsible>
            <p className="mt-2 text-xs text-gray-600">Uploaded files are temporary and may disappear after a server restart without prior notice. Keep your original files. A repeated filename gets a number, such as ward (1).csv.</p>
            {uploadedFiles.length === 0 ? <p className="mt-3 text-sm text-gray-500">No uploaded files.</p> : (
              <ul className="mt-3 space-y-3">
                {uploadedFiles.map(file => (
                  <li key={file.id} className="flex items-start gap-2">
                    <span className="min-w-0 flex-1 break-words text-sm">{file.filename}<span className="block text-xs text-gray-500">{(file.bytes / 1000).toLocaleString()} KB</span></span>
                    <button type="button" aria-label={`Remove ${file.filename}`} disabled={isStreaming || removingUploadId !== null}
                      onClick={() => void removeUploadedFile(file.id)} className="rounded px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50">Remove</button>
                  </li>
                ))}
              </ul>
            )}
          </MobileDetails>
        </aside>
      )}

      <ChatTranscriptView
        messages={messages}
        showReasoning={showReasoning}
        showTools={showTools}
        showCosts={showCosts}
        showModels={showModels}
        steeringAssistantId={steeringAssistantId}
        conversationUnavailable={conversationUnavailable}
        removingDownloadId={removingDownloadId}
        downloadingOptimizationId={downloadingOptimizationId}
        downloadGeneratedFiles={downloadGeneratedFiles}
        removeGeneratedFiles={removeGeneratedFiles}
        downloadOptimizationResult={downloadOptimizationResult}
        activeSessionId={activeSessionId}
        sessionExpiresAt={sessionExpiresAt}
        sessionRetentionSeconds={sessionRetentionSeconds}
      />

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
        style={{ bottom: keyboardInset }}
        className={`fixed inset-x-2 bottom-0 sm:inset-x-10 z-30 mx-auto max-w-5xl space-y-3 ${fileCapability.retained ? 'xl:inset-x-72' : ''} bg-gradient-to-t from-white via-white to-white/90 px-2 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 sm:px-6 ${
          isDraggingFiles ? 'rounded-xl ring-2 ring-blue-400 ring-offset-2' : ''
        }`}
      >
        {isDraggingFiles && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-xl border-2 border-dashed border-blue-500 bg-blue-50/90 text-sm font-semibold text-blue-800">
            Drop files to attach
          </div>
        )}
        {(showScrollToTop || showScrollToBottom) && (
          <div role="group" aria-label="Chat navigation" className="absolute -top-10 left-1/2 flex -translate-x-1/2 gap-2">
            {showScrollToTop && (
              <button
                type="button"
                onClick={scrollToPageTop}
                aria-label="Back to top"
                title="Back to top"
                className="rounded-full border border-gray-300 bg-white/95 p-2 text-gray-700 shadow-md backdrop-blur hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
              >
                <FiArrowUp aria-hidden="true" className="h-4 w-4" />
              </button>
            )}
            {showScrollToBottom && (
              <button
                type="button"
                onClick={scrollToPageBottom}
                aria-label="Scroll to bottom"
                title="Scroll to bottom"
                className="rounded-full border border-gray-300 bg-white/95 p-2 text-gray-700 shadow-md backdrop-blur hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
              >
                <FiArrowDown aria-hidden="true" className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
        {isReconnecting && (
          <div role="status" className="rounded-xl border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-900">
            Reconnecting. Your AI response continues on the server.
          </div>
        )}
        {activeOptimization !== null && (
          <div
            role="status"
            className="flex flex-wrap items-center gap-2 rounded-xl border border-violet-200 bg-violet-50 px-3 py-2 text-xs text-violet-900"
          >
            <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-violet-600" />
            <span>Optimizer running in the background · {activeOptimization.state}</span>
            {activeOptimization.points.length > 0 && (
              <div className="ml-auto flex items-center gap-2 text-violet-800">
                <span className="font-semibold tabular-nums">
                  Score {new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(
                    activeOptimization.points.at(-1)!.currentBestScore
                  )}
                </span>
                {activeOptimization.points.length > 1 && <OptimizationSparkline points={activeOptimization.points} />}
              </div>
            )}
            <button
              type="button"
              onClick={() => void cancelActiveOptimization()}
              disabled={cancellingOptimizationId === activeOptimization.jobId || activeOptimization.state === 'cancelling' || isReconnecting}
              className="ml-auto inline-flex items-center gap-1 rounded-md border border-violet-300 px-2 py-1 font-medium hover:bg-violet-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 disabled:cursor-wait disabled:opacity-60"
            >
              <FiSquare aria-hidden="true" className="h-3 w-3" />
              {cancellingOptimizationId === activeOptimization.jobId || activeOptimization.state === 'cancelling' ? 'Cancelling optimizer…' : 'Cancel optimizer'}
            </button>
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
        {modelSelectionEnabled && serverStatus === 'online' && (!authRequired || authToken) && <ModelControls
          endpoint={aiEndpoint} token={authToken} sessionId={activeSessionId} disabled={conversationUnavailable}
          modelLocked={messages.some(message => message.request?.active)} runActive={isStreaming}
          onChange={setSelection}
        />}
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
            onPaste={event => {
              const markdown = clipboardHtmlToMarkdown(event.clipboardData.getData('text/html'));
              if (markdown === null) return;
              event.preventDefault();
              const input = event.currentTarget;
              const { selectionStart: start, selectionEnd: end, value } = input;
              const pasted = markdown;
              // Keep converted paste in the browser's text undo history.
              if (typeof document.execCommand === 'function' && document.execCommand('insertText', false, pasted)) return;
              setDraft(value.slice(0, start) + pasted + value.slice(end));
              requestAnimationFrame(() => input.setSelectionRange(start + pasted.length, start + pasted.length));
            }}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey && !isImeCompositionKeyEvent(event)
                && !isTouchOnlyPointer()) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            rows={1}
            aria-label="Ask about the current schedule"
            placeholder="Ask anything…"
            className="min-h-6 max-h-40 min-w-0 flex-1 resize-none bg-transparent px-2 py-2 text-base leading-6 text-gray-900 outline-none"
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
                className="group relative inline-flex h-10 w-10 items-center justify-center rounded-full text-amber-600 [@media(pointer:coarse)]:hidden transition-colors hover:bg-amber-50 hover:text-amber-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
              >
                <FiMic aria-hidden="true" className="h-4 w-4" />
                <span className="pointer-events-none absolute bottom-10 right-0 z-10 hidden w-72 rounded-lg bg-gray-900 px-3 py-2 text-left text-xs font-normal leading-5 text-white shadow-lg group-hover:block group-focus-visible:block">
                  {firefoxVersion >= FIREFOX_ON_DEVICE_SPEECH_VERSION
                    ? 'Firefox dictation is experimental. In about:config, enable media.webspeech.recognition.enable, then reload this page.'
                    : 'Dictation is unavailable in this Firefox version. Try Firefox Nightly or another supported browser.'}
                </span>
              </a>
            ) : (
              // Phone and tablet keyboards provide their own dictation, so touch screens omit this control.
              <div className="relative mr-1.5 sm:mr-0 [@media(pointer:coarse)]:hidden">
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
                <span className="absolute -bottom-1.5 -right-1.5 h-6 w-6 sm:-bottom-0.5 sm:-right-0.5 sm:h-4 sm:w-4 rounded-full border border-gray-300 bg-white text-gray-600 shadow-sm focus-within:ring-2 focus-within:ring-blue-400">
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
                  disabled={!isClientReady || composerUnavailable || !draft.trim()}
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
        {(contextUsage !== null || messages.length > 0 || costSummary) && (
          <p className="mt-2 px-2 text-center text-[0.6875rem] text-gray-500" aria-live="polite">
            {(contextUsage !== null || messages.length > 0) && <span title={contextDescription}>
              Context {contextUsage?.usedTokens !== undefined && contextUsage.maxTokens !== undefined
                ? `${contextUsage.estimated !== false ? '~' : ''}${(100 * contextUsage.usedTokens / contextUsage.maxTokens).toFixed(1)}% used`
                : 'unavailable'}
            </span>}
            {contextUsage?.usedTokens !== undefined && <>
              {' · '}
              <span title={tokenDescription}>
                Tokens: {contextUsage.estimated !== false ? '~' : ''}{contextUsage.usedTokens.toLocaleString('en-US')} / {contextUsage.maxTokens?.toLocaleString('en-US') ?? 'unavailable'}
              </span>
            </>}
            {activeSessionId && <>
              {' · '}
              <button type="button" onClick={() => void compactContext()}
                disabled={isStreaming || isCompacting || composerUnavailable}
                className="underline disabled:cursor-not-allowed disabled:opacity-50"
                title="Summarize older conversation context without generating an answer.">
                Compact context
              </button>
            </>}
            {costSummary && <>
              {(contextUsage !== null || messages.length > 0) && ' · '}
              <span title="Estimated LLM cost across this conversation, including retries and tool follow-up calls.">
                Est. cost: {costLabel(costSummary, false)}
              </span>
            </>}
          </p>
        )}
      </form>
    </main>
  );
}
