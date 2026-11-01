-- SPDX-License-Identifier: AGPL-3.0-or-later
-- SPDX-FileCopyrightText: 2026 Johnson Sun
-- This file is mostly AI generated.

-- Recover an applied schedule even if its stream publication was lost in a crash.
ALTER TABLE chat_runs ADD COLUMN schedule_change jsonb;
