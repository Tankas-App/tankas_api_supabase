-- ---------------------------------------------------------------------------
-- 002_comments.sql — issue comments
--
-- Ported from the legacy tankas_app-api, which supported commenting on issues.
-- Additive only: safe to run against a database already built from
-- tankas_migration.sql.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS comments (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  issue_id   UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  content    TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comments_issue_id ON comments(issue_id);
CREATE INDEX IF NOT EXISTS idx_comments_user_id  ON comments(user_id);
CREATE INDEX IF NOT EXISTS idx_comments_created  ON comments(created_at DESC);
