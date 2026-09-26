-- Experimental AI history restarts at this schema. Earlier experimental tables are
-- dropped rather than migrated, because nothing would prune rows left behind in them.
DROP TABLE IF EXISTS chat_turn_entries, chat_turns, chat_sessions;

CREATE TABLE chat_sessions (
    id uuid PRIMARY KEY,
    auth_credential_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE chat_runs (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    model text NOT NULL,
    status text NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'cancelled', 'stale')),
    error_code text,
    attachment_count integer NOT NULL,
    usage jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE INDEX chat_runs_session_sequence ON chat_runs(session_id, sequence);
CREATE INDEX chat_runs_started_at ON chat_runs(started_at);

-- One agent message per row in run order. The payload holds the fields of its
-- transcript.py type.
CREATE TABLE chat_run_entries (
    run_id uuid NOT NULL REFERENCES chat_runs(id) ON DELETE CASCADE,
    seq integer NOT NULL,
    type text NOT NULL CHECK (type IN ('user', 'assistant', 'tool_result', 'proposal_decision')),
    payload jsonb NOT NULL,
    PRIMARY KEY (run_id, seq)
);
