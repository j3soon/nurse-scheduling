-- SPDX-License-Identifier: AGPL-3.0-or-later
-- SPDX-FileCopyrightText: 2026 Johnson Sun
-- This file is mostly AI generated.

CREATE TABLE chat_recovery_sessions (
    id uuid PRIMARY KEY,
    owner_hash text NOT NULL,
    auth_credential_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    state jsonb NOT NULL
);
CREATE INDEX chat_recovery_sessions_expiry ON chat_recovery_sessions(expires_at);

CREATE TABLE chat_recovery_turns (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES chat_recovery_sessions(id) ON DELETE CASCADE,
    request_id text,
    question text NOT NULL,
    kind text NOT NULL DEFAULT 'foreground' CHECK (kind IN ('foreground', 'background')),
    auth_credential_id text,
    model text NOT NULL DEFAULT '',
    attachment_count integer NOT NULL DEFAULT 0,
    usage jsonb,
    error_code text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    sequence bigint GENERATED ALWAYS AS IDENTITY,
    status text NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'cancelled', 'stale')),
    UNIQUE (session_id, request_id)
);
CREATE INDEX chat_recovery_turns_running ON chat_recovery_turns(session_id, sequence) WHERE status = 'running';
CREATE INDEX chat_recovery_turns_kind ON chat_recovery_turns(session_id, kind, sequence);

CREATE TABLE chat_recovery_entries (
    session_id uuid NOT NULL REFERENCES chat_recovery_sessions(id) ON DELETE CASCADE,
    channel text NOT NULL,
    turn_id uuid REFERENCES chat_recovery_turns(id) ON DELETE CASCADE,
    event_id bigint NOT NULL,
    last_event_id bigint NOT NULL,
    event_type text NOT NULL,
    data jsonb NOT NULL,
    sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (last_event_id >= event_id),
    PRIMARY KEY (session_id, channel, event_id)
);
CREATE INDEX chat_recovery_entries_session_order ON chat_recovery_entries(session_id, sequence);

CREATE TABLE chat_recovery_stops (
    session_id uuid NOT NULL REFERENCES chat_recovery_sessions(id) ON DELETE CASCADE,
    request_id text NOT NULL,
    PRIMARY KEY (session_id, request_id)
);

-- Recovery entries replace the separate audit copies. Existing audit rows are discarded.
DROP TABLE chat_turns;
DROP TABLE chat_sessions;
