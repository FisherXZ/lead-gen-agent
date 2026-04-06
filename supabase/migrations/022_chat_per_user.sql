-- Make chat conversations per-user instead of shared
-- Run AFTER deploying the backend code changes (new user_id params default to None)

-- 1. Add user_id column (nullable first for backfill)
ALTER TABLE chat_conversations
  ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id);

-- 2. Backfill existing conversations to the first admin (or first user)
UPDATE chat_conversations
SET user_id = (
  SELECT COALESCE(
    (SELECT ur.user_id FROM user_roles ur WHERE ur.role = 'admin' LIMIT 1),
    (SELECT id FROM auth.users ORDER BY created_at LIMIT 1)
  )
)
WHERE user_id IS NULL;

-- 3. Delete orphans if no users exist, then make NOT NULL
DELETE FROM chat_conversations WHERE user_id IS NULL;
ALTER TABLE chat_conversations ALTER COLUMN user_id SET NOT NULL;

-- 4. Index for efficient per-user listing
CREATE INDEX IF NOT EXISTS idx_chat_conversations_user
  ON chat_conversations (user_id, updated_at DESC);

-- 5. Per-user RLS on chat_conversations
DROP POLICY IF EXISTS "Authenticated read" ON chat_conversations;
DROP POLICY IF EXISTS "Public read chat_conversations" ON chat_conversations;

CREATE POLICY "Users read own conversations" ON chat_conversations
  FOR SELECT USING (auth.uid() = user_id);

-- 6. Per-user RLS on chat_messages (via conversation ownership)
DROP POLICY IF EXISTS "Authenticated read" ON chat_messages;
DROP POLICY IF EXISTS "Public read chat_messages" ON chat_messages;

CREATE POLICY "Users read own conversation messages" ON chat_messages
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM chat_conversations c
      WHERE c.id = chat_messages.conversation_id
      AND c.user_id = auth.uid()
    )
  );
