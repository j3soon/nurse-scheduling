-- SPDX-License-Identifier: AGPL-3.0-or-later
-- SPDX-FileCopyrightText: 2026 Johnson Sun
-- This file is mostly AI generated.

ALTER TABLE chat_session_entries DROP CONSTRAINT chat_session_entries_type_check;
ALTER TABLE chat_session_entries ADD CONSTRAINT chat_session_entries_type_check
    CHECK (type IN ('user', 'assistant', 'tool_result', 'proposal_decision', 'app_event', 'compaction'));
