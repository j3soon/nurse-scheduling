-- SPDX-License-Identifier: AGPL-3.0-or-later
-- SPDX-FileCopyrightText: 2026 Johnson Sun
-- This file is mostly AI generated.

-- Keep existing ownership, expiry, run metadata, and named Stop requests.
ALTER TABLE chat_recovery_sessions RENAME TO chat_sessions;
ALTER TABLE chat_recovery_turns RENAME TO chat_runs;
ALTER TABLE chat_runs RENAME COLUMN request_id TO message_id;
ALTER TABLE chat_runs ADD COLUMN committed boolean NOT NULL DEFAULT false;
ALTER TABLE chat_recovery_stops RENAME TO chat_run_stops;
ALTER TABLE chat_run_stops RENAME COLUMN request_id TO message_id;

CREATE TABLE chat_session_entries (
    session_id uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    seq bigint NOT NULL,
    run_id uuid REFERENCES chat_runs(id) ON DELETE CASCADE,
    type text NOT NULL CHECK (type IN ('user', 'assistant', 'tool_result', 'proposal_decision', 'app_event')),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, seq)
);
CREATE INDEX chat_session_entries_run ON chat_session_entries(run_id);

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

-- The legacy channels had independent cursors. Their shared sequence preserves
-- publication order when they become one stream. Restart resets replace old cursors.
INSERT INTO chat_session_events (session_id, event_id, last_event_id, run_id, type, data, created_at)
SELECT session_id, sequence, sequence, turn_id,
       CASE WHEN event_type = 'turn_start' THEN 'run_start' ELSE event_type END,
       (data - 'turn_id') || CASE
           WHEN turn_id IS NOT NULL THEN jsonb_build_object('run_id', turn_id::text)
           ELSE '{}'::jsonb
       END || CASE
           WHEN event_type = 'turn_start' THEN jsonb_build_object('trigger', coalesce(data->>'trigger', 'user'))
           ELSE '{}'::jsonb
       END,
       created_at
FROM chat_recovery_entries ORDER BY sequence;
DROP TABLE chat_recovery_entries;

-- ChatHistory.initialize converts both legacy text histories and typed snapshots
-- to ordered entries in this transaction, then removes the redundant question column.
