-- 0010_token_version.sql  (sign-in tokens can be revoked)
-- Every sign-in token of a personal account (and every Admin link) carries the number below. A password change or reset, and
-- switching an account off or on, add 1, so every token issued before that moment stops working at once.
-- The column is prefixed "vista_" because "users" can be a table shared with the platform.
ALTER TABLE users ADD COLUMN IF NOT EXISTS vista_token_version integer NOT NULL DEFAULT 0;
