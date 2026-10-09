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

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { streamSessionEvents } from './aiClient';
import type { SessionEventHandler } from './sessionEvents';

interface ConnectionOptions {
  sessionId: string;
  endpoint: string;
  authToken: string | null;
  resetReplay?: boolean;
  onEvent: SessionEventHandler;
  onEventId: (id: number) => void;
  onDisconnect: () => void;
  onError: (error: unknown) => void;
}

interface Connection {
  options: ConnectionOptions;
  controller: AbortController | null;
  timer: ReturnType<typeof setTimeout> | null;
}

const RETRY_MS = 1000;
const MAX_RETRY_MS = 30000;

/** Own one session reader, its acknowledged cursor, and its reconnect timer. */
export function useSessionEventStream() {
  const connection = useRef<Connection | null>(null);
  const retryCount = useRef(0);
  const cursor = useRef(0);
  const disconnect = useCallback(() => {
    const current = connection.current;
    connection.current = null;
    current?.controller?.abort();
    if (current?.timer !== null && current?.timer !== undefined) clearTimeout(current.timer);
  }, []);
  const reset = useCallback(() => {
    disconnect();
    cursor.current = 0;
    retryCount.current = 0;
  }, [disconnect]);
  useEffect(() => disconnect, [disconnect]);

  const connect = useCallback((options: ConnectionOptions) => {
    disconnect();
    const current: Connection = { options, controller: null, timer: null };
    connection.current = current;
    let resetReplay = options.resetReplay ?? false;
    const open = () => {
      if (connection.current !== current) return;
      current.timer = null;
      const controller = new AbortController();
      current.controller = controller;
      const ownsReader = () => connection.current === current
        && current.controller === controller && !controller.signal.aborted;
      const openedAt = Date.now();
      const reconnect = () => {
        if (!ownsReader()) return;
        current.controller = null;
        options.onDisconnect();
        // Back off rapid failures. A long-lived reader starts afresh.
        if (Date.now() - openedAt >= MAX_RETRY_MS) retryCount.current = 0;
        const delay = Math.min(MAX_RETRY_MS, RETRY_MS * 2 ** retryCount.current);
        retryCount.current += 1;
        current.timer = setTimeout(open, delay);
      };
      const stream = streamSessionEvents(options.sessionId, {
        lastEventId: cursor.current,
        reset: resetReplay,
        onEventId: id => {
          if (!ownsReader()) return;
          cursor.current = id;
          retryCount.current = 0;
          options.onEventId(id);
        },
        onEvent: event => { if (ownsReader()) options.onEvent(event); },
      }, controller.signal, options.authToken, options.endpoint);
      resetReplay = false;
      void stream.then(reconnect, error => {
        if (!ownsReader()) return;
        options.onError(error);
        reconnect();
      });
    };
    open();
  }, [disconnect]);

  return useMemo(() => ({
    connect, reset, cursor,
    connected: (sessionId?: string, authToken?: string | null, endpoint?: string) => {
      const current = connection.current;
      return current !== null && (sessionId === undefined || current.options.sessionId === sessionId)
        && (authToken === undefined || current.options.authToken === authToken)
        && (endpoint === undefined || current.options.endpoint === endpoint);
    },
  }), [connect, reset]);
}
