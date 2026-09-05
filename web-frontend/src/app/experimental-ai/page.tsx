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
import { ChangeEvent, FormEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { FiArrowDown } from 'react-icons/fi';
import BackendTokenField from '@/components/BackendTokenField';
import PageDocumentationLink from '@/components/PageDocumentationLink';
import { DOCUMENTATION_URLS, GITHUB_AI_BETA_ACCESS_URL, GITHUB_PRIVACY_URL } from '@/constants/urls';
import { useSchedulingData } from '@/hooks/useSchedulingData';
import { useTabSwitchWarning } from '@/utils/unsavedEditingState';
import { generateYamlFromState } from '@/utils/yamlGenerator';
import yaml from 'js-yaml';
import { ActivityEntry, AssistantActivity } from './AssistantActivity';
import {
  AiCapabilities,
  AiStaleTurnError,
  LOCAL_AI_API_URL,
  PRODUCTION_AI_API_URL,
  ToolActivity,
  approveProposal,
  createSession,
  getAiBaseUrl,
  getCapabilities,
  normalizeAiEndpoint,
  rejectProposal,
  streamMessage,
  updateSessionSchedule,
} from './aiClient';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  attachmentNames?: string[];
  activity?: ActivityEntry[];
  status?: 'pending' | 'failed';
  retry?: {
    question: string;
    requiresAttachments: boolean;
  };
}

const AI_STORAGE_KEY = 'nurse-scheduling-ai-data';
const AI_AUTH_STORAGE_KEY = 'nurse-scheduling-ai-auth';
const AI_SERVER_STORAGE_KEY = 'nurse-scheduling-ai-server';

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

