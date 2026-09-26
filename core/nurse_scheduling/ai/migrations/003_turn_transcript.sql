-- The ordered run transcript records queued steering, which user_message omits.
ALTER TABLE chat_turns ADD COLUMN transcript jsonb;
