-- 0007_visitor_email.sql  (optional visitor email, so the approved QR code can be emailed)
ALTER TABLE village_visit_details ADD COLUMN IF NOT EXISTS email text;
