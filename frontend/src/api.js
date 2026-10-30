// All calls go to the FastAPI backend. Empty VITE_API_URL = same origin (Vite proxy in dev).
export const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '');

// Signed-in identity. With STAFF_ACCESS_CODE set the server returns a token; in demo mode role headers are used.
export const SESS = { role: '', lot: '', name: '', token: '', prop: '' };

// Two doors: "/" is the main site (Admins). "/<village-link>" is one village's own page (visitors, guards, HOA, households).
// The first path segment is the village link; the server looks the village up by it (X-Property header).
export const pathSegment = () => decodeURIComponent((window.location.pathname.split('/').filter(Boolean)[0] || '')).toLowerCase();
// Accepts a pasted full link, a path, or just the code: 'https://x.ph/greenfield-village-7f3a?a=1' -> 'greenfield-village-7f3a'.
export function parseVillageLink(text) {
  let s = String(text || '').trim();
  try { if (/^https?:\/\//i.test(s)) s = new URL(s).pathname; } catch { /* not a URL */ }
  return (s.split(/[?#]/)[0].split('/').filter(Boolean)[0] || '').toLowerCase();
}

function authHeaders(h = {}) {
  const village = SESS.prop || pathSegment();
  if (village) h['X-Property'] = village;
  if (SESS.token) h.Authorization = 'Bearer ' + SESS.token;
  else if (SESS.role) {
    h['X-Role'] = SESS.role;
    if (SESS.lot) h['X-Household'] = SESS.lot;
    if (SESS.name) h['X-User'] = SESS.name;
  }
  return h;
}

// Fetch a protected image (the entry photo needs the sign-in headers, so an <img src> cannot load it). Returns an object URL.
export async function apiImage(path) {
  const r = await fetch(BASE + '/api' + path, { headers: authHeaders() });
  if (!r.ok) throw new Error(r.status === 404 ? 'No photo on file' : 'Could not load the photo');
  return URL.createObjectURL(await r.blob());
}

// A protected file (the village map) as an object URL; the type comes from the server.
export async function apiFile(path) {
  const r = await fetch(BASE + '/api' + path, { headers: authHeaders() });
  if (!r.ok) throw new Error(r.status === 404 ? 'No map imported yet' : 'Could not load the file');
  return URL.createObjectURL(await r.blob());
}

export async function api(path, o = {}) {
  const h = authHeaders({ 'Content-Type': 'application/json', ...(o.h || {}) });
  let r;
  try {
    r = await fetch(BASE + '/api' + path, {
      method: o.method || (o.body ? 'POST' : 'GET'),
      headers: h,
      body: o.body ? JSON.stringify(o.body) : undefined,
    });
  } catch {
    const e = new Error('Cannot reach the server. Check your connection and try again.');
    e.network = true;
    throw e;
  }
  let j = null;
  try { j = await r.json(); } catch { /* empty body */ }
  if (!r.ok) {
    const d = j && j.detail;
    const e = new Error(typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => x.msg).join(', ') : 'Request failed (' + r.status + ')');
    e.status = r.status;   // the store signs a person out when the server says the session is over (401 while signed in)
    throw e;
  }
  return j;
}
