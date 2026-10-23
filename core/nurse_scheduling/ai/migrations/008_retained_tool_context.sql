-- SPDX-License-Identifier: AGPL-3.0-or-later
-- SPDX-FileCopyrightText: 2026 Johnson Sun
-- This file is mostly AI generated.

-- Old offsets counted only non-tool entries. Convert them to complete-entry
-- offsets before recovery starts retaining tool results in model context.
WITH eligible AS (
    SELECT e.session_id, e.seq, e.type
    FROM chat_session_entries e
    LEFT JOIN chat_runs r ON r.id = e.run_id
    WHERE e.run_id IS NULL OR e.type IN ('app_event', 'proposal_decision') OR r.committed
), boundaries AS (
    SELECT s.id, coalesce(
        (SELECT e.seq FROM eligible e
         WHERE e.session_id = s.id AND e.type <> 'tool_result'
         ORDER BY e.seq OFFSET (s.state->>'dropped_entries')::bigint LIMIT 1),
        (SELECT coalesce(max(e.seq) + 1, 0) FROM eligible e WHERE e.session_id = s.id)
    ) AS first_seq
    FROM chat_sessions s
    WHERE coalesce((s.state->>'dropped_entries')::bigint, 0) > 0
)
UPDATE chat_sessions s
SET state = jsonb_set(s.state, '{dropped_entries}',
    to_jsonb((SELECT count(*) FROM eligible e WHERE e.session_id = s.id AND e.seq < b.first_seq)))
FROM boundaries b WHERE s.id = b.id;
