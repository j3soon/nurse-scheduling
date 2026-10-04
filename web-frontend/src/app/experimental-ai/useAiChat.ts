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

import { useCallback, useEffect, useEffectEvent, useRef, useState, useSyncExternalStore } from 'react';
import type { Dispatch, SetStateAction } from 'react';
import type { OptimizationProgressPoint } from '@/components/OptimizationProgressChart';
import {
  AiHttpError, AiStaleRunError, DEFAULT_SESSION_RETENTION_SECONDS,
  type ContextUsage, type OptimizationActivity,
  approveProposal, createSession, getSessionStatus, isAuthenticationError, queueMessage,
  rejectProposal, sendMessage, stopSession, updateSessionSchedule,
} from './aiClient';
import {
  type AssistantEvent, applyAssistantEvent, messageId, toAssistantEvent,
} from './assistantEvents';
import { type ChatMessage, applyResponseEvent, beginResponse, createResponse, resetRunMessages, restoreTranscript, steerResponse } from './chatTranscript';
import { ChatLifecycle, scopedEventHandler } from './chatLifecycle';
import { SessionEventRouter } from './sessionEventRouter';
import type { SessionEvent, SessionEventHandler } from './sessionEvents';
import { useSessionEventStream } from './useSessionEventStream';

export type { ChatMessage } from './chatTranscript';

export interface ActiveOptimization extends OptimizationActivity {
  points: OptimizationProgressPoint[];
}

/** Conversation data for tab storage. Browser I/O stays in the page. */
export interface ChatConversation {
  sessionId: string;
  endpoint: string;
  expiresAt: number;
  retentionSeconds: number;
  messages: ChatMessage[];
  syncedSchedule: string;
  proposalDiff: string | null;
  sessionEventId?: number;
  activeOptimization?: ActiveOptimization | null;
  contextUsage?: ContextUsage | null;
  backgroundAssistantId?: string | null;
  trimmedHistoryCount?: number;
}

export function retentionLabel(seconds: number): string {
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return `${hours} ${hours === 1 ? 'hour' : 'hours'}`;
  }
  return `${seconds.toLocaleString()} seconds`;
}

function expiryNotice(seconds: number): string {
  return `This chat expired after ${retentionLabel(seconds)} of inactivity. Start a new chat to continue.`;
}

interface QueuedChatMessage {
  createdAt: number;
  id: string;
  content: string;
}

// A solver can emit a progress event per incumbent solution, and the whole series is
// persisted with the conversation. Halving the oldest points keeps the sparkline shape
// while bounding the array and the tab storage a long run consumes.
const OPTIMIZATION_PROGRESS_POINT_LIMIT = 500;

function optimizationMessage(activity: OptimizationActivity): string {
  const summary = activity.state === 'completed'
    ? activity.downloadable
      ? 'Optimization finished. Download the optimized schedule to review it.'
      : 'Optimization finished, but no result workbook is available to download.'
    : `Optimization ended with status: ${activity.state}.`;
  const details: string[] = [];
  const add = (label: string, value: string | number | undefined) => {
    // Indent continuation lines so field values cannot introduce another label.
    if (value !== undefined) details.push(`${label}: ${String(value).replace(/\r\n?|\n/g, '\n ')}`);
  };
  add('Outcome', activity.result?.outcome);
  add('Final score', activity.result?.score);
  add('Solver', activity.request?.solver);
  add('Solver status', activity.result?.solverStatus);
  add('Termination reason', activity.result?.terminationReason);
  if (activity.request?.timeoutSeconds !== undefined) add('Solver timeout', `${activity.request.timeoutSeconds}s`);
  if (activity.backend) {
    add('Backend URL', activity.backend.url ?? 'unknown');
    add('Backend version', activity.backend.appVersion ?? 'unknown');
    add('API version', activity.backend.apiVersion);
    add('Service', activity.backend.serviceName);
    add('Deployment', activity.backend.deploymentId);
    add('Instance', activity.backend.instanceId);
    if (activity.backend.requestTimeoutSeconds !== undefined) {
      add('Backend request timeout', `${activity.backend.requestTimeoutSeconds}s`);
    }
    const claimed = activity.backend.claimedPerformance;
    add('Claimed performance', claimed ? `${claimed.score} (version ${claimed.appVersion}, measured ${claimed.measuredAt})` : 'unavailable');
  }
  add('Error code', activity.error?.code);
  add('Error', activity.error?.message);
  return [summary, ...details].join('\n');
}

