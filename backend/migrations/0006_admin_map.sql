-- 0006_admin_map.sql  (Admin: editable village map, wayfinding routes)

-- Where a lot / gate sits on the map, as a percentage of the map width and height (NULL = not placed yet).
ALTER TABLE village_lots ADD COLUMN IF NOT EXISTS pos_x real;
ALTER TABLE village_lots ADD COLUMN IF NOT EXISTS pos_y real;
ALTER TABLE gates        ADD COLUMN IF NOT EXISTS pos_x real;
ALTER TABLE gates        ADD COLUMN IF NOT EXISTS pos_y real;

-- Admin-written directions from the gate to a lot. NULL = the automatic "Main gate, Village Road, Block n, Lot n".
ALTER TABLE village_lots ADD COLUMN IF NOT EXISTS route text;

-- The imported map (image or PDF), one per property. Capacity limits do not apply to the village map.
CREATE TABLE IF NOT EXISTS village_maps (
  property_id  uuid PRIMARY KEY REFERENCES properties(id) ON DELETE CASCADE,
  content      bytea NOT NULL,
  content_type text  NOT NULL,
  updated_at   timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE village_maps ENABLE ROW LEVEL SECURITY;
