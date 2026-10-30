-- 0004_entry_photos_and_host_fk.sql

-- 1) Removing a person from the household form must not fail just because they host a visit.
--    The visit keeps the name that was typed (typed_host); only the link to the member is cleared.
ALTER TABLE village_visit_details DROP CONSTRAINT IF EXISTS village_visit_details_host_member_id_fkey;
ALTER TABLE village_visit_details
  ADD CONSTRAINT village_visit_details_host_member_id_fkey
  FOREIGN KEY (host_member_id) REFERENCES village_members(id) ON DELETE SET NULL;

-- 2) The guard's entry photo of the vehicle. Stored in the database so no object storage is needed;
--    personal data, so it has a retention date and is purged by the background job (PHOTO_RETENTION_DAYS).
CREATE TABLE IF NOT EXISTS village_entry_photos (
  visit_id     uuid PRIMARY KEY REFERENCES visits(id) ON DELETE CASCADE,
  property_id  uuid NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
  content      bytea NOT NULL,
  content_type text NOT NULL DEFAULT 'image/jpeg',
  created_at   timestamptz NOT NULL DEFAULT now(),
  delete_after timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_vep_delete_after ON village_entry_photos (delete_after);