// Output that closes a steering placeholder, so queued input starts a new response.
function startsVisibleOutput(event: AssistantEvent): boolean {
  if (event.type === 'delta' || event.type === 'reasoning') return event.text.length > 0;
  return event.type === 'tool_start';
}

interface AiChatOptions {
  scheduleYaml: string;
  aiEndpoint: string;
  authRequired: boolean;
  authToken: string | null;
  isClientReady: boolean;
  setError: Dispatch<SetStateAction<string | null>>;
  reportRequestError: (error: unknown, fallback: string) => void;
  onSendStart: (clearComposer: boolean) => void;
  onUnavailable: () => void;
  onApplySchedule: (scheduleYaml: string) => void;
}

/** Chat control over the existing run lifecycle and session event router. */
export function useAiChat({
  scheduleYaml, aiEndpoint, authRequired, authToken, isClientReady,
  setError, reportRequestError, onSendStart, onUnavailable, onApplySchedule,
}: AiChatOptions) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [contextUsage, setContextUsage] = useState<ContextUsage | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionExpiresAt, setSessionExpiresAt] = useState<number | null>(null);
  const [sessionRetentionSeconds, setSessionRetentionSeconds] = useState(DEFAULT_SESSION_RETENTION_SECONDS);
  const [conversationUnavailable, setConversationUnavailable] = useState(false);
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
  const [trimmedHistoryCount, setTrimmedHistoryCount] = useState(0);
  const [lifecycle] = useState(() => new ChatLifecycle());
  const [activeOptimization, setActiveOptimization] = useState<ActiveOptimization | null>(null);
  const [queuedMessages, setQueuedMessages] = useState<QueuedChatMessage[]>([]);
  const [steeringAssistantId, setSteeringAssistantId] = useState<string | null>(null);
  const [proposalDiff, setProposalDiff] = useState<string | null>(null);
  const [proposalNotice, setProposalNotice] = useState<string | null>(null);
  const [isApplyingProposal, setIsApplyingProposal] = useState(false);
  const operations = useSyncExternalStore(lifecycle.subscribe, lifecycle.getSnapshot, lifecycle.getSnapshot);
  const isStreaming = Object.values(operations).some(active => active !== null && active.phase !== 'interrupted');
  const isStopping = Object.values(operations).some(active => active?.phase === 'stopping');
  const syncedScheduleRef = useRef<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const sessionEndpointRef = useRef<string | null>(null);
  const checkedSessionRef = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const eventRouterRef = useRef(new SessionEventRouter());
  const scheduleYamlRef = useRef(scheduleYaml);
  const sandboxScheduleRef = useRef<string | null>(null);
  const queuedMessagesRef = useRef<QueuedChatMessage[]>([]);
  const sessionEvents = useSessionEventStream();
  scheduleYamlRef.current = scheduleYaml;
  const reset = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    sessionEvents.reset();
    sessionIdRef.current = null;
    sessionEndpointRef.current = null;
    checkedSessionRef.current = null;
    syncedScheduleRef.current = null;
    sandboxScheduleRef.current = null;
    queuedMessagesRef.current = [];
    lifecycle.reset();
    setActiveSessionId(null);
    setSessionExpiresAt(null);
    setQueuedMessages([]);
    setActiveOptimization(null);
    setProposalDiff(null);
    setIsApplyingProposal(false);
  }, [lifecycle, sessionEvents]);
  useEffect(() => () => {
    lifecycle.reset();
    abortControllerRef.current?.abort();
  }, [lifecycle]);

  const renewSessionExpiration = () => {
    setSessionExpiresAt(Date.now() + sessionRetentionSeconds * 1000);
  };

  const markConversationUnavailable = useCallback((notice: string) => {
    reset();
    setConversationUnavailable(true);
    setSessionNotice(notice);
    onUnavailable();
  }, [reset, onUnavailable]);

  const restore = useCallback((conversation: ChatConversation) => {
    reset();
    // Replayed events reconcile onto the unfinished background message by ID, so
    // restore it before the stream opens. Its tools stopped with the old page.
    if (conversation.backgroundAssistantId) {
      lifecycle.begin('background', conversation.backgroundAssistantId, 'interrupted');
    }
    setMessages(restoreTranscript(conversation.messages));
    setProposalDiff(conversation.proposalDiff);
    setSessionRetentionSeconds(conversation.retentionSeconds);
    sessionEvents.cursor.current = conversation.sessionEventId ?? 0;
    setContextUsage(conversation.contextUsage ?? null);
    setActiveOptimization(conversation.activeOptimization
      ? { ...conversation.activeOptimization, points: conversation.activeOptimization.points ?? [] }
      : null);
    syncedScheduleRef.current = conversation.syncedSchedule;
    sessionEndpointRef.current = conversation.endpoint;
    if (conversation.expiresAt <= Date.now()) {
      setConversationUnavailable(true);
      setSessionNotice(expiryNotice(conversation.retentionSeconds));
      onUnavailable();
    } else {
      sessionIdRef.current = conversation.sessionId;
      setActiveSessionId(conversation.sessionId);
      setSessionExpiresAt(conversation.expiresAt);
      setConversationUnavailable(false);
      setSessionNotice(null);
      // The trim lasts as long as the conversation, but its event sits behind the
      // stored cursor. An expired chat keeps the transcript without this warning.
      setTrimmedHistoryCount(conversation.trimmedHistoryCount ?? 0);
    }
  }, [reset, lifecycle, sessionEvents, onUnavailable]);

  const snapshot = useCallback((): ChatConversation | null => {
    if (activeSessionId === null || sessionExpiresAt === null || sessionIdRef.current !== activeSessionId) return null;
    return {
      sessionId: activeSessionId,
      endpoint: sessionEndpointRef.current ?? aiEndpoint,
      expiresAt: sessionExpiresAt,
      retentionSeconds: sessionRetentionSeconds,
      messages,
      syncedSchedule: syncedScheduleRef.current ?? scheduleYaml,
      proposalDiff,
      sessionEventId: sessionEvents.cursor.current,
      activeOptimization,
      contextUsage,
      backgroundAssistantId: operations.background?.token.id,
      trimmedHistoryCount,
    };
  }, [activeSessionId, sessionExpiresAt, aiEndpoint, sessionRetentionSeconds, messages,
    scheduleYaml, proposalDiff, sessionEvents, activeOptimization, contextUsage,
    operations.background, trimmedHistoryCount]);

  const clearConversation = useCallback(() => {
    reset();
    setMessages([]);
    setContextUsage(null);
    setTrimmedHistoryCount(0);
    setProposalNotice(null);
    setConversationUnavailable(false);
    setSessionNotice(null);
  }, [reset]);

  const captureConversation = useCallback(() => lifecycle.capture(), [lifecycle]);

  useEffect(() => {
    if (!isClientReady || activeSessionId === null || checkedSessionRef.current === activeSessionId) return;
    checkedSessionRef.current = activeSessionId;
    const ownsConversation = lifecycle.capture();
    getSessionStatus(activeSessionId, authToken, sessionEndpointRef.current ?? aiEndpoint)
      .then(expiresInSeconds => {
        if (!ownsConversation() || sessionIdRef.current !== activeSessionId) return;
        setSessionExpiresAt(Date.now() + expiresInSeconds * 1000);
      })
      .catch((statusError: unknown) => {
        if (!ownsConversation() || sessionIdRef.current !== activeSessionId) return;
        if (statusError instanceof AiHttpError && statusError.status === 404) {
          markConversationUnavailable('This chat is no longer available on the AI server. Start a new chat to continue.');
        } else {
          checkedSessionRef.current = null;
          reportRequestError(statusError, 'The stored AI chat could not be checked.');
        }
      });
  }, [activeSessionId, aiEndpoint, authToken, isClientReady, lifecycle,
    reportRequestError, markConversationUnavailable]);

  useEffect(() => {
    if (activeSessionId === null || sessionExpiresAt === null) return;
    const expire = () => markConversationUnavailable(expiryNotice(sessionRetentionSeconds));
    const delay = sessionExpiresAt - Date.now();
    if (delay <= 0) {
      expire();
      return;
    }
    const timeout = window.setTimeout(expire, delay);
    return () => window.clearTimeout(timeout);
  }, [activeSessionId, sessionExpiresAt, sessionRetentionSeconds, markConversationUnavailable]);

  const projectSessionState = useCallback((event: SessionEvent): boolean => {
    switch (event.type) {
      case 'proposal': setProposalDiff(event.diff); return true;
      case 'context_usage': setContextUsage(event.usage); return true;
      case 'history_trimmed': setTrimmedHistoryCount(event.dropped); return true;
      default: return false;
    }
  }, []);

  const startSessionEventStream = useCallback((sessionId: string, endpoint: string) => {
    if (sessionEvents.connected()) return;
    // One background run occupies one UI answer, keyed by its run ID.
    const beginBackgroundMessage = (runId: string) => {
      lifecycle.begin('background', runId);
      // The server renews the session when it starts this run.
      setSessionExpiresAt(Date.now() + sessionRetentionSeconds * 1000);
      sandboxScheduleRef.current = scheduleYamlRef.current;
      setMessages(previous => beginResponse(previous, createResponse(runId, Date.now(), runId)));
    };
    // A reconnect replays only retained events, so a long run can lose its own
    // run_start. Adopt the remaining output instead of discarding the answer.
    const resumeBackgroundMessage = () => {
      if (lifecycle.getSnapshot().background?.phase !== 'interrupted' && lifecycle.current('background')) return;
      beginBackgroundMessage(lifecycle.current('background')?.id ?? messageId());
    };
    const updateBackgroundMessage = (event: AssistantEvent, messageId?: string) => {
      const activeId = lifecycle.current('background')?.id ?? messageId;
      if (activeId === undefined) return;
      setMessages(previous => applyResponseEvent(previous, activeId, event, Date.now()));
    };
    const ownsConversation = lifecycle.capture();
    const handleBackground: SessionEventHandler = event => {
      if (projectSessionState(event)) return;
      const output = toAssistantEvent(event, sandboxScheduleRef, scheduleYamlRef);
      if (output) {
        resumeBackgroundMessage();
        updateBackgroundMessage(output);
        return;
      }
      switch (event.type) {
        case 'session_reset': {
          const { reset } = event;
          setMessages(previous => resetRunMessages(previous, reset.runIds));
          setProposalDiff(reset.proposalDiff);
          setActiveOptimization(null);
          lifecycle.finish(lifecycle.current('background'));

          if (reset.incomplete) setSessionNotice('Some earlier response output expired from event replay.');
          break;
        }
        case 'run_context': {
          const id = event.runId;
          if (lifecycle.current('background')?.id !== id) beginBackgroundMessage(id);
          break;
        }
        case 'run_start': {
          beginBackgroundMessage(event.runId);
          break;
        }
        case 'steering': {
          const { messageId: queuedId, message: content } = event;
          const runId = lifecycle.current('background')?.id;
          if (!runId) return;
          setMessages(previous => {
            if (previous.some(message => message.id === queuedId)) return previous;
            const answer = previous.find(message => message.id === runId);
            const now = Date.now();
            const user: ChatMessage = { id: queuedId, runId, role: 'user', content, createdAt: now };
            const continuationId = answer && (answer.content || answer.activity?.length) ? runId : undefined;
            return steerResponse(previous, runId, user, now, continuationId, `${runId}:${queuedId}`);
          });
          break;
        }
        case 'optimization': {
          const { activity } = event;
          if (!activity.terminal) {
            setActiveOptimization(current => ({
              ...activity,
              points: current?.jobId === activity.jobId ? current.points : [],
            }));
            return;
          }
          setActiveOptimization(current => current?.jobId === activity.jobId ? null : current);
          const content = optimizationMessage(activity);
          setMessages(previous => previous.some(message => message.id === `optimizer-${activity.jobId}`)
            ? previous
            : [
              ...previous,
              {
                id: `optimizer-${activity.jobId}`,
                role: 'optimizer',
                createdAt: Date.now(),
                content,
                optimizerJob: { jobId: activity.jobId, downloadable: activity.downloadable },
              },
            ]);
          break;
        }
        case 'optimization_progress': {
          const { jobId, point } = event.activity;
          setActiveOptimization(current => {
            if (current !== null && current.jobId !== jobId) return current;
            const previous = current?.points ?? [];
            const last = previous.at(-1);
            if (last?.elapsedSeconds === point.elapsedSeconds && last.currentBestScore === point.currentBestScore) {
              return current;
            }
            const retained = previous.length >= OPTIMIZATION_PROGRESS_POINT_LIMIT
              ? previous.filter((_, index) => index % 2 === 0 || index === previous.length - 1)
              : previous;
            return {
              jobId,
              state: current?.state ?? 'running',
              terminal: false,
              downloadable: false,
              points: [...retained, point],
            };
          });
          break;
        }
        case 'done': case 'stopped': case 'stale': case 'error': {
          updateBackgroundMessage(event, event.runId);
          lifecycle.finish(lifecycle.current('background'));
          if (event.type === 'stale' || event.type === 'error') setError(event.message);
          break;
        }
      }
    };
    const handle: SessionEventHandler = event => eventRouterRef.current.dispatch(event, handleBackground, ownsConversation);
    sessionEvents.connect(sessionId, handle, authToken, endpoint, (streamError, firstFailure) => {
      if (firstFailure) reportRequestError(streamError, 'The AI session event stream disconnected.');
      if (streamError instanceof AiHttpError && streamError.status === 404) {
        eventRouterRef.current.foreground?.reject(streamError);
      }
    });
  }, [authToken, lifecycle, reportRequestError, sessionEvents, sessionRetentionSeconds, setError, projectSessionState]);

  useEffect(() => {
    if (!isClientReady || activeSessionId === null || conversationUnavailable) return;
    startSessionEventStream(activeSessionId, sessionEndpointRef.current ?? aiEndpoint);
  }, [activeSessionId, aiEndpoint, conversationUnavailable, isClientReady, startSessionEventStream]);

  const sendRequest = async (
    question: string,
    files: File[],
    clearComposer: boolean,
    createdAt = Date.now(),
  ) => {
    if (!question || lifecycle.busy || conversationUnavailable || (authRequired && authToken === null)) return;

    const userMessage: ChatMessage = {
      id: messageId(),
      role: 'user',
      createdAt,
      content: question,
      attachmentNames: files.map(file => file.name),
    };
    const initialAssistantId = messageId();
    let activeAssistantId = initialAssistantId;
    const runMessageIds = new Set([initialAssistantId]);
    let activeAssistantHasOutput = false;
    let activeQuestion = question;
    let activeQuestionRequiresAttachments = files.length > 0;
    const responseStartedAt = Date.now();
    setMessages(previous => [
      ...previous,
      userMessage,
      createResponse(activeAssistantId, responseStartedAt),
    ]);
    onSendStart(clearComposer);
    setError(null);
    setProposalDiff(null);
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
      } else if (syncedScheduleRef.current !== scheduleYaml) {
        // The schedule can change elsewhere in the app between questions.
        await updateSessionSchedule(sessionId, scheduleYaml, authToken, sessionEndpoint);
      }
      if (!lifecycle.owns(operation)) return;
      controller.signal.throwIfAborted();
      syncedScheduleRef.current = scheduleYaml;
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
      const handle = scopedEventHandler(event => {
        if (projectSessionState(event)) return;
        const output = toAssistantEvent(event, sandboxScheduleRef, scheduleYamlRef);
        if (output) {
          if (startsVisibleOutput(output)) {
            activeAssistantHasOutput = true;
            setSteeringAssistantId(null);
          }
          const assistantId = activeAssistantId;
          setMessages(previous => applyResponseEvent(previous, assistantId, output, Date.now()));
          return;
        }
        switch (event.type) {
          case 'done': {
            finishRun();
            break;
          }
          case 'stopped': {
            controller.abort(); finishRun();
            break;
          }
          case 'error': {
            rejectRun(new Error(event.message));
            break;
          }
          case 'stale': {
            rejectRun(new AiStaleRunError(event.message));
            break;
          }
          case 'session_reset': {
            const runId = eventRouterRef.current.foreground?.runId;
            activeAssistantId = initialAssistantId;
            activeAssistantHasOutput = false;
            activeQuestion = question;
            const recoveredMessageIds = new Set(runMessageIds);
            setMessages(previous => resetRunMessages(
              previous, [], createResponse(initialAssistantId, responseStartedAt, runId), recoveredMessageIds,
            ));
            runMessageIds.clear();
            runMessageIds.add(initialAssistantId);
            break;
          }
          case 'steering': {
            const { messageId: queuedId, message: queuedMessage } = event;
            const runId = eventRouterRef.current.foreground?.runId;
            const createdAt = queuedMessagesRef.current.find(message => message.id === queuedId)?.createdAt ?? Date.now();
            queuedMessagesRef.current = queuedMessagesRef.current.filter(message => message.id !== queuedId);
            setQueuedMessages(queuedMessagesRef.current);
            runMessageIds.add(queuedId);
            const steeringStartedAt = Date.now();
            const previousAssistantId = activeAssistantId;
            const nextAssistantId = activeAssistantHasOutput ? messageId() : undefined;
            if (nextAssistantId) runMessageIds.add(nextAssistantId);
            setMessages(previous => steerResponse(
              previous,
              previousAssistantId,
              { id: queuedId, runId, role: 'user', content: queuedMessage, createdAt },
              steeringStartedAt,
              nextAssistantId,
            ));
            activeAssistantId = nextAssistantId ?? previousAssistantId;
            setSteeringAssistantId(activeAssistantId);
            activeAssistantHasOutput = false;
            activeQuestion = queuedMessage;
            activeQuestionRequiresAttachments = false;
            break;
          }
        }
      }, () => lifecycle.owns(operation) && !controller.signal.aborted);
      const foreground = eventRouterRef.current.begin(handle, rejectRun);
      const aborted = () => finishRun();
      controller.signal.addEventListener('abort', aborted, { once: true });
      try {
        const runId = await sendMessage(
          sessionId,
          question,
          controller.signal,
          authToken,
          {
            files,
          },
          sessionEndpoint,
        );
        eventRouterRef.current.acknowledge(foreground, runId, acceptedId => {
          setMessages(previous => previous.map(message => runMessageIds.has(message.id)
            ? { ...message, runId: acceptedId } : message));
        });
        if (!runFinished && lifecycle.getSnapshot().foreground?.phase === 'stopping') {
          // Stop may have reached the server before the message was accepted.
          await stopSession(sessionId, authToken, sessionEndpoint).catch(stopError => {
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
      setMessages(previous => applyResponseEvent(
        previous, activeAssistantId, { type: controller.signal.aborted ? 'stopped' : 'done' }, Date.now(),
      ));
    } catch (streamError) {
      if (!lifecycle.owns(operation)) return;
      const staleRunMessage = streamError instanceof AiStaleRunError ? streamError.message : null;
      setMessages(previous => previous.map(message => {
        if (message.id !== activeAssistantId) return message;
        if (controller.signal.aborted) return applyAssistantEvent(message, { type: 'stopped' });
        return {
          ...applyAssistantEvent(message, staleRunMessage === null
            ? { type: 'error', message: '' } : { type: 'stale', message: staleRunMessage }),
          retry: {
            question: activeQuestion,
            requiresAttachments: activeQuestionRequiresAttachments,
          },
        };
      }));
      if (streamError instanceof AiHttpError && streamError.status === 404) {
        markConversationUnavailable('This chat expired or is no longer available. Start a new chat to continue.');
      } else if (!controller.signal.aborted && staleRunMessage === null) {
        reportRequestError(streamError, 'The AI request failed.');
      }
    } finally {
      if (lifecycle.owns(operation)) {
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

  const queue = async (question: string) => {
    const queuedMessage = { id: messageId(), content: question, createdAt: Date.now() };
    queuedMessagesRef.current = [...queuedMessagesRef.current, queuedMessage];
    setQueuedMessages(queuedMessagesRef.current);
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
  };

  const retryMessage = (failedId: string, question: string) => {
    if (!question || isStreaming || (authRequired && authToken === null)) return;
    // The retried run replaces the failed pair, so the question is not repeated.
    setMessages(previous => {
      const failedIndex = previous.findIndex(message => message.id === failedId);
      if (failedIndex < 0) return previous;
      const start = previous[failedIndex - 1]?.role === 'user' ? failedIndex - 1 : failedIndex;
      return [...previous.slice(0, start), ...previous.slice(failedIndex + 1)];
    });
    void sendRequest(question, [], false);
  };

  const stop = () => {
    if (isStopping) return;
    const stopping = lifecycle.stop();
    queuedMessagesRef.current = [];
    setQueuedMessages([]);
    const sessionId = sessionIdRef.current;
    if (sessionId === null) {
      abortControllerRef.current?.abort();
      return;
    }
    // The request only asks the server to stop. The run stays active until a terminal
    // event reports it ended, so every one of those clears the pending state instead.
    void stopSession(sessionId, authToken, sessionEndpointRef.current ?? aiEndpoint)
      .catch(stopError => {
        if (!stopping.some(operation => lifecycle.owns(operation))) return;
        reportRequestError(stopError, 'The AI response could not be stopped.');
        lifecycle.stopFailed(stopping);
      });
  };

  const applyProposal = async () => {
    const sessionId = sessionIdRef.current;
    if (sessionId === null || proposalDiff === null) return;
    const ownsConversation = lifecycle.capture();
    const baseSchedule = scheduleYaml;
    setIsApplyingProposal(true);
    setError(null);
    try {
      const approvedYaml = await approveProposal(
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
      await rejectProposal(sessionId, authToken, sessionEndpointRef.current ?? aiEndpoint);
      if (!ownsConversation()) return;
      renewSessionExpiration();
    } catch (rejectError) {
      if (ownsConversation() && isAuthenticationError(rejectError)) {
        reportRequestError(rejectError, 'The proposal could not be rejected.');
      }
    }
  };

  return {
    messages,
    contextUsage,
    activeSessionId,
    sessionExpiresAt,
    sessionRetentionSeconds,
    configureRetention: setSessionRetentionSeconds,
    conversationUnavailable,
    sessionNotice,
    trimmedHistoryCount,
    isStreaming,
    isStopping,
    activeOptimization,
    queuedMessages,
    steeringAssistantId,
    backgroundAssistantId: operations.background?.token.id,
    proposalDiff,
    proposalNotice,
    isApplyingProposal,
    sessionEndpoint: sessionEndpointRef.current ?? aiEndpoint,
    snapshot,
    restore,
    clearConversation,
    captureConversation,
    sendRequest,
    queue,
    retryMessage,
    stop,
    applyProposal,
    discardProposal,
  };
}
