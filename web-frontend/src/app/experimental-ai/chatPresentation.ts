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

import type { ActivityEntry } from './AssistantActivity';
import type { ChatMessageContent } from './chatTranscript';

export function formatCharacterCount(characters: number): string {
  return characters >= 1000 ? `${(characters / 1000).toFixed(1)}k` : `${characters}`;
}

export function formatResponseDuration(startedAt: number, completedAt: number): string {
  const seconds = Math.max(0, completedAt - startedAt) / 1000;
  if (seconds < 1) return '<1s';
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  const totalSeconds = Math.round(seconds);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  return `${Math.floor(totalSeconds / 60)}m ${totalSeconds % 60}s`;
}

export function activitySummary(entry: Exclude<ActivityEntry, { kind: 'response' }>): string {
  if (entry.kind === 'reasoning') return `Reasoning · ${formatCharacterCount(entry.text.length)} characters`;
  if (entry.kind === 'schedule-change') return 'schedule edit';
  if (entry.kind === 'schedule-check') return entry.ok ? 'Schedule check passed' : 'Schedule check failed';
  if (entry.kind === 'schedule-applied') return 'Applied to your schedule';
  if (entry.state === 'running') return `${entry.name} · running`;
  if (entry.state === 'interrupted') return `${entry.name} · interrupted`;
  return entry.ok ? entry.name : `${entry.name} · failed`;
}

export function scheduleChangeLines(beforeText: string, afterText: string): { removed: string[]; added: string[] } {
  const before = beforeText.split('\n');
  const after = afterText.split('\n');
  let prefix = 0;
  while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix += 1;
  let suffix = 0;
  while (
    suffix < before.length - prefix
    && suffix < after.length - prefix
    && before[before.length - suffix - 1] === after[after.length - suffix - 1]
  ) suffix += 1;
  return {
    removed: before.slice(prefix, before.length - suffix),
    added: after.slice(prefix, after.length - suffix),
  };
}
export function retentionLabel(seconds: number): string {
  if (seconds % 86400 === 0) {
    const days = seconds / 86400;
    return `${days} ${days === 1 ? 'day' : 'days'}`;
  }
  if (seconds % 3600 === 0) {
    const hours = seconds / 3600;
    return `${hours} ${hours === 1 ? 'hour' : 'hours'}`;
  }
  return `${seconds.toLocaleString()} seconds`;
}

export function formatSessionExpiration(timestamp: number): string {
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

export function formatResponseTime(timestamp: number): string {
  const completed = new Date(timestamp);
  const now = new Date();
  const sameDate = completed.getFullYear() === now.getFullYear()
    && completed.getMonth() === now.getMonth()
    && completed.getDate() === now.getDate();
  return completed.toLocaleString([], sameDate
    ? { hour: 'numeric', minute: '2-digit' }
    : { year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function uploadedFileLines(files: { filename: string; bytes: number }[]): string[] {
  return files.map(file => `${file.filename} (${(file.bytes / 1000).toLocaleString('en-US')} KB)`);
}

export function messageUploadedFileLines(message: ChatMessageContent): string[] {
  if (message.source !== 'app' || message.title !== 'Files Uploaded') return [];
  const separator = message.content.indexOf(': ');
  if (separator < 0) return [];
  try {
    const files: unknown = JSON.parse(message.content.slice(separator + 2));
    if (!Array.isArray(files) || !files.every(file => file !== null && typeof file === 'object'
      && typeof file.filename === 'string' && typeof file.bytes === 'number' && Number.isFinite(file.bytes) && file.bytes >= 0)) {
      return [];
    }
    return uploadedFileLines(files);
  } catch {
    return [];
  }
}

export function messageLabel(message: ChatMessageContent): string {
  if (message.role === 'system') return 'System';
  if (message.role === 'assistant') return 'Assistant';
  if (message.role === 'optimizer') return 'Optimizer';
  const topic = message.title ? ` - ${message.title}` : '';
  if (message.source === 'app') return `User · App${topic}`;
  if (message.source === 'status') return `User · Status${topic}`;
  if (message.source === 'optimizer') return 'User · Optimizer';
  return 'User';
}
