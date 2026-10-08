-- SPDX-License-Identifier: AGPL-3.0-or-later
-- SPDX-FileCopyrightText: 2026 Johnson Sun
-- This file is mostly AI generated.

-- Conversation entries move from runs to sessions, as Pi's session entries, so app
-- events between runs are saved too and restore rebuilds the conversation from them.
-- Sessions saved by 002_chat_session_recovery.sql keep their conversation in `state`
-- and never saved their app events as entries, so they cannot be restored.
DELETE FROM chat_sessions;
DROP TABLE chat_run_entries;

-- Whether the run's messages joined the session conversation. A failed, stale, or
-- interrupted run did not, nor did a message stopped before it ran.
ALTER TABLE chat_runs ADD COLUMN committed boolean NOT NULL DEFAULT false;

-- One agent message or app entry per row, in session order. Run messages and proposal
-- decisions name their run. The payload holds the fields of the matching transcript.py type.
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
