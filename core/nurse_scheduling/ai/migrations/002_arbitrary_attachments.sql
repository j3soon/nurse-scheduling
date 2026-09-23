ALTER TABLE chat_turns ADD COLUMN attachment_count integer NOT NULL DEFAULT 0;
ALTER TABLE chat_turns DROP COLUMN image_count;
ALTER TABLE chat_turns DROP COLUMN document_count;
