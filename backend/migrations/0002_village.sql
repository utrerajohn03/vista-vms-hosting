-- 0002_village.sql  (Village group: extends the foundation; every table carries property_id)

CREATE TABLE IF NOT EXISTS village_households (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id  uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  lot_code     text,                                   -- e.g. B1-L4, NULL while only invited
  owner_name   text NOT NULL DEFAULT '(invited)',
  holder_name  text,
  email        text,
  phone        text,
  status       text NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','awaiting','verified')),
  verified_at  timestamptz,
  verified_by  text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
-- The platform's own migration may already have created village_households (and the tables below). Extend them, never recreate:
-- every column the Village group needs is added if it is missing, and existing rows keep their data.
ALTER TABLE village_households ADD COLUMN IF NOT EXISTS lot_code    text;
ALTER TABLE village_households ADD COLUMN IF NOT EXISTS owner_name  text NOT NULL DEFAULT '(invited)';
ALTER TABLE village_households ADD COLUMN IF NOT EXISTS holder_name text;
ALTER TABLE village_households ADD COLUMN IF NOT EXISTS email       text;
ALTER TABLE village_households ADD COLUMN IF NOT EXISTS phone       text;
ALTER TABLE village_households ADD COLUMN IF NOT EXISTS status      text NOT NULL DEFAULT 'invited';
ALTER TABLE village_households ADD COLUMN IF NOT EXISTS verified_at timestamptz;
ALTER TABLE village_households ADD COLUMN IF NOT EXISTS verified_by text;
ALTER TABLE village_households ADD COLUMN IF NOT EXISTS created_at  timestamptz NOT NULL DEFAULT now();
CREATE UNIQUE INDEX IF NOT EXISTS ux_vh_lot ON village_households (property_id, lower(lot_code)) WHERE lot_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS village_members (          -- listed only, no accounts
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id  uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  household_id uuid NOT NULL REFERENCES village_households(id) ON DELETE CASCADE,
  full_name    text NOT NULL,
  is_minor     boolean NOT NULL DEFAULT false
);
ALTER TABLE village_members ADD COLUMN IF NOT EXISTS full_name text NOT NULL DEFAULT '';
ALTER TABLE village_members ADD COLUMN IF NOT EXISTS is_minor  boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS ix_vm_hh ON village_members (property_id, household_id);

CREATE TABLE IF NOT EXISTS village_lots (             -- map lots, may exist before a household is linked
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id  uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  lot_code     text NOT NULL,
  household_id uuid REFERENCES village_households(id) ON DELETE SET NULL
);
ALTER TABLE village_lots ADD COLUMN IF NOT EXISTS lot_code     text;
ALTER TABLE village_lots ADD COLUMN IF NOT EXISTS household_id uuid REFERENCES village_households(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_vl_lot ON village_lots (property_id, lower(lot_code));

CREATE TABLE IF NOT EXISTS restricted_areas (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  name        text NOT NULL,
  active      boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS restricted_area_members (
  property_id uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  area_id     uuid NOT NULL REFERENCES restricted_areas(id) ON DELETE CASCADE,
  member_id   uuid NOT NULL REFERENCES village_members(id) ON DELETE CASCADE,
  PRIMARY KEY (area_id, member_id)
);

CREATE TABLE IF NOT EXISTS village_visit_details (
  visit_id          uuid PRIMARY KEY REFERENCES visits(id) ON DELETE CASCADE,
  property_id       uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  household_id      uuid REFERENCES village_households(id),   -- NULL while in the HOA queue
  host_member_id    uuid REFERENCES village_members(id),      -- NULL = any household member
  visitor_name      text NOT NULL,
  visitor_phone     text NOT NULL,
  typed_house       text NOT NULL,
  typed_host        text NOT NULL DEFAULT '',
  purpose           text,
  visit_at          timestamptz,
  arrival_method    text NOT NULL CHECK (arrival_method IN ('walking','own_vehicle','ride')),
  declared_kind     text, declared_color text, declared_plate text,
  restricted_flag   boolean NOT NULL DEFAULT false,
  walk_in           boolean NOT NULL DEFAULT false,
  gate_notified_at  timestamptz,                               -- starts the 3-hour Missing timer
  vehicle_left      boolean NOT NULL DEFAULT false,
  close_reason      text,
  reject_reason     text
);
CREATE INDEX IF NOT EXISTS ix_vvd_hh ON village_visit_details (property_id, household_id);
CREATE INDEX IF NOT EXISTS ix_vvd_phone ON village_visit_details (property_id, visitor_phone);

CREATE TABLE IF NOT EXISTS village_visit_people (            -- one pass per person in the group
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  property_id uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  visit_id    uuid NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
  full_name   text NOT NULL,
  is_lead     boolean NOT NULL DEFAULT false,
  sort        int NOT NULL DEFAULT 0,
  badge_id    uuid REFERENCES badges(id),
  arrived_at  timestamptz,                                     -- resident scan at the house
  left_at     timestamptz                                      -- guard scan at exit
);
CREATE INDEX IF NOT EXISTS ix_vvp_visit ON village_visit_people (property_id, visit_id);

CREATE TABLE IF NOT EXISTS village_vehicle_checks (          -- entry photo is personal data
  visit_id        uuid PRIMARY KEY REFERENCES visits(id) ON DELETE CASCADE,
  property_id     uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  photo_path      text,
  plate_ok        boolean NOT NULL DEFAULT false,
  color_ok        boolean NOT NULL DEFAULT false,
  type_ok         boolean NOT NULL DEFAULT false,
  override_used   boolean NOT NULL DEFAULT false,
  override_reason text,
  checked_by      text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  delete_after    timestamptz                                   -- retention: purge with a cleanup job
);
