-- 0008_platform.sql  (Super Admin: platform level, outside any village)

-- A village the Super Admin has switched off cannot be opened by anyone except a Super Admin.
ALTER TABLE properties ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true;

-- One Admin per property.
CREATE UNIQUE INDEX IF NOT EXISTS ux_one_admin_per_property ON users (property_id) WHERE role = 'admin';

-- What the Super Admin did on the platform (creating properties, assigning Admins, entering a property).
-- Entering a property is also written to that property's own audit log, role "Super Admin".
CREATE TABLE IF NOT EXISTS platform_audit (
  id          bigserial PRIMARY KEY,
  actor       text NOT NULL,
  action      text NOT NULL,
  property_id uuid REFERENCES properties(id) ON DELETE SET NULL,
  property    text,                                   -- the name at the time, kept if the property is later removed
  created_at  timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE platform_audit ENABLE ROW LEVEL SECURITY;
