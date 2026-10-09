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

import { ChatLifecycle, scopedCallbacks } from './chatLifecycle';
import {
  type Dispatch,
  type SetStateAction,
  useCallback,
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';

import { applyModelInput, type ChatMessage } from './chatTranscript';
import { applyOptimizationEvent, appendOptimizationResult, type ActiveOptimization } from './optimizerEvents';
import { retentionLabel } from './chatPresentation';

import {
  AiHttpError,
  AiStaleRunError,
  DEFAULT_SESSION_RETENTION_SECONDS,
  OptimizationActivity,
  type ContextUsage,
  ToolActivity,
  approveProposal,
  createSession,
  removeGeneratedZip,
  getUploads,
  removeUpload,
  type ModelInput,
  type UploadedFile,
  getSessionStatus,
  queueMessage,
  rejectProposal,
  sendMessage,
  stopSession,
  updateSessionSchedule,
  uploadFiles,
} from './aiClient';
import type { SessionReset, ToolStartActivity, OptimizationProgressActivity } from './aiClient';
import type { SessionEvent } from './sessionEvents';
import { useSessionEventStream } from './useSessionEventStream';
import { SessionEventRouter } from './sessionEventRouter';
import {
  applyAssistantEvent,
  stopResponse,
  messageId,
  interruptRunningTools,
  type AssistantEvent,
} from './assistantEvents';
import { AI_CONVERSATION_STORAGE_KEY, type StoredChatConversation } from './chatConversation';
import { isAuthenticationError } from './aiClient';

interface StreamCallbacks {
  onDownload?: (id: string) => void;
  onWarning?: (message: string) => void;
  onModelInput?: (input: ModelInput) => void;
  onReset?: (reset: SessionReset) => void;
  onRunStart?: (runId: string, trigger: string) => void;
  onRunContext?: (runId: string) => void;
  onDelta: (text: string) => void;
  onReasoning?: (text: string) => void;
  onTruncated?: () => void;
  onToolStart?: (activity: ToolStartActivity) => void;
  onTool?: (activity: ToolActivity) => void;
  onSteering?: (messageId: string, message: string) => void;
  onScheduleChange?: (scheduleYaml: string) => void;
  onProposal?: (diff: string) => void;
  onOptimization?: (activity: OptimizationActivity) => void;
  onOptimizationProgress?: (activity: OptimizationProgressActivity) => void;
  onDone?: (runId?: string) => void;
  onStopped?: (runId?: string) => void;
  onStale?: (message: string) => void;
  onContextUsage?: (usage: ContextUsage) => void;
  onHistoryTrimmed?: (dropped: number) => void;
  onError?: (message: string) => void;
}

function dispatchPageEvent(event: SessionEvent, callbacks: StreamCallbacks): void {
  if (event.runId && event.type !== 'run_context' && event.type !== 'session_reset') callbacks.onRunContext?.(event.runId);
  switch (event.type) {
    case 'session_reset': callbacks.onReset?.(event.reset); break;
    case 'run_context': callbacks.onRunContext?.(event.runId); break;
    case 'run_start': callbacks.onRunStart?.(event.runId, event.trigger); break;
    case 'delta': callbacks.onDelta(event.text); break;
    case 'reasoning': callbacks.onReasoning?.(event.text); break;
    case 'truncated': callbacks.onTruncated?.(); break;
    case 'tool_start': callbacks.onToolStart?.(event.activity); break;
    case 'tool': callbacks.onTool?.(event.activity); break;
    case 'steering': callbacks.onSteering?.(event.messageId, event.message); break;
    case 'schedule_change': callbacks.onScheduleChange?.(event.scheduleYaml); break;
    case 'proposal': callbacks.onProposal?.(event.diff); break;
    case 'download': callbacks.onDownload?.(event.downloadId); break;
    case 'warning': callbacks.onWarning?.(event.message); break;
    case 'model_input': callbacks.onModelInput?.(event.input); break;
    case 'optimization': callbacks.onOptimization?.(event.activity); break;
    case 'optimization_progress': callbacks.onOptimizationProgress?.(event.activity); break;
    case 'done': callbacks.onDone?.(event.runId); break;
    case 'stopped': callbacks.onStopped?.(event.runId); break;
    case 'stale': callbacks.onStale?.(event.message); break;
    case 'error': callbacks.onError?.(event.message); break;
    case 'context_usage': callbacks.onContextUsage?.(event.usage); break;
    case 'history_trimmed': callbacks.onHistoryTrimmed?.(event.dropped); break;
  }
}

function startsVisibleOutput(event: AssistantEvent): boolean {
  return event.type === 'tool_start' || event.type === 'tool' || event.type === 'schedule_change'
    || ((event.type === 'delta' || event.type === 'reasoning') && event.text.length > 0);
}

function assistantEventCallbacks(
  apply: (event: AssistantEvent) => void,
  workingSchedule: { current: string | null },
  browserSchedule: { readonly current: string },
): Required<Pick<StreamCallbacks, 'onDelta' | 'onReasoning' | 'onTruncated' | 'onToolStart' | 'onTool' | 'onScheduleChange'>> {
  return {
    onDelta: text => apply({ type: 'delta', text }),
    onReasoning: text => apply({ type: 'reasoning', text }),
    onTruncated: () => apply({ type: 'truncated' }),
    onToolStart: activity => apply({ type: 'tool_start', activity }),
    onTool: activity => apply({ type: 'tool', activity }),
    onScheduleChange: after => {
      const before = workingSchedule.current ?? browserSchedule.current;
      workingSchedule.current = after;
      apply({ type: 'schedule_change', before, after });
    },
  };
}

const UNSAVED_APPROVAL_WARNING = 'This approval could not be saved for recovery after a service restart.';
const UNSAVED_REJECTION_WARNING = 'This rejection could not be saved for recovery after a service restart.';

interface QueuedChatMessage {
  createdAt: number;
  id: string;
  content: string;
}

interface AiChatOptions {
  scheduleYaml: string;
  aiEndpoint: string;
  authRequired: boolean;
  authToken: string | null;
  isClientReady: boolean;
  serverStatus: string;
  retainsUploads: boolean;
  backendVersion?: string;
  setError: Dispatch<SetStateAction<string | null>>;
  reportRequestError: (error: unknown, fallback: string) => void;
  onSendStart: (kind: 'send' | 'retry' | 'queue') => void;
  onReset: () => void;
  onApplySchedule: (scheduleYaml: string) => void;
}

/** Own chat operations and saved conversation state independently of composer UI. */
export function useAiChat({ scheduleYaml, aiEndpoint, authRequired, authToken, isClientReady,
  serverStatus, retainsUploads, backendVersion, setError, reportRequestError, onSendStart, onReset, onApplySchedule,
}: AiChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
  const [removingUploadId, setRemovingUploadId] = useState<string | null>(null);
  const [removingDownloadId, setRemovingDownloadId] = useState<string | null>(null);
  const [contextUsage, setContextUsage] = useState<ContextUsage | null>(null);
  const updateContextUsage = useCallback((usage: ContextUsage) => setContextUsage(previous => (
    usage.usedTokens === undefined && previous?.usedTokens !== undefined
      ? { ...usage, usedTokens: previous.usedTokens, maxTokens: previous.maxTokens }
      : usage
  )), []);

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionExpiresAt, setSessionExpiresAt] = useState<number | null>(null);
  const [sessionRetentionSeconds, setSessionRetentionSeconds] = useState(DEFAULT_SESSION_RETENTION_SECONDS);
  const [conversationUnavailable, setConversationUnavailable] = useState(false);
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
  const [trimmedHistoryCount, setTrimmedHistoryCount] = useState(0);
  const [lifecycle] = useState(() => new ChatLifecycle());
  const operations = useSyncExternalStore(lifecycle.subscribe, lifecycle.getSnapshot, lifecycle.getSnapshot);
  const isStreaming = Object.values(operations).some(active => active !== null && active.phase !== 'interrupted');

  const isStopping = Object.values(operations).some(active => active?.phase === 'stopping');

  const [isReconnecting, setIsReconnecting] = useState(false);
  const resumedRequestRef = useRef<string | null>(null);
  const currentRequestRef = useRef<{ id: string; stopped: boolean } | null>(null);
  const [activeOptimization, setActiveOptimization] = useState<ActiveOptimization | null>(null);
  const [queuedMessages, setQueuedMessages] = useState<QueuedChatMessage[]>([]);
  const [steeringAssistantId, setSteeringAssistantId] = useState<string | null>(null);
  const [proposalDiff, setProposalDiff] = useState<string | null>(null);
  const [proposalNotice, setProposalNotice] = useState<string | null>(null);
  const [isApplyingProposal, setIsApplyingProposal] = useState(false);
  const syncedScheduleRef = useRef<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const sessionEndpointRef = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const eventRouterRef = useRef(new SessionEventRouter());
  const sessionEvents = useSessionEventStream();

  const lastSessionEventIdRef = sessionEvents.cursor;

  const scheduleYamlRef = useRef(scheduleYaml);
  const sandboxScheduleRef = useRef<string | null>(null);
  const queuedMessagesRef = useRef<QueuedChatMessage[]>([]);
  const conversationStorageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const persistConversationRef = useRef<(() => void) | null>(null);
  const checkedSessionRef = useRef<string | null>(null);
  const resetRuntime = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    sessionEvents.reset();
    sessionIdRef.current = null;
    sessionEndpointRef.current = null;
    syncedScheduleRef.current = null;
    sandboxScheduleRef.current = null;
    checkedSessionRef.current = null;
    queuedMessagesRef.current = [];
    lifecycle.reset();
    setIsReconnecting(false);
    currentRequestRef.current = null;
    setActiveSessionId(null);
    setSessionExpiresAt(null);
    setQueuedMessages([]);
    setActiveOptimization(null);
    setProposalDiff(null);
    onReset();
    setIsApplyingProposal(false);
  }, [lifecycle, sessionEvents, onReset]);

  scheduleYamlRef.current = scheduleYaml;

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
          backendVersion,
          contextUsage,
          backgroundAssistantId: lifecycle.current('background')?.id,
          trimmedHistoryCount,
          pendingRequest: (() => {
            const request = messages.find(message => message.request?.active)?.request;
            return request ? { messageId: request.id, question: request.question, questionId: request.questionId,
              assistantId: request.assistantId, activeAssistantId: request.activeAssistantId,
              createdAt: messages.find(message => message.id === request.questionId)?.createdAt ?? Date.now(),
              uploading: request.uploading } : null;
          })(),
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
    backendVersion,
    contextUsage,
    aiEndpoint,
    isClientReady,
    lifecycle,
    lastSessionEventIdRef,
    messages,
    proposalDiff,
    scheduleYaml,
    sessionExpiresAt,
    sessionRetentionSeconds,
    trimmedHistoryCount,
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
        if (sessionIdRef.current !== activeSessionId) return;
        setSessionExpiresAt(Date.now() + expiresInSeconds * 1000);
      })
      .catch((statusError: unknown) => {
        if (sessionIdRef.current !== activeSessionId) return;
        if (statusError instanceof AiHttpError && statusError.status === 404) {
          resetRuntime();
          setConversationUnavailable(true);
          setSessionNotice('This chat is no longer available on the AI server. Start a new chat to continue.');
          window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
        } else {
          checkedSessionRef.current = null;
          reportRequestError(statusError, 'The stored AI chat could not be checked.');
        }
      });
  }, [activeSessionId, aiEndpoint, authToken, isClientReady, reportRequestError, resetRuntime]);

  useEffect(() => {
    if (!activeSessionId || !retainsUploads || conversationUnavailable) {
      setUploadedFiles([]);
      return;
    }
    if (isStreaming || removingUploadId !== null || (authRequired && authToken === null)) return;
    const controller = new AbortController();
    getUploads(activeSessionId, authToken, sessionEndpointRef.current ?? aiEndpoint, controller.signal)
      .then(files => { if (!controller.signal.aborted) setUploadedFiles(files); })
      .catch(uploadError => {
        if (!controller.signal.aborted) reportRequestError(uploadError, 'Uploaded files could not be listed.');
      });
    return () => controller.abort();
  }, [activeSessionId, retainsUploads, isStreaming, removingUploadId, aiEndpoint, authToken, authRequired, conversationUnavailable, reportRequestError]);

  const removeUploadedFile = async (uploadId: string) => {
    const sessionId = sessionIdRef.current;
    if (!sessionId) return;
    setRemovingUploadId(uploadId);
    try {
      await removeUpload(sessionId, uploadId, authToken, sessionEndpointRef.current ?? aiEndpoint);
      setUploadedFiles(files => files.filter(file => file.id !== uploadId));
      renewSessionExpiration();
    } catch (uploadError) {
      reportRequestError(uploadError, 'The uploaded file could not be removed.');
    } finally {
      setRemovingUploadId(null);
    }
  };

  useEffect(() => {
    if (activeSessionId === null || sessionExpiresAt === null) return;
    let timeout: number | undefined;
    const checkExpiration = () => {
      const delay = sessionExpiresAt - Date.now();
      if (delay > 0) {
        // Browser timers cannot wait more than 2,147,483,647 milliseconds at once.
        timeout = window.setTimeout(checkExpiration, Math.min(delay, 2147483647));
        return;
      }
      resetRuntime();
      setConversationUnavailable(true);
      setSessionNotice(
        `This chat expired after ${retentionLabel(sessionRetentionSeconds)} of inactivity. Start a new chat to continue.`,
      );
      window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
    };
    checkExpiration();
    return () => window.clearTimeout(timeout);
  }, [activeSessionId, resetRuntime, sessionExpiresAt, sessionRetentionSeconds]);

  const renewSessionExpiration = () => {
    setSessionExpiresAt(Date.now() + sessionRetentionSeconds * 1000);
  };

  const markConversationUnavailable = (notice: string) => {
    resetRuntime();
    setConversationUnavailable(true);
    setSessionNotice(notice);
    window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
  };

  const startSessionEventStream = useCallback((sessionId: string, endpoint: string, resetReplay = false) => {
    const beginBackgroundMessage = (runId: string) => {
      lifecycle.begin('background', runId);
      // The server renews the session when it starts this turn.
      setSessionExpiresAt(Date.now() + sessionRetentionSeconds * 1000);
      sandboxScheduleRef.current = scheduleYamlRef.current;
      setMessages(previous => {
        const existing = [...previous].reverse().find(message => message.role === 'assistant' && (message.runId ?? message.id) === runId);
        return existing ? previous.map(message => message.id === existing.id
          ? { ...message, runId, status: 'pending' as const, responseCompletedAt: undefined } : message)
          : [...previous, { id: runId, runId, role: 'assistant', content: '', status: 'pending', responseStartedAt: Date.now() }];
      });
    };
    // A reconnect replays only retained events, so a long turn can lose its own
    // turn_start. Adopt the remaining output instead of discarding the answer.
    const resumeBackgroundMessage = () => {
      if (lifecycle.getSnapshot().background?.phase !== 'interrupted' && lifecycle.current('background')) return;
      beginBackgroundMessage(lifecycle.current('background')?.id ?? messageId());
    };
    const updateBackgroundMessage = (update: (message: ChatMessage) => ChatMessage, messageId?: string) => {
      const activeId = lifecycle.current('background')?.id ?? messageId;
      if (activeId === undefined) return;
      setMessages(previous => {
        const answer = [...previous].reverse().find(message => message.role === 'assistant' && (message.runId ?? message.id) === activeId);
        return previous.map(message => message.id === answer?.id ? update(message) : message);
      });
    };
    const failBackgroundTurn = (message: string) => {
      updateBackgroundMessage(entry => ({
        ...entry,
        content: entry.content || message,
        status: 'failed',
        responseCompletedAt: Date.now(),
        activity: interruptRunningTools(entry.activity ?? []),
      }));
      lifecycle.finish(lifecycle.current('background'));
      setError(message);
    };
    const ownsConversation = lifecycle.capture();
    const handlers: StreamCallbacks = {
      onReset: reset => {
        setMessages(previous => {
          const keptRuns = new Set<string>();
          return previous.flatMap(message => {
            const runId = message.runId ?? message.id;
            if (!reset.runIds.includes(runId)) return [message];
            if (message.role !== 'assistant' || keptRuns.has(runId)) return [];
            keptRuns.add(runId);
            return [{ ...message, runId, content: '', activity: [], status: 'pending' as const, responseCompletedAt: undefined }];
          });
        });
        setProposalDiff(reset.proposalDiff);
        setActiveOptimization(null);
        lifecycle.finish(lifecycle.current('background'));
        const foreground = eventRouterRef.current.foreground;
        if (foreground?.runId && !reset.runIds.includes(foreground.runId) && !reset.terminalRunIds.includes(foreground.runId)
          && reset.activeRunId !== foreground.runId) {
          foreground.reject(new Error('This response expired from event replay. Start a new question.'));
        }
        if (reset.incomplete) setSessionNotice('Some earlier response output expired from event replay.');
      },
      onRunContext: id => {
        if (lifecycle.current('background')?.id !== id) beginBackgroundMessage(id);
      },
      onRunStart: beginBackgroundMessage,
      onSteering: (queuedId, content) => {
        const runId = lifecycle.current('background')?.id;
        if (!runId) return;
        const nextId = messageId();
        setMessages(previous => {
          if (previous.some(message => message.id === queuedId)) return previous;
          const answer = [...previous].reverse().find(message => message.role === 'assistant' && (message.runId ?? message.id) === runId);
          const index = previous.findIndex(message => message.id === answer?.id);
          const user: ChatMessage = { id: queuedId, runId, role: 'user', content, createdAt: Date.now() };
          if (answer && (answer.content || answer.activity?.length)) {
            const finished = { ...answer, status: undefined, responseCompletedAt: Date.now() };
            const next: ChatMessage = { id: nextId, runId, role: 'assistant', content: '', status: 'pending', responseStartedAt: Date.now() };
            return [...previous.slice(0, index), finished, user, next, ...previous.slice(index + 1)];
          }
          return index < 0 ? [...previous, user] : [...previous.slice(0, index), user, ...previous.slice(index)];
        });
      },
      ...assistantEventCallbacks(event => {
        resumeBackgroundMessage();
        updateBackgroundMessage(message => applyAssistantEvent(message, event));
      }, sandboxScheduleRef, scheduleYamlRef),
      onProposal: diff => setProposalDiff(diff),
      onOptimization: activity => {
        setActiveOptimization(current => applyOptimizationEvent(current, { type: 'optimization', activity }));
        if (activity.terminal) setMessages(previous => appendOptimizationResult(previous, activity, Date.now()));
      },
      onOptimizationProgress: activity => {
        setActiveOptimization(current => applyOptimizationEvent(current, { type: 'optimization_progress', activity }));
      },
      onDone: runId => {
        updateBackgroundMessage(message => ({
          ...message,
          status: undefined,
          responseCompletedAt: Date.now(),
        }), runId);
        lifecycle.finish(lifecycle.current('background'));
      },
      onStopped: runId => {
        updateBackgroundMessage(stopResponse, runId);
        lifecycle.finish(lifecycle.current('background'));
      },
      onStale: message => {
        updateBackgroundMessage(entry => ({
          ...entry,
          content: message,
          status: 'failed',
          responseCompletedAt: Date.now(),
          activity: [{ kind: 'response', text: message }],
        }));
        lifecycle.finish(lifecycle.current('background'));
        setError(message);
      },
      onDownload: id => updateBackgroundMessage(entry => ({ ...entry, downloadId: id })),
      onWarning: setError,
      onModelInput: input => {
        const runId = lifecycle.current('background')?.id;
        setMessages(previous => {
        const answer = [...previous].reverse().find(message => message.role === 'assistant' && (message.runId ?? message.id) === runId);
        if (!answer) return previous;
        const index = previous.findIndex(message => message.id === answer.id);
        const question = [...previous.slice(0, index)].reverse().find(message => message.role === 'user' && message.source === undefined);
        return applyModelInput(previous, input, { questionId: question?.id ?? null, assistantId: answer.id });
        });
      },
      onContextUsage: updateContextUsage,
      onHistoryTrimmed: setTrimmedHistoryCount,
      onError: failBackgroundTurn,
    };
    sessionEvents.connect({
      sessionId, endpoint, authToken, resetReplay,
      onEventId: () => setIsReconnecting(false),
      onDisconnect: () => { if (lifecycle.busy) setIsReconnecting(true); },
      onEvent: event => eventRouterRef.current.dispatch(event, value => dispatchPageEvent(value, handlers), ownsConversation),
      onError: streamError => {
        if (isAuthenticationError(streamError)) reportRequestError(streamError, 'The AI session could not reconnect.');
      },
    });
  }, [authToken, lifecycle, reportRequestError, sessionRetentionSeconds, updateContextUsage, sessionEvents, setError]);

  useEffect(() => {
    if (!isClientReady || activeSessionId === null || conversationUnavailable) return;
    if (messages.some(message => message.request?.active) && eventRouterRef.current.foreground === null) return;
    if (!sessionEvents.connected(activeSessionId, authToken, sessionEndpointRef.current ?? aiEndpoint)) {
      startSessionEventStream(activeSessionId, sessionEndpointRef.current ?? aiEndpoint);
    }
  }, [
    activeSessionId,
    aiEndpoint,
    authToken,
    conversationUnavailable,
    isClientReady,
    messages,
    sessionEvents,
    startSessionEventStream,
  ]);

  const sendRequest = async (
    question: string,
    attachmentsForMessage: File[],
    clearComposer: boolean,
    createdAt = Date.now(),
    resume?: { id: string; questionId: string; assistantId: string; activeAssistantId?: string; recover?: boolean },
  ) => {
    if (!question || lifecycle.busy || conversationUnavailable || (authRequired && authToken === null)) return;

    const userMessage: ChatMessage = {
      id: resume?.questionId ?? messageId(),
      role: 'user',
      createdAt,
      content: question,
    };
    const request = {
      id: resume?.id ?? messageId(), question, questionId: userMessage.id,
      assistantId: resume?.assistantId ?? messageId(), active: true,
      // Recovery must not send the question without files whose upload never finished.
      uploading: attachmentsForMessage.length > 0,
    };
    currentRequestRef.current = { id: request.id, stopped: false };
    const currentRequest = currentRequestRef.current;
    userMessage.requestId = request.id;
    // Cursor recovery continues the active reply. Replacement snapshots rebuild from the original reply.
    let activeAssistantId = resume?.recover ? resume.activeAssistantId ?? request.assistantId : request.assistantId;
    const initialAssistantId = request.assistantId;
    const runMessageIds = new Set([
      initialAssistantId, activeAssistantId,
      ...messages.filter(message => resume?.recover && message.requestId === request.id && message.id !== userMessage.id)
        .map(message => message.id),
    ]);
    const recoveredAssistant = resume?.recover ? messages.find(message => message.id === activeAssistantId) : undefined;
    let activeAssistantHasOutput = Boolean(recoveredAssistant?.content || recoveredAssistant?.activity?.length);
    let activeQuestion = resume?.recover
      ? messages.slice(0, messages.findIndex(message => message.id === activeAssistantId))
        .findLast(message => message.role === 'user' && message.requestId === request.id)?.content ?? question
      : question;
    let activeQuestionRequiresAttachments = attachmentsForMessage.length > 0;
    const responseStartedAt = Date.now();
    onSendStart(clearComposer ? 'send' : 'retry');
    const withActiveAssistant = (message: ChatMessage, assistantId: string): ChatMessage => (
      message.request?.id === request.id
        ? { ...message, request: { ...message.request, activeAssistantId: assistantId } } : message
    );
    const resetResponse = () => {
      const assistantId = activeAssistantId;
      setMessages(previous => {
        const original = previous.find(message => message.id === assistantId);
        const assistant: ChatMessage = {
          id: assistantId, role: 'assistant', content: '', status: 'pending',
          responseStartedAt: original?.responseStartedAt ?? responseStartedAt, requestId: request.id,
          request: { ...request, activeAssistantId: assistantId },
          ...(resume?.recover && original ? { content: original.content, activity: original.activity, runId: original.runId } : {}),
        };
        const retained = previous.filter(message => message.id !== `status-${assistantId}`
          && (resume?.recover || message.requestId !== request.id || message.id === userMessage.id || message.id === assistantId))
          .map(message => withActiveAssistant(message, assistantId));
        if (original) return retained.map(message => message.id === assistantId ? assistant : message);
        const questionIndex = retained.findIndex(message => message.id === userMessage.id);
        if (questionIndex < 0) return [...retained, userMessage, assistant];
        retained.splice(questionIndex + 1, 0, assistant);
        return retained;
      });
    };
    resetResponse();
    setError(null);
    // A pending proposal stays approvable across messages until it is approved, rejected, or replaced.
    setProposalNotice(null);
    const operation = lifecycle.begin('foreground', activeAssistantId);
    sandboxScheduleRef.current = scheduleYaml;
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      let sessionId = sessionIdRef.current;
      const sessionEndpoint = sessionEndpointRef.current ?? aiEndpoint;
      if (sessionId === null) {
        sessionId = await createSession(scheduleYaml, authToken, sessionEndpoint);
        if (!lifecycle.owns(operation)) return;
        controller.signal.throwIfAborted();
        sessionIdRef.current = sessionId;
        sessionEndpointRef.current = sessionEndpoint;
        startSessionEventStream(sessionId, sessionEndpoint);
        checkedSessionRef.current = sessionId;
        setActiveSessionId(sessionId);
        setConversationUnavailable(false);
        setSessionNotice(null);
      } else if (!resume?.recover && syncedScheduleRef.current !== scheduleYaml) {
        // The schedule can change elsewhere in the app between questions. The backend then
        // discards a proposal made for the previous schedule.
        await updateSessionSchedule(sessionId, scheduleYaml, authToken, sessionEndpoint);
        if (!lifecycle.owns(operation)) return;
        setProposalDiff(null);
      }
      if (!lifecycle.owns(operation)) return;
      controller.signal.throwIfAborted();
      if (!resume?.recover) syncedScheduleRef.current = scheduleYaml;
      renewSessionExpiration();
      let runFinished = false;
      let finishRun!: () => void;
      let rejectRun!: (error: Error) => void;
      const finished = new Promise<void>((resolve, reject) => {
        finishRun = () => { runFinished = true; resolve(); };
        rejectRun = reject;
      });
      void finished.catch(() => {});
      // Subscribe before submitting. Neither a fast terminal event nor a reconnect
      // should finish a different operation.
      const callbacks = scopedCallbacks<StreamCallbacks>({
        onDone: finishRun,
        onStopped: () => { controller.abort(); finishRun(); },
        onError: message => rejectRun(new Error(message)),
        onStale: message => rejectRun(new AiStaleRunError(message)),
        onReset: () => {
          const runId = eventRouterRef.current.foreground?.runId;
          activeAssistantId = initialAssistantId;
          activeAssistantHasOutput = false;
          activeQuestion = question;
          const resetIds = new Set(runMessageIds);
          setMessages(previous => {
            const first = previous.findIndex(message => resetIds.has(message.id));
            const position = first < 0 ? previous.findIndex(message => message.id === userMessage.id) + 1
              : previous.slice(0, first).filter(message => !resetIds.has(message.id)).length;
            const retained = previous.filter(message => !resetIds.has(message.id))
              .map(message => withActiveAssistant(message, initialAssistantId));
            retained.splice(position, 0, {
              id: initialAssistantId, runId, requestId: request.id, request: { ...request, activeAssistantId: initialAssistantId },
              role: 'assistant', content: '', status: 'pending', responseStartedAt,
            });
            return retained;
          });
          runMessageIds.clear();
          runMessageIds.add(initialAssistantId);
        },
        ...assistantEventCallbacks(event => {
          if (startsVisibleOutput(event)) {
            activeAssistantHasOutput = true;
            setSteeringAssistantId(null);
          }
          const assistantId = activeAssistantId;
          setMessages(previous => previous.map(message => (
            message.id === assistantId ? applyAssistantEvent(message, event) : message
          )));
        }, sandboxScheduleRef, scheduleYamlRef),
        onSteering: (queuedId, queuedMessage) => {
          const runId = eventRouterRef.current.foreground?.runId;
          const createdAt = queuedMessagesRef.current.find(message => message.id === queuedId)?.createdAt ?? Date.now();
          queuedMessagesRef.current = queuedMessagesRef.current.filter(message => message.id !== queuedId);
          setQueuedMessages(queuedMessagesRef.current);
          runMessageIds.add(queuedId);
          const steeringStartedAt = Date.now();
          if (activeAssistantHasOutput) {
            const completedAssistantId = activeAssistantId;
            const nextAssistantId = messageId();
            runMessageIds.add(nextAssistantId);
            setMessages(previous => {
              const completedIndex = previous.findIndex(message => message.id === completedAssistantId);
              const completed = previous.map(message => withActiveAssistant(
                message.id === completedAssistantId
                  ? { ...message, runId, status: undefined, responseCompletedAt: steeringStartedAt }
                  : message, nextAssistantId,
              ));
              const queued: ChatMessage = { id: queuedId, runId, requestId: request.id, role: 'user', content: queuedMessage, createdAt };
              const next: ChatMessage = {
                id: nextAssistantId,
                runId,
                requestId: request.id,
                request: { ...request, activeAssistantId: nextAssistantId },
                role: 'assistant',
                content: '',
                status: 'pending',
                responseStartedAt: steeringStartedAt,
              };
              const position = completedIndex < 0 ? completed.length : completedIndex + 1;
              return [...completed.slice(0, position), queued, next, ...completed.slice(position)];
            });
            activeAssistantId = nextAssistantId;
            setSteeringAssistantId(nextAssistantId);
            activeAssistantHasOutput = false;
          } else {
            const pendingAssistantId = activeAssistantId;
            setMessages(previous => {
              const pendingIndex = previous.findIndex(message => message.id === pendingAssistantId);
              const queued: ChatMessage = { id: queuedId, runId, requestId: request.id, role: 'user', content: queuedMessage, createdAt };
              if (pendingIndex < 0) return [...previous, queued];
              return [
                ...previous.slice(0, pendingIndex),
                queued,
                ...previous.slice(pendingIndex),
              ];
            });
            setSteeringAssistantId(pendingAssistantId);
          }
          activeQuestion = queuedMessage;
          activeQuestionRequiresAttachments = false;
        },
        onDownload: id => setMessages(previous => previous.map(message => message.id === activeAssistantId ? { ...message, downloadId: id } : message)),
        onWarning: setError,
        onModelInput: input => {
          const assistantId = activeAssistantId;
          setMessages(previous => applyModelInput(previous, input, { questionId: userMessage.id, assistantId }));
        },
        onProposal: diff => setProposalDiff(diff),
        onContextUsage: updateContextUsage,
        onHistoryTrimmed: setTrimmedHistoryCount,
      }, () => lifecycle.owns(operation) && !controller.signal.aborted);
      const foreground = eventRouterRef.current.begin(
        event => dispatchPageEvent(event, callbacks), rejectRun,
        () => startSessionEventStream(sessionId, sessionEndpoint, true),
      );
      if (!sessionEvents.connected()) startSessionEventStream(sessionId, sessionEndpoint);
      const aborted = () => finishRun();
      controller.signal.addEventListener('abort', aborted, { once: true });
      try {
        if (attachmentsForMessage.length > 0) {
          const uploaded = await uploadFiles(sessionId, attachmentsForMessage, authToken, sessionEndpoint, controller.signal);
          setUploadedFiles(previous => [...previous, ...uploaded]);
          activeQuestionRequiresAttachments = false;
          request.uploading = false;
          setMessages(previous => previous.map(message => message.request?.id === request.id
            ? { ...message, request: { ...message.request, uploading: false } } : message));
        }
        if (currentRequest.stopped) {
          controller.abort();
          setMessages(previous => previous.map(message => message.id === activeAssistantId ? stopResponse(message) : message));
          finishRun();
          return;
        }
        const runId = await sendMessage(sessionId, question, controller.signal, authToken, sessionEndpoint, {
          messageId: request.id,
          shouldStop: () => currentRequest.stopped,
          onConnectionChange: connected => setIsReconnecting(!connected),
        });
        eventRouterRef.current.acknowledge(foreground, runId, id => {
          setMessages(previous => previous.map(message => runMessageIds.has(message.id)
            ? { ...message, runId: id, requestId: request.id } : message));
        });
        if (!runFinished && lifecycle.getSnapshot().foreground?.phase === 'stopping') {
          // Stop may have reached the server before the message was admitted.
          await stopSession(sessionId, authToken, sessionEndpoint, request.id).catch(stopError => {
            if (!lifecycle.owns(operation)) return;
            lifecycle.stopFailed([operation]);
            reportRequestError(stopError, 'The AI response could not be stopped.');
          });
        }
        await finished;
      } finally {
        controller.signal.removeEventListener('abort', aborted);
        eventRouterRef.current.finish(foreground);
      }
      if (!lifecycle.owns(operation)) return;
      setMessages(previous => previous.map(message => (
        message.id === activeAssistantId
          ? controller.signal.aborted ? stopResponse(message)
            : { ...message, status: undefined, responseCompletedAt: Date.now() }
          : message
      )));
    } catch (streamError) {
      if (!lifecycle.owns(operation)) return;
      const staleTurnMessage = streamError instanceof AiStaleRunError ? streamError.message : null;
      setMessages(previous => previous.map(message => {
        if (message.id !== activeAssistantId) return message;
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
      if (lifecycle.owns(operation)) {
        setMessages(previous => previous.map(message => message.request?.id === request.id
          ? { ...message, request: { ...message.request, active: false } } : message));
        if (currentRequestRef.current === currentRequest) currentRequestRef.current = null;
        setIsReconnecting(false);
        setSteeringAssistantId(null);
        if (abortControllerRef.current === controller) abortControllerRef.current = null;
        lifecycle.finish(operation);
      }
    }
  };

  const sendQueuedMessage = useEffectEvent(() => {
    if (lifecycle.busy || conversationUnavailable) return;
    const next = queuedMessagesRef.current[0];
    if (!next) return;
    queuedMessagesRef.current = queuedMessagesRef.current.slice(1);
    setQueuedMessages(queuedMessagesRef.current);
    void sendRequest(next.content, [], false, next.createdAt);
  });

  useEffect(() => {
    if (!isStreaming && queuedMessages.length > 0) sendQueuedMessage();
  }, [isStreaming, queuedMessages.length]);

  useEffect(() => {
    if (!isClientReady || serverStatus !== 'online' || activeSessionId === null || isStreaming || conversationUnavailable
      || (authRequired && authToken === null)) return;
    const pending = messages.find(message => message.request?.active)?.request;
    if (!pending || resumedRequestRef.current === pending.id) return;
    resumedRequestRef.current = pending.id;
    if (pending.uploading) failInterruptedUpload(pending);
    else void sendRequest(pending.question, [], false, Date.now(), { ...pending, recover: true });
  });

  const submitMessage = async (question: string, attachments: File[]) => {
    if (!question || (authRequired && authToken === null)) return;
    if (isStreaming) {
      const queuedMessage = { id: messageId(), content: question, createdAt: Date.now() };
      queuedMessagesRef.current = [...queuedMessagesRef.current, queuedMessage];
      setQueuedMessages(queuedMessagesRef.current);
      onSendStart('queue');
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
    await sendRequest(question, attachments, true);
  };

  const retryMessage = (failedId: string, question: string) => {
    if (!question || isStreaming || (authRequired && authToken === null)) return;
    const failedIndex = messages.findIndex(message => message.id === failedId);
    const original = messages.slice(0, failedIndex).reverse().find(message => message.role === 'user' && message.source === undefined);
    if (!original) return;
    void sendRequest(question, [], false, original.createdAt, { id: messageId(), questionId: original.id, assistantId: failedId });
  };

  const failInterruptedUpload = (pending: NonNullable<ChatMessage['request']>) => {
    setMessages(previous => previous.map(message => ({
      ...message,
      ...(message.request?.id === pending.id ? { request: { ...message.request, active: false } } : {}),
      ...(message.id === pending.assistantId ? {
        status: 'failed' as const, responseCompletedAt: Date.now(), request: { ...pending, active: false },
        retry: { question: pending.question, requiresAttachments: true },
      } : {}),
    })));
  };

  const stop = () => {
    if (isStopping) return;
    const stopping = lifecycle.stop();
    if (currentRequestRef.current) currentRequestRef.current.stopped = true;
    queuedMessagesRef.current = [];
    setQueuedMessages([]);
    const sessionId = sessionIdRef.current;
    if (sessionId === null) {
      abortControllerRef.current?.abort();
      return;
    }
    // The request only asks the server to stop. The turn keeps running until a terminal
    // event reports it ended, so every one of those clears the pending state instead.
    void stopSession(sessionId, authToken, sessionEndpointRef.current ?? aiEndpoint, currentRequestRef.current?.id)
      .catch(stopError => {
        if (!stopping.some(operation => lifecycle.owns(operation))) return;
        reportRequestError(stopError, 'The AI response could not be stopped.');
        lifecycle.stopFailed(stopping);
      });
  };

  const removeGeneratedFiles = async (downloadId: string) => {
    const sessionId = sessionIdRef.current;
    if (!sessionId || removingDownloadId !== null) return;
    setRemovingDownloadId(downloadId);
    try {
      await removeGeneratedZip(sessionId, downloadId, authToken, sessionEndpointRef.current ?? aiEndpoint);
      if (sessionIdRef.current === sessionId) {
        setMessages(previous => previous.map(message => (
          message.downloadId === downloadId ? { ...message, downloadId: undefined } : message
        )));
        renewSessionExpiration();
      }
    } catch (downloadError) {
      reportRequestError(downloadError, 'The generated ZIP could not be removed.');
    } finally {
      setRemovingDownloadId(null);
    }
  };

  const applyProposal = async () => {
    const sessionId = sessionIdRef.current;
    if (sessionId === null || proposalDiff === null) return;
    const ownsConversation = lifecycle.capture();
    const baseSchedule = scheduleYaml;
    setIsApplyingProposal(true);
    setError(null);
    try {
      const { scheduleYaml: approvedYaml, historySaved } = await approveProposal(
        sessionId,
        scheduleYaml,
        authToken,
        sessionEndpointRef.current ?? aiEndpoint,
      );
      if (!ownsConversation()) return;
      if (scheduleYamlRef.current !== baseSchedule) {
        setProposalDiff(null);
        setProposalNotice('The schedule changed while approval was pending. The proposal was not applied.');
        return;
      }
      // One import call is one history entry, so undo reverts the whole proposal.
      onApplySchedule(approvedYaml);
      syncedScheduleRef.current = approvedYaml;
      renewSessionExpiration();
      setProposalDiff(null);
      setProposalNotice('The proposed schedule was applied. Undo reverts it in one step.');
      if (!historySaved) setError(UNSAVED_APPROVAL_WARNING);
    } catch (approveError) {
      if (ownsConversation()) reportRequestError(approveError, 'The proposal could not be applied.');
    } finally {
      if (ownsConversation()) setIsApplyingProposal(false);
    }
  };

  const discardProposal = async () => {
    const sessionId = sessionIdRef.current;
    const ownsConversation = lifecycle.capture();
    setProposalDiff(null);
    setProposalNotice(null);
    if (sessionId === null) return;
    try {
      const historySaved = await rejectProposal(sessionId, authToken, sessionEndpointRef.current ?? aiEndpoint);
      if (!ownsConversation()) return;
      renewSessionExpiration();
      if (!historySaved) setError(UNSAVED_REJECTION_WARNING);
    } catch (rejectError) {
      if (ownsConversation() && isAuthenticationError(rejectError)) {
        reportRequestError(rejectError, 'The proposal could not be rejected.');
      }
    }
  };

  const restoreConversation = useCallback((storedConversation: StoredChatConversation) => {
      // Replayed events reconcile onto the unfinished background message by ID, so
      // restore it before the stream opens. Its tools stopped with the old page.
      if (storedConversation.backgroundAssistantId) {
        lifecycle.begin('background', storedConversation.backgroundAssistantId, 'interrupted');
      }
      setMessages(storedConversation.messages.map(message => (
        message.status === 'pending' && !message.requestId
          ? { ...message, status: 'failed' as const, activity: interruptRunningTools(message.activity ?? []) }
          : message
      )));
      setProposalDiff(storedConversation.proposalDiff);
      setSessionRetentionSeconds(storedConversation.retentionSeconds);
      lastSessionEventIdRef.current = storedConversation.sessionEventId ?? 0;
      setContextUsage(storedConversation.contextUsage ?? null);
      setActiveOptimization(storedConversation.activeOptimization
        ? { ...storedConversation.activeOptimization, points: storedConversation.activeOptimization.points ?? [] }
        : null);
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
        // The trim lasts as long as the conversation, but the event announcing it sits
        // behind the stored cursor and never replays, so restore the warning directly.
        // An expired chat sends nothing at all, so it keeps the transcript without it.
        setTrimmedHistoryCount(storedConversation.trimmedHistoryCount ?? 0);
      }
  }, [lifecycle, lastSessionEventIdRef]);

  useEffect(() => () => {
    lifecycle.reset();
    abortControllerRef.current?.abort();
  }, [lifecycle]);

  const newConversation = () => {
    resetRuntime();
    setMessages([]);
    setContextUsage(null);
    setTrimmedHistoryCount(0);
    setProposalNotice(null);
    setConversationUnavailable(false);
    setSessionNotice(null);
    setError(null);
    window.sessionStorage.removeItem(AI_CONVERSATION_STORAGE_KEY);
  };
  const captureSession = () => sessionIdRef.current === null ? null : ({
    id: sessionIdRef.current,
    endpoint: sessionEndpointRef.current ?? aiEndpoint,
    ownsConversation: lifecycle.capture(),
  });
  return {
    messages, uploadedFiles, removingUploadId, removingDownloadId, contextUsage,
    activeSessionId, sessionExpiresAt, sessionRetentionSeconds, conversationUnavailable,
    sessionNotice, trimmedHistoryCount, isStreaming, isStopping, isReconnecting,
    activeOptimization, queuedMessages, steeringAssistantId, proposalDiff, proposalNotice, isApplyingProposal,
    setSessionRetentionSeconds, restoreConversation, captureSession,
    newConversation, submitMessage, retryMessage, stop, removeUploadedFile,
    removeGeneratedFiles, applyProposal, discardProposal,
    sessionEndpoint: sessionEndpointRef.current ?? aiEndpoint,
  };
}
