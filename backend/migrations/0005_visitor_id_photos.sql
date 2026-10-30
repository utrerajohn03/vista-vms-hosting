-- 0005_visitor_id_photos.sql
-- The visitor's "ID or photo" from the request form. Personal data: shown only to guard and admin,
-- kept for PHOTO_RETENTION_DAYS and purged by the same background job as the entry photos.
CREATE TABLE IF NOT EXISTS village_id_photos (
  visit_id     uuid PRIMARY KEY REFERENCES visits(id) ON DELETE CASCADE,
  property_id  uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  content      bytea NOT NULL,
  content_type text NOT NULL DEFAULT 'image/jpeg',
  created_at   timestamptz NOT NULL DEFAULT now(),
  delete_after timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_vip_delete_after ON village_id_photos (delete_after);
ALTER TABLE village_id_photos ENABLE ROW LEVEL SECURITY;
