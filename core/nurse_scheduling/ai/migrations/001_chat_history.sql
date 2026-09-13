CREATE TABLE chat_sessions (
    id uuid PRIMARY KEY,
    auth_credential_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE chat_turns (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    sequence bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    user_message text NOT NULL,
    assistant_message text NOT NULL DEFAULT '',
    model text NOT NULL,
    status text NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'cancelled', 'stale')),
    error_code text,
    image_count integer NOT NULL,
    document_count integer NOT NULL,
    usage jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);
CREATE INDEX chat_turns_session_sequence ON chat_turns(session_id, sequence);
CREATE INDEX chat_turns_started_at ON chat_turns(started_at);
