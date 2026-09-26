-- Ordered entries are the canonical record of a turn. Turns keep only run metadata.
CREATE TABLE chat_turn_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id uuid NOT NULL REFERENCES chat_turns(id) ON DELETE CASCADE,
    seq integer NOT NULL,
    type text NOT NULL CHECK (type IN ('user', 'assistant', 'proposal_decision')),
    text text,
    stop_reason text CHECK (stop_reason IN ('stop', 'length', 'aborted', 'error')),
    decision text CHECK (decision IN ('approved', 'rejected', 'invalid')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (turn_id, seq),
    CHECK (
        (type = 'user' AND text IS NOT NULL AND stop_reason IS NULL AND decision IS NULL)
        OR (type = 'assistant' AND text IS NOT NULL AND stop_reason IS NOT NULL AND decision IS NULL)
        OR (type = 'proposal_decision' AND text IS NULL AND stop_reason IS NULL AND decision IS NOT NULL)
    )
);

INSERT INTO chat_turn_entries (turn_id, seq, type, text, created_at)
SELECT id, 0, 'user', user_message, started_at FROM chat_turns;

INSERT INTO chat_turn_entries (turn_id, seq, type, text, stop_reason, created_at)
SELECT
    id,
    1,
    'assistant',
    assistant_message,
    CASE status WHEN 'cancelled' THEN 'aborted' WHEN 'failed' THEN 'error' ELSE 'stop' END,
    COALESCE(finished_at, started_at)
FROM chat_turns
WHERE status <> 'running';

ALTER TABLE chat_turns DROP COLUMN user_message;
ALTER TABLE chat_turns DROP COLUMN assistant_message;
ALTER TABLE chat_turns DROP COLUMN IF EXISTS transcript;
