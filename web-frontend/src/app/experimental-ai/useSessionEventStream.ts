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
import { AiHttpError, streamSessionEvents } from './aiClient';
import { scopedEventHandler } from './chatLifecycle';

import type { SessionEventHandler, SessionStreamOptions } from './sessionEvents';

const RETRY_MS = 1000;
const MAX_RETRY_MS = 30000;

interface Connection {
  controller: AbortController | null;
  timer: ReturnType<typeof setTimeout> | null;
}

/** Own the session reader. Disconnects reconnect, while Stop leaves it running. */
export function useSessionEventStream() {
  const connection = useRef<Connection | null>(null);
  const retryCount = useRef(0);
  const cursor = useRef(0);
  const disconnect = useCallback(() => {
    const current = connection.current;
    connection.current = null;
    current?.controller?.abort();
    if (current?.timer) clearTimeout(current.timer);
  }, []);
  const reset = useCallback(() => {
    disconnect();
    cursor.current = 0;
    retryCount.current = 0;
  }, [disconnect]);
  useEffect(() => disconnect, [disconnect]);

  const connect = useCallback((
    sessionId: string,
    handle: SessionEventHandler,
    authToken: string | null,
    endpoint: string,
    onError: (error: unknown, firstFailure: boolean) => void,
  ) => {
    disconnect();
    const current: Connection = { controller: null, timer: null };
    connection.current = current;
    const open = () => {
      current.timer = null;
      const controller = new AbortController();
      current.controller = controller;
      const ownsReader = () => connection.current === current
        && current.controller === controller && !controller.signal.aborted;
      const openedAt = Date.now();
      const reconnect = () => {
        if (!ownsReader()) return;
        current.controller = null;
        // Back off repeated rapid failures. A long-lived reader starts afresh.
        if (Date.now() - openedAt >= MAX_RETRY_MS) retryCount.current = 0;
        const delay = Math.min(MAX_RETRY_MS, RETRY_MS * 2 ** retryCount.current);
        retryCount.current += 1;
        current.timer = setTimeout(open, delay);
      };
      const handlers: SessionStreamOptions = {
        onEvent: scopedEventHandler(handle, ownsReader),
        lastEventId: cursor.current,
        onEventId: id => {
          if (!ownsReader()) return;
          cursor.current = id;
          retryCount.current = 0;
        },
      };
      void streamSessionEvents(sessionId, handlers, controller.signal, authToken, endpoint).then(
        reconnect,
        (error: unknown) => {
          if (!ownsReader()) return;
          onError(error, retryCount.current === 0);
          if (error instanceof AiHttpError && error.status === 404) return;
          if (error instanceof AiHttpError && (error.status === 401 || error.status === 403)) {
            // The page can reconnect after the user changes credentials.
            connection.current = null;
            return;
          }
          reconnect();
        },
      );
    };
    open();
  }, [disconnect]);

  return useMemo(() => ({
    connect,
    reset,
    cursor,
    connected: () => connection.current !== null,
  }), [connect, reset]);
}
