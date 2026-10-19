-- SPDX-License-Identifier: AGPL-3.0-or-later
-- SPDX-FileCopyrightText: 2026 Johnson Sun
-- This file is mostly AI generated.

ALTER TABLE chat_uploads RENAME TO chat_files;
ALTER TABLE chat_files DROP CONSTRAINT chat_uploads_pkey;
ALTER TABLE chat_files RENAME COLUMN id TO source_id;
ALTER TABLE chat_files ALTER COLUMN source_id TYPE text USING source_id::text;
ALTER TABLE chat_files
    ADD COLUMN id uuid NOT NULL DEFAULT gen_random_uuid(),
    ADD COLUMN kind text NOT NULL DEFAULT 'upload',
    ADD COLUMN filename text NOT NULL DEFAULT 'attachment',
    ADD COLUMN media_type text NOT NULL DEFAULT 'application/octet-stream',
    ADD COLUMN run_id text,
    ADD COLUMN created_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN removed_at timestamptz,
    ADD PRIMARY KEY (session_id, id);

CREATE UNIQUE INDEX chat_files_active_source ON chat_files (session_id, kind, source_id)
    WHERE removed_at IS NULL;

UPDATE chat_files f SET filename = u->>'filename', media_type = u->>'media_type',
    created_at = s.created_at
FROM chat_sessions s CROSS JOIN LATERAL jsonb_array_elements(s.state->'uploads') u
WHERE f.session_id = s.id AND f.source_id = u->>'id';
