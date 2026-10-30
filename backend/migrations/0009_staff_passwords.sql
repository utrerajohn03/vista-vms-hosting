-- 0009_staff_passwords.sql  (per-person staff sign-in: email + password, replaces the shared staff code over time)
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash text;   -- scrypt$salt$hash; NULL = no password set yet
