// Household form rules. The API checks the same things; this gives the answer before the round trip.
export const LOT_RE = /^B(\d{1,3})\s*-\s*L(\d{1,3})$/i;
const HOUSE_RE = /^[A-Z0-9][A-Z0-9 .#/-]{0,19}$/;
// Block and lot ("b1 - l4" becomes B1-L4) or a plain house number ("25a" becomes 25A). null when empty or unusable.
export const normLot = (s) => {
  const t = String(s || '').replace(/\s+/g, ' ').trim();
  const m = LOT_RE.exec(t);
  if (m) return `B${+m[1]}-L${+m[2]}`;
  const u = t.toUpperCase();
  return HOUSE_RE.test(u) ? u : null;
};
const squash = (s) => String(s || '').replace(/\s+/g, ' ').trim();

// People textarea: one per line, "(minor)" marks a minor. Duplicates (same name) are dropped.
export function parseMembers(text) {
  const seen = new Set(), out = [];
  for (const line of String(text || '').split('\n')) {
    const minor = /\(minor\)/i.test(line);
    const n = squash(line.replace(/\(minor\)/gi, ''));
    if (n && !seen.has(n.toLowerCase())) { seen.add(n.toLowerCase()); out.push({ n, minor }); }
  }
  return out;
}

// Returns an error message, or '' when the form is fine.
export function checkHousehold(f) {
  if (!squash(f.owner)) return 'Enter the owner name';
  if (!squash(f.holder)) return 'Enter the account holder’s name';
  if (!normLot(f.lot)) return 'Enter the block and lot (like B1-L4) or the house number';
  if (!f.em.trim()) return 'Enter the account holder’s email address';
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.em.trim())) return 'Enter a valid email address';
  if (!f.ph.trim()) return 'Enter the account holder’s phone number';
  const digits = f.ph.replace(/\D/g, '');
  if (digits.length < 7 || digits.length > 15) return 'Enter a valid phone number';
  const people = parseMembers(f.mem);
  if (!people.length) return 'List the people living here (at least the account holder)';
  const me = people.find((p) => p.n.toLowerCase() === squash(f.holder).toLowerCase());
  if (!me) return 'The account holder must be one of the people listed';
  if (me.minor) return 'The account holder must be an adult';
  return '';
}