function readStoredAuthTokens(): Record<string, string> {
  try {
    const stored = window.localStorage.getItem(AI_AUTH_STORAGE_KEY);
    if (stored === null) return {};
    const parsed = JSON.parse(stored) as StoredAiAuth;
    const tokens = typeof parsed.tokens === 'object' && parsed.tokens !== null
      ? Object.fromEntries(Object.entries(parsed.tokens).filter((entry): entry is [string, string] => (
          typeof entry[1] === 'string' && entry[1].trim().length > 0
        )))
      : {};
    if (typeof parsed.endpoint === 'string' && typeof parsed.token === 'string' && parsed.token.trim()) {
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
  kind: 'image' | 'document';
  previewUrl?: string;
}

const DISABLED_IMAGE_CAPABILITY: AiCapabilities['image_attachments'] = {
  enabled: false,
  accepted_media_types: [],
  max_files: 1,
  max_bytes_per_file: 1,
};

const DISABLED_DOCUMENT_CAPABILITY: AiCapabilities['document_attachments'] = {
  enabled: false,
  accepted_extensions: [],
  max_files: 1,
  max_bytes_per_file: 1,
};

const DOCUMENT_MEDIA_TYPES: Record<string, string> = {
  '.txt': 'text/plain',
  '.md': 'text/markdown',
  '.csv': 'text/csv',
  '.pdf': 'application/pdf',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
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
  const [draft, setDraft] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
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
  const [imageCapability, setImageCapability] = useState(DISABLED_IMAGE_CAPABILITY);
  const [documentCapability, setDocumentCapability] = useState(DISABLED_DOCUMENT_CAPABILITY);
  const [selectedAttachments, setSelectedAttachments] = useState<SelectedAttachment[]>([]);
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
  const sandboxScheduleRef = useRef<string | null>(null);
  const selectedAttachmentsRef = useRef<SelectedAttachment[]>([]);
  const followPageBottomRef = useRef(true);
  const hasMessagesRef = useRef(false);
  const composerRef = useRef<HTMLFormElement | null>(null);
  hasMessagesRef.current = messages.length > 0;
  useTabSwitchWarning(messages.length > 0);

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
    const storedTokens = readStoredAuthTokens();
    const storedToken = storedTokens[endpoint] ?? null;
    authTokensRef.current = storedTokens;
    setAiEndpoint(endpoint);
    setAuthToken(storedToken);
    setRememberAuthToken(storedToken !== null);
    setIsClientReady(true);
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
        setImageCapability(capabilities.image_attachments);
        setDocumentCapability(capabilities.document_attachments);
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

  useEffect(() => () => {
      abortControllerRef.current?.abort();
      selectedAttachmentsRef.current.forEach(attachment => {
        if (attachment.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
      });
  }, []);

  useEffect(() => {
    selectedAttachmentsRef.current = selectedAttachments;
  }, [selectedAttachments]);

  useEffect(() => {
    if (messages.length === 0) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => window.removeEventListener('beforeunload', warnBeforeUnload);
  }, [messages.length]);

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
    setImageCapability(DISABLED_IMAGE_CAPABILITY);
    setDocumentCapability(DISABLED_DOCUMENT_CAPABILITY);
    setServerError(null);
    setCapabilitiesError(null);
    setIsEditingServer(false);
    try {
      window.localStorage.setItem(AI_SERVER_STORAGE_KEY, endpoint);
    } catch {
      // A browser that refuses storage still applies the server for this visit.
    }
  };

  const reportRequestError = (requestError: unknown, fallback: string) => {
    if (isAuthenticationError(requestError)) {
      setAuthRequired(true);
      setAuthRejected(true);
      setIsEditingAuthToken(true);
      setError('AI credentials were rejected. Enter the current AI token and try again.');
      return;
    }
    setError(requestError instanceof Error ? requestError.message : fallback);
  };

  const selectAttachments = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = '';
    if (files.length === 0) return;

    const candidates = files.map(file => {
      if (imageCapability.enabled && imageCapability.accepted_media_types.includes(file.type)) {
        return { file, kind: 'image' as const };
      }
      const extension = fileExtension(file.name);
      if (documentCapability.enabled && documentCapability.accepted_extensions.includes(extension)) {
        const normalizedFile = new File([file], file.name, {
          type: DOCUMENT_MEDIA_TYPES[extension] ?? 'text/plain',
          lastModified: file.lastModified,
        });
        return { file: normalizedFile, kind: 'document' as const };
      }
      return null;
    });
    if (candidates.some(candidate => candidate === null)) {
      setError('Attach only a file type enabled by the AI backend.');
      return;
    }
    const attachments = candidates.filter(candidate => candidate !== null);
    const selectedImageCount = selectedAttachments.filter(attachment => attachment.kind === 'image').length;
    const selectedDocumentCount = selectedAttachments.length - selectedImageCount;
    const imageCount = attachments.filter(attachment => attachment.kind === 'image').length;
    const documentCount = attachments.length - imageCount;
    if (selectedImageCount + imageCount > imageCapability.max_files) {
      setError(`Attach at most ${imageCapability.max_files} images to one question.`);
      return;
    }
    if (selectedDocumentCount + documentCount > documentCapability.max_files) {
      setError(`Attach at most ${documentCapability.max_files} documents to one question.`);
      return;
    }
    if (attachments.some(attachment => (
      attachment.kind === 'image' && attachment.file.size > imageCapability.max_bytes_per_file
    ))) {
      const maxMegabytes = (imageCapability.max_bytes_per_file / 1_000_000).toLocaleString(undefined, {
        maximumFractionDigits: 1,
      });
      setError(`Each image must be ${maxMegabytes} MB or smaller.`);
      return;
    }
    if (attachments.some(attachment => (
      attachment.kind === 'document' && attachment.file.size > documentCapability.max_bytes_per_file
    ))) {
      const maxKilobytes = Math.floor(documentCapability.max_bytes_per_file / 1000).toLocaleString();
      setError(`Each document must be ${maxKilobytes} KB or smaller.`);
      return;
    }

    setError(null);
    setSelectedAttachments(previous => [
      ...previous,
      ...attachments.map(attachment => ({
        ...attachment,
        id: messageId(),
        ...(attachment.kind === 'image' ? { previewUrl: URL.createObjectURL(attachment.file) } : {}),
      })),
    ]);
  };

  const removeAttachment = (id: string) => {
    setSelectedAttachments(previous => {
      const removed = previous.find(attachment => attachment.id === id);
      if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl);
      return previous.filter(attachment => attachment.id !== id);
    });
  };

  const sendRequest = async (
    question: string,
    attachmentsForMessage: SelectedAttachment[],
    clearComposer: boolean,
  ) => {
    if (!question || isStreaming || (authRequired && authToken === null)) return;

    const userMessage: ChatMessage = {
      id: messageId(),
      role: 'user',
      content: question,
      attachmentNames: attachmentsForMessage.map(attachment => attachment.file.name),
    };
    const assistantId = messageId();
    followPageBottomRef.current = true;
    setShowScrollToBottom(false);
    setMessages(previous => [
      ...previous,
      userMessage,
      { id: assistantId, role: 'assistant', content: '', status: 'pending' },
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
      } else if (syncedScheduleRef.current !== scheduleYaml) {
        // The schedule can change elsewhere in the app between questions.
        await updateSessionSchedule(sessionId, scheduleYaml, authToken, sessionEndpoint);
      }
      syncedScheduleRef.current = scheduleYaml;
      await streamMessage(
        sessionId,
        question,
        {
          onDelta: text => setMessages(previous => previous.map(message => (
            message.id === assistantId
              ? {
                ...message,
                content: message.content + text,
                activity: appendResponseActivity(message.activity ?? [], text),
              }
              : message
          ))),
          onReasoning: text => setMessages(previous => previous.map(message => {
            if (message.id !== assistantId) return message;
            const activity = message.activity ?? [];
            const last = activity[activity.length - 1];
            // Consecutive reasoning belongs to one entry, so the order of work stays readable.
            if (last?.kind === 'reasoning') {
              return { ...message, activity: [...activity.slice(0, -1), { ...last, text: last.text + text }] };
            }
            return { ...message, activity: [...activity, { kind: 'reasoning', text }] };
          })),
          onToolStart: activity => setMessages(previous => previous.map(message => (
            message.id === assistantId
              ? {
                ...message,
                activity: [
                  ...(message.activity ?? []),
                  { kind: 'tool' as const, ...activity, result: '', ok: true, state: 'running' as const },
                ],
              }
              : message
          ))),
          onTool: activity => setMessages(previous => previous.map(message => {
            if (message.id !== assistantId) return message;
            return { ...message, activity: finishToolActivity(message.activity ?? [], activity) };
          })),
          onScheduleChange: candidate => {
            const before = sandboxScheduleRef.current ?? scheduleYaml;
            sandboxScheduleRef.current = candidate;
            setMessages(previous => previous.map(message => (
              message.id === assistantId
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
          images: attachmentsForMessage
            .filter(attachment => attachment.kind === 'image')
            .map(attachment => attachment.file),
          documents: attachmentsForMessage
            .filter(attachment => attachment.kind === 'document')
            .map(attachment => attachment.file),
        },
        sessionEndpoint,
      );
      setMessages(previous => previous.map(message => (
        message.id === assistantId ? { ...message, status: undefined } : message
      )));
    } catch (streamError) {
      const staleTurnMessage = streamError instanceof AiStaleTurnError ? streamError.message : null;
      setMessages(previous => previous.map(message => (
        message.id === assistantId
          ? {
            ...message,
            content: staleTurnMessage ?? message.content,
            status: 'failed',
            activity: staleTurnMessage === null
              ? interruptRunningTools(message.activity ?? [])
              : [{ kind: 'response' as const, text: staleTurnMessage }],
            retry: {
              question,
              requiresAttachments: attachmentsForMessage.length > 0,
            },
          }
          : message
      )));
      if (!controller.signal.aborted && staleTurnMessage === null) {
        reportRequestError(streamError, 'The AI request failed.');
      }
    } finally {
      abortControllerRef.current = null;
      setIsStreaming(false);
    }
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const question = draft.trim();
    if (!question || isStreaming || (authRequired && authToken === null)) return;
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

  const stop = () => abortControllerRef.current?.abort();
  const selectedImageCount = selectedAttachments.filter(attachment => attachment.kind === 'image').length;
  const selectedDocumentCount = selectedAttachments.length - selectedImageCount;
  const credentialsMissing = authRequired && authToken === null;
  const attachmentPickerDisabled = isStreaming || credentialsMissing || (
    (!imageCapability.enabled || selectedImageCount >= imageCapability.max_files)
    && (!documentCapability.enabled || selectedDocumentCount >= documentCapability.max_files)
  );
  const serverLocked = sessionIdRef.current !== null || messages.length > 0;

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
        </div>
        <p className="text-sm text-gray-600">
          Ask questions about the schedule currently open in this browser, or ask for a change. You can attach supported images and documents when the backend enables them. Proposed changes apply only after you approve them.
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
          . Assume all AI chats are logged, may be used to improve our product and the AI provider&apos;s product, and are not currently anonymized.{' '}
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
              onClick={() => setIsEditingServer(previous => !previous)}
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
        <div className="mt-2 flex flex-wrap gap-4 text-xs text-gray-500">
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
                : 'mr-auto border border-gray-200 bg-white text-gray-900'
            }`}
          >
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide opacity-70">
              {message.role === 'user' ? 'You' : 'Assistant'}
            </p>
            {message.activity && (
              <AssistantActivity
                entries={message.activity.filter(entry => (
                  entry.kind === 'response' || (entry.kind === 'reasoning' ? showReasoning : showTools)
                ))}
              />
            )}
            {message.role === 'assistant' && !message.content && message.status === 'pending' ? (
              <ThinkingIndicator />
            ) : message.role === 'user' ? (
              <p className="whitespace-pre-wrap break-words">{message.content}</p>
            ) : null}
            {message.attachmentNames && message.attachmentNames.length > 0 && (
              <p className="mt-2 text-xs opacity-80">
                Attached: {message.attachmentNames.join(', ')}
              </p>
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
        className="fixed inset-x-10 bottom-0 z-30 mx-auto max-w-5xl space-y-3 bg-gradient-to-t from-white via-white to-white/90 px-4 pb-4 pt-3 sm:px-6"
      >
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
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          {(imageCapability.enabled || documentCapability.enabled) && (
            <label className={`order-2 rounded-xl border px-3 py-3 text-center text-sm font-medium sm:order-1 ${
              attachmentPickerDisabled
                ? 'cursor-not-allowed border-gray-200 bg-gray-100 text-gray-400'
                : 'cursor-pointer border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
            }`}>
              <input
                type="file"
                accept={[
                  ...(imageCapability.enabled ? imageCapability.accepted_media_types : []),
                  ...(documentCapability.enabled ? documentCapability.accepted_extensions : []),
                ].join(',')}
                multiple
                disabled={attachmentPickerDisabled}
                onChange={selectAttachments}
                className="sr-only"
              />
              Attach files
            </label>
          )}
          <label className="order-1 flex-1 sm:order-2">
            <span className="sr-only">Ask about the current schedule</span>
            <textarea
              value={draft}
              onChange={event => setDraft(event.target.value)}
              onKeyDown={event => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              disabled={!isClientReady || credentialsMissing}
              rows={3}
              maxLength={8000}
              placeholder="Ask about the current schedule…"
              className="w-full resize-none rounded-xl border border-gray-300 bg-white px-4 py-3 text-gray-900 shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-200 disabled:bg-gray-100"
            />
          </label>
          {isStreaming ? (
            <button
              type="button"
              onClick={stop}
              className="order-3 rounded-xl bg-gray-800 px-5 py-3 font-medium text-white hover:bg-gray-900"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!isClientReady || credentialsMissing || !draft.trim()}
              className="order-3 rounded-xl bg-blue-600 px-5 py-3 font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-gray-300"
            >
              Send
            </button>
          )}
        </div>
      </form>
    </main>
  );
}
