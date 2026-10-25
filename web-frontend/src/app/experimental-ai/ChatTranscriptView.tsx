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

import { AssistantActivity, CompactionSummary } from './AssistantActivity';
import { CostDetails } from './CostDetails';
import CollapsedText from './CollapsedText';
import { characterCount, messageLabel, messageUploadedFileLines, transcriptConversation } from './chatPresentation';
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
  showCosts: boolean;
  showModels: boolean;
  steeringAssistantId: string | null;
  conversationUnavailable: boolean;
  removingDownloadId: string | null;
  downloadingOptimizationId: string | null;
  downloadGeneratedFiles: (id: string) => Promise<void>;
  removeGeneratedFiles: (id: string) => Promise<void>;
  downloadOptimizationResult: (id: string) => Promise<void>;
  activeSessionId: string | null;
  sessionExpiresAt: number | null;
  sessionRetentionSeconds: number;
}

/** Render the transcript with the same activity and failure notices as the page. */
export function ChatTranscriptView({
  messages,
  showReasoning,
  showTools,
  showCosts,
  showModels,
  steeringAssistantId,
  conversationUnavailable,
  removingDownloadId,
  downloadingOptimizationId,
  downloadGeneratedFiles,
  removeGeneratedFiles,
  downloadOptimizationResult,
  activeSessionId,
  sessionExpiresAt,
  sessionRetentionSeconds,
}: ChatTranscriptViewProps) {
  const bubbles = transcriptConversation(messages).map((part, index) => ({
    message: part, key: `${part.id}-${index}`,
  }));
  return (
      <section
        aria-label="Chat messages"
        aria-live="polite"
        className="mb-4 min-h-80 space-y-4 rounded-xl border border-gray-200 bg-gray-50 p-2 sm:p-4"
      >
        {messages.length === 0 && (
          <div className="flex min-h-72 items-center justify-center text-center text-gray-500">
            <p>Try asking “Who is available on the first date?”</p>
          </div>
        )}
        {bubbles.map(({ message, key }) => {
          const notice = message.presentation === 'notice';
          const summary = message.presentation === 'summary' ? message.compaction : undefined;
          const uploads = messageUploadedFileLines(message);
          const timestamp = message.responseCompletedAt ?? message.createdAt;
          const optimizer = message.role === 'optimizer' ? parseOptimizerMessage(message.content) : null;
          return (
            <article
              key={key}
              className={`min-w-0 rounded-xl px-3 py-3 sm:px-4 ${
                notice || summary?.invalidated
                  ? 'mx-auto max-w-[95%] sm:max-w-[85%] border border-gray-200 bg-gray-50 text-gray-700'
                  : message.role === 'optimizer'
                  ? 'mx-auto max-w-[95%] sm:max-w-[85%] border border-emerald-200 bg-emerald-50 text-emerald-950'
                  : message.role === 'system'
                    ? 'ml-auto max-w-[95%] sm:max-w-[85%] border border-dashed border-gray-300 bg-gray-50 text-gray-700'
                    : message.role === 'user' && message.source === undefined
                      ? 'ml-auto max-w-[95%] sm:max-w-[85%] bg-blue-600 text-white'
                      : message.role === 'user'
                        ? 'ml-auto max-w-[95%] sm:max-w-[85%] border border-blue-200 bg-blue-50 text-blue-950'
                        : 'mr-auto max-w-[95%] sm:max-w-[85%] border border-gray-200 bg-white text-gray-900'
              }`}
            >
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide opacity-70">{notice ? 'App notice'
                : summary ? summary.invalidated ? 'Discarded conversation summary' : 'User · Conversation summary' : messageLabel(message)}</p>
              {/* Messages reach the model by default, so only exceptions get a status line. */}
              {(notice || summary?.invalidated || message.role === 'optimizer' || message.compacted) && (
                <p className="mb-2 text-xs opacity-70">
                  {summary?.invalidated ? 'Omitted from future model context.'
                    : message.compacted ? 'Compacted out of context.' : 'Not sent to AI.'}
                </p>
              )}
              {summary && <details className="text-xs">
                <summary className="cursor-pointer select-none text-gray-500 hover:text-gray-700">Conversation summary</summary>
                <CompactionSummary entry={summary} />
              </details>}
              {uploads.length > 0 && (
                <ul aria-label="Uploaded files in this message" className="mb-2 list-inside list-disc text-xs">
                  {uploads.map((file, index) => <li key={index}>{file}</li>)}
                </ul>
              )}
              {message.activity && (
                <AssistantActivity
                  entries={message.activity.filter(entry => (
                    entry.kind === 'notice' || entry.kind === 'response' || entry.kind === 'schedule-applied' || entry.kind === 'schedule-check'
                      || entry.kind === 'compaction'
                      || (entry.kind === 'reasoning' ? showReasoning : showTools)
                  ))}
                />
              )}
              {summary ? null : notice ? null : message.presentation === 'context' ? (
                <p className="whitespace-pre-wrap break-words text-xs">{message.content}</p>
              ) : message.role === 'assistant' && !message.content && message.status === 'pending' ? (
                message.activity?.some(entry => entry.kind === 'compaction' && entry.state === 'running') ? null
                  : steeringAssistantId === message.id ? <p className="text-xs text-gray-500">Steering…</p> : <ThinkingIndicator />
              ) : message.role === 'system' ? (
                <CollapsedText summary={`${characterCount(message.content).toLocaleString('en-US')} characters`} text={message.content} />
              ) : message.source !== undefined ? (
                // The label names the topic, so the exact text starts collapsed.
                <CollapsedText summary={`${characterCount(message.content).toLocaleString('en-US')} characters`} text={message.content} />
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
              {showCosts && message.costSummary && <CostDetails summary={message.costSummary} calls={message.providerCalls ?? []}
                running={message.status === 'pending'} />}
              {showModels && message.modelSelection && <div className="mt-2 break-all text-xs text-gray-500">
                {message.modelSelection.model} · {message.modelSelection.reasoning === 'default' ? 'Default reasoning' : message.modelSelection.reasoning}
              </div>}
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
              {message.truncated && <p className="mt-2 text-sm text-amber-800">
                A response reached the output token limit. Tool calls in that response were not executed.
              </p>}
              {message.status === 'failed' && message.failureReason && !message.activity?.some(entry => (
                entry.kind === 'response' && entry.text === message.failureReason
              )) && (
                <p className="mt-2 whitespace-pre-wrap text-sm text-red-700">{message.failureReason}</p>
              )}
              {message.role === 'assistant' && message.status === 'failed' && !conversationUnavailable && (
                <p className="mt-3 border-t border-red-200 pt-3 text-sm text-red-700">
                  {message.unsentFiles
                    ? `This question was not sent because its files did not finish uploading. Uploaded files stay in this chat. Attach ${message.unsentFiles.length ? message.unsentFiles.join(', ') : 'the files'} again, then send the question.`
                    : 'This response failed before completion. Send a new message to continue.'}
                </p>
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
