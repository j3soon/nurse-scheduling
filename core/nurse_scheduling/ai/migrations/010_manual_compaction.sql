-- SPDX-License-Identifier: AGPL-3.0-or-later
-- SPDX-FileCopyrightText: 2026 Johnson Sun
-- This file is mostly AI generated.

ALTER TABLE chat_runs DROP CONSTRAINT chat_recovery_turns_kind_check;
ALTER TABLE chat_runs ADD CONSTRAINT chat_runs_kind_check
    CHECK (kind IN ('foreground', 'background', 'compaction'));
