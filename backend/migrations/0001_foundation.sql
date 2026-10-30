-- 0001_foundation.sql
-- Stand-in for the shared platform foundation (properties, users, visits, badges, audit).
-- If the platform already owns these tables, keep its versions, align names, and only run 0002.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS properties (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL,
  slug       text NOT NULL UNIQUE,                 -- e.g. greenfield-village-7f3a
  kind       text NOT NULL DEFAULT 'village',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id  uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  email        text NOT NULL,
  name         text NOT NULL,
  role         text NOT NULL CHECK (role IN ('admin','guard','hoa','household')),
  active       boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email ON users (property_id, lower(email));

CREATE TABLE IF NOT EXISTS visits (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  seq         bigint GENERATED ALWAYS AS IDENTITY,        -- shown as VS-0001
  status      text NOT NULL CHECK (status IN ('pending','queue','walkin_pending','approved','at_gate',
                'arrived','missing','left','closed','declined','rejected','wrong_destination')),
  qr_token    text NOT NULL UNIQUE,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_visits_prop_status ON visits (property_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS ux_visits_prop_seq ON visits (property_id, seq);

CREATE TABLE IF NOT EXISTS badges (               -- passes
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  code        text NOT NULL,
  status      text NOT NULL DEFAULT 'avail' CHECK (status IN ('avail','issued','lost')),
  holder      text,
  UNIQUE (property_id, code)
);

CREATE TABLE IF NOT EXISTS audit_log (
  id          bigserial PRIMARY KEY,
  property_id uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  actor       text NOT NULL,
  role        text NOT NULL,
  action      text NOT NULL,
  visit_id    uuid,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_audit_prop_time ON audit_log (property_id, created_at DESC);

CREATE TABLE IF NOT EXISTS notifications (         -- Messages page; EmailJS sends the real email
  id          bigserial PRIMARY KEY,
  property_id uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  recipient   text NOT NULL,
  subject     text NOT NULL,
  status      text NOT NULL DEFAULT 'sent',
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
  id          bigserial PRIMARY KEY,
  property_id uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  kind        text NOT NULL,
  detail      text NOT NULL,
  status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved')),
  visit_id    uuid,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS gates (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  name        text NOT NULL,
  kind        text NOT NULL DEFAULT 'Entry and exit',
  active      boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS settings (
  property_id uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  key         text NOT NULL,
  value       jsonb NOT NULL,
  PRIMARY KEY (property_id, key)
);
