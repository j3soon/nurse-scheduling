-- SPDX-License-Identifier: AGPL-3.0-or-later
-- SPDX-FileCopyrightText: 2026 Johnson Sun
-- This file is mostly AI generated.

CREATE TABLE chat_uploads (
    session_id uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    id uuid NOT NULL,
    data bytea NOT NULL,
    PRIMARY KEY (session_id, id)
);
