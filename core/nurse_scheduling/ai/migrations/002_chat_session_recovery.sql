-- SPDX-License-Identifier: AGPL-3.0-or-later
-- SPDX-FileCopyrightText: 2026 Johnson Sun
-- This file is mostly AI generated.

-- Session recovery extends the run history with session state, replayable events,
-- and Stop requests. Existing rows have no restorable state, and the separate
-- recovery tables of the earlier experimental 003_chat_recovery.sql use another
-- format. Both are discarded, because nothing would prune rows left behind.
DROP TABLE IF EXISTS chat_recovery_stops, chat_recovery_entries, chat_recovery_turns, chat_recovery_sessions;
DELETE FROM chat_sessions;

-- The state holds the schedule, pending proposal, and conversation context.
ALTER TABLE chat_sessions
    ADD COLUMN owner_hash text NOT NULL,
    ADD COLUMN expires_at timestamptz NOT NULL,
    ADD COLUMN state jsonb NOT NULL;
CREATE INDEX chat_sessions_expiry ON chat_sessions(expires_at);

-- Runs are deleted with their expired session instead of by start time.
DROP INDEX chat_runs_started_at;
ALTER TABLE chat_runs
    ADD COLUMN message_id text,
    ADD COLUMN kind text NOT NULL DEFAULT 'foreground' CHECK (kind IN ('foreground', 'background')),
    ADD COLUMN auth_credential_id text,
    ADD CONSTRAINT chat_runs_session_message UNIQUE (session_id, message_id);
CREATE INDEX chat_runs_running ON chat_runs(session_id) WHERE status = 'running';

-- Replayable events of the session stream. Optimizer progress is not stored.
-- Adjacent text fragments of one run share a row covering event_id through last_event_id.
CREATE TABLE chat_session_events (
    session_id uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    event_id bigint NOT NULL,
    last_event_id bigint NOT NULL,
    run_id uuid,
    type text NOT NULL,
    data jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (last_event_id >= event_id),
    PRIMARY KEY (session_id, event_id)
);
CREATE INDEX chat_session_events_last ON chat_session_events(session_id, last_event_id);

-- Named Stop requests, including requests for messages that have not arrived yet.
CREATE TABLE chat_run_stops (
    session_id uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_id text NOT NULL,
    PRIMARY KEY (session_id, message_id)
);
