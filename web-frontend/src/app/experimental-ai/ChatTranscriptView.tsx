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

import { FiDownload } from 'react-icons/fi';

import { AssistantActivity } from './AssistantActivity';
import CollapsedText from './CollapsedText';
import { messageLabel } from './chatExport';
import { formatResponseDuration, formatResponseTime, formatSessionExpiration, retentionLabel } from './chatPresentation';
import { parseOptimizerMessage } from './optimizerMessage';

import type { ChatMessage } from './chatTranscript';

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

interface ChatTranscriptViewProps {
  messages: ChatMessage[];
  showReasoning: boolean;
  showTools: boolean;
  steeringAssistantId: string | null;
  isStreaming: boolean;
  conversationUnavailable: boolean;
  removingDownloadId: string | null;
  downloadingOptimizationId: string | null;
  retryMessage: (id: string, question: string) => void;
  prepareAttachmentRetry: (question: string) => void;
  downloadGeneratedFiles: (id: string) => Promise<void>;
  removeGeneratedFiles: (id: string) => Promise<void>;
  downloadOptimizationResult: (id: string) => Promise<void>;
  activeSessionId: string | null;
  sessionExpiresAt: number | null;
  sessionRetentionSeconds: number;
}

/** Render the transcript with the same activity and retry rules as the page. */
export function ChatTranscriptView({
  messages,
  showReasoning,
  showTools,
  steeringAssistantId,
  isStreaming,
  conversationUnavailable,
  removingDownloadId,
  downloadingOptimizationId,
  retryMessage,
  prepareAttachmentRetry,
  downloadGeneratedFiles,
  removeGeneratedFiles,
  downloadOptimizationResult,
  activeSessionId,
  sessionExpiresAt,
  sessionRetentionSeconds,
}: ChatTranscriptViewProps) {
  return (
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
        {messages.map(message => {
          const timestamp = message.responseCompletedAt ?? message.createdAt;
          const optimizer = message.role === 'optimizer' ? parseOptimizerMessage(message.content) : null;
          return (
            <article
              key={message.id}
              className={`rounded-xl px-4 py-3 ${
                message.role === 'system'
                  ? 'border border-dashed border-gray-300 bg-gray-50 text-gray-700'
                  : message.role === 'user' && message.source === undefined
                    ? 'ml-auto max-w-[85%] bg-blue-600 text-white'
                    : message.source === 'optimizer'
                      // Optimizer messages align left like the optimizer notice, in the chat and in exports.
                      ? 'mr-auto max-w-[85%] border border-emerald-200 bg-emerald-50 text-emerald-950'
                      : message.role === 'user'
                        ? 'ml-auto max-w-[85%] border border-blue-200 bg-blue-50 text-blue-950'
                        : message.role === 'optimizer'
                          ? 'mr-auto max-w-[85%] border border-emerald-200 bg-emerald-50 text-emerald-950'
                          : 'mr-auto max-w-[85%] border border-gray-200 bg-white text-gray-900'
              }`}
            >
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide opacity-70">{messageLabel(message)}</p>
              {message.activity && (
                <AssistantActivity
                  entries={message.activity.filter(entry => (
                    entry.kind === 'response' || (entry.kind === 'reasoning' ? showReasoning : showTools)
                  ))}
                />
              )}
              {message.role === 'assistant' && !message.content && message.status === 'pending' ? (
                steeringAssistantId === message.id ? <p className="text-xs text-gray-500">Steering…</p> : <ThinkingIndicator />
              ) : message.role === 'system' ? (
                <CollapsedText summary={`${message.content.length.toLocaleString('en-US')} characters`} text={message.content} />
              ) : message.source !== undefined ? (
                // The label names the topic, so the exact text starts collapsed.
                <CollapsedText summary={`${message.content.length.toLocaleString('en-US')} characters`} text={message.content} />
              ) : message.role === 'user' ? (
                <p className="whitespace-pre-wrap break-words">{message.content}</p>
              ) : optimizer ? (
                <>
                  <p className="whitespace-pre-wrap break-words">{optimizer.summary}</p>
                  {optimizer.details.length > 0 && (
                    <dl className="mt-3 grid gap-1.5 text-sm">
                      {optimizer.details.map(({ label, value }, index) => (
                        <div key={`${label}-${index}`} className="min-w-0 [overflow-wrap:anywhere]">
                          <dt className="inline font-semibold">{label}:</dt>{' '}
                          <dd className="inline whitespace-pre-wrap">{value}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </>
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
              {message.downloadId && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <button type="button" onClick={() => void downloadGeneratedFiles(message.downloadId!)}
                    disabled={removingDownloadId === message.downloadId}
                    className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50">
                    Download files (ZIP)
                  </button>
                  <button type="button" onClick={() => void removeGeneratedFiles(message.downloadId!)}
                    disabled={removingDownloadId !== null || conversationUnavailable}
                    title="Remove this ZIP from the chat to free session storage."
                    className="rounded-lg px-3 py-2 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50">
                    {removingDownloadId === message.downloadId ? 'Removing...' : 'Remove ZIP'}
                  </button>
                </div>
              )}
              {timestamp !== undefined && (
                <time
                  dateTime={new Date(timestamp).toISOString()}
                  title={new Date(timestamp).toLocaleString()}
                  className={`mt-2 block text-[0.6875rem] ${message.role === 'user' && message.source === undefined ? 'text-blue-100' : 'text-gray-400'}`}
                >
                  {formatResponseTime(timestamp)}
                  {message.responseStartedAt !== undefined && message.responseCompletedAt !== undefined && (
                    <> · {formatResponseDuration(message.responseStartedAt, message.responseCompletedAt)}</>
                  )}
                </time>
              )}
              {message.role === 'assistant' && message.status === 'stopped' && (
                <p className="mt-2 text-sm text-gray-500">Stopped before completion.</p>
              )}
              {message.role === 'assistant' && message.status === 'failed' && message.retry && (
                <div className="mt-3 border-t border-red-200 pt-3 text-sm text-red-700">
                  <p>This response failed and will not be used as context for future messages.</p>
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
          );
        })}
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
  );
}
