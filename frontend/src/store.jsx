import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { api, pathSegment, SESS } from './api.js';
import { START } from './config.js';

export const EMPTY = { visits: [], households: [], lots: [], routes: [], gates: [], passes: [], staff: [], areas: [], rm: [], alerts: [], msgs: [], audit: [], scan: [], map: { has: false }, report: null, now: '', prop: { name: '', slug: '' } };
const INIT = { page: 'dashboard', tab: {}, q: '', sf: '', pg: 1, size: 10, side: false, front: 'home', role: 'admin', me: '', online: null, codeReq: false, sa: false, plat: null, res: [], appr: '', door: 'loading', village: null, accounts: false, authMode: '', acct: false };

const Ctx = createContext(null);
export const useApp = () => useContext(Ctx);

export function AppProvider({ children }) {
  const [D, setD] = useState(EMPTY);
  const [S, setS] = useState(INIT);
  const [toastMsg, setToastMsg] = useState('');
  const [modal, setModal] = useState(null);
  const timer = useRef();
  const expireRef = useRef(() => {});   // set below, once signOut exists: the server ended this session (password changed, account switched off)

  const set = useCallback((p) => setS((s) => ({ ...s, ...(typeof p === 'function' ? p(s) : p) })), []);
  const toast = useCallback((t) => {
    setToastMsg(t);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToastMsg(''), 2600);
  }, []);
  const load = useCallback(async () => { setD(await api('/state')); }, []);
  // Every action: call the API, reload the PostgreSQL-backed state, show a message. Returns a truthy value on success.
  const run = useCallback(async (fn, ok) => {
    try {
      const r = await fn();
      await load();
      if (ok) toast(typeof ok === 'function' ? ok(r) : ok);
      return r ?? true;
    } catch (x) { if (x.status === 401 && SESS.token) expireRef.current(x.message); else toast(x.message); }
  }, [load, toast]);
  const closeModal = useCallback(() => setModal(null), []);

  // Opening a page from the menu starts on its first tab (a page left on its last tab would otherwise reopen there, hiding the rest).
  const go = useCallback((p) => { set((s) => ({ page: p, tab: { ...s.tab, [p]: 0 }, q: '', sf: '', pg: 1, side: false })); window.scrollTo(0, 0); }, [set]);
  const goTab = useCallback((i) => set((s) => ({ tab: { ...s.tab, [s.page]: i }, q: '', sf: '', pg: 1 })), [set]);

  // Three ways in: a personal account (email + password), a signed link (household invitation, Admin link), or the shared staff code.
  // The server decides the role. For an account it comes from the account itself, so the screen always shows what the server says.
  const signIn = useCallback(async ({ role, lot, name, code, invite, adminLink, email, password }) => {
    const s = await api('/session', { body: {
      role: role || '', household_lot: role === 'household' ? lot : null, name: name || null, code: code || null,
      invite: invite || null, admin_link: adminLink || null, email: email || null, password: email ? password || '' : null,
    } });
    Object.assign(SESS, { role: s.role, lot: s.household_lot || '', name: s.name, token: s.token || '', prop: s.property?.slug || SESS.prop });
    try { await load(); } catch (x) { Object.assign(SESS, { role: '', lot: '', name: '', token: '', prop: '' }); throw x; }   // never stay half signed in
    set({ role: s.role, me: s.name, village: s.property || null, page: invite ? 'u_form' : START[s.role] || START.guard, tab: {}, q: '', sf: '', pg: 1, front: null, side: false, sa: false, plat: null, acct: !!(email || adminLink) });
    window.scrollTo(0, 0);
  }, [load, set]);

  // Platform level: the Super Admin has their own code and token, and no village.
  const signInPlatform = useCallback(async ({ code, name }) => {
    const s = await api('/platform/session', { body: { code, name: name || '' } });
    Object.assign(SESS, { role: 'super', lot: '', name: s.name, token: s.token, prop: '' });
    set({ role: 'super', me: s.name, front: null, side: false, sa: false, plat: null, village: null });
    window.scrollTo(0, 0);
  }, [set]);
  // Work inside a village as its Admin. The platform sign-in is kept so "Back to platform" needs no new code.
  const enterProperty = useCallback(async (id) => {
    const plat = { token: SESS.token, name: SESS.name };
    const s = await api(`/platform/properties/${id}/enter`, { method: 'POST' });
    Object.assign(SESS, { role: 'admin', lot: '', name: s.name, token: s.token, prop: s.property.slug });
    try { await load(); } catch (x) { Object.assign(SESS, { role: 'super', token: plat.token, name: plat.name, prop: '' }); throw x; }
    set({ role: 'admin', me: s.name, village: s.property, page: 'dashboard', tab: {}, q: '', sf: '', pg: 1, front: null, side: false, sa: true, plat });
    window.scrollTo(0, 0);
  }, [load, set]);
  const backToPlatform = useCallback(() => {
    const plat = S.plat;
    if (!plat) return;
    Object.assign(SESS, { role: 'super', lot: '', name: plat.name, token: plat.token, prop: '' });
    setD(EMPTY); setModal(null);
    set({ role: 'super', me: plat.name, village: null, sa: false, plat: null, front: null });
  }, [S.plat, set]);
  // Which door is this? No village link in the path: the main site. Otherwise ask the server whose page it is.
  const doorReq = useRef(0);   // only the latest address check may change the page (a slow older answer must not undo a newer one)
  const readDoor = useCallback(async () => {
    const me = ++doorReq.current, seg = pathSegment();
    if (!seg) { set({ door: 'main', village: null }); return; }
    set({ door: 'loading' });
    try {
      const village = await api('/property/' + encodeURIComponent(seg));
      if (me === doorReq.current) set({ door: 'village', village });
    } catch (x) {
      if (me === doorReq.current) set({ door: x.network ? 'offline' : 'invalid', village: null });
    }
  }, [set]);
  const signOut = useCallback(() => {
    const wasAdmin = SESS.role === 'admin' || SESS.role === 'super';
    Object.assign(SESS, { role: '', lot: '', name: '', token: '', prop: '' });
    setD(EMPTY); setModal(null);
    set({ front: 'home', me: '', side: false, role: 'admin', sa: false, plat: null, acct: false });
    if (wasAdmin && pathSegment()) window.history.pushState(null, '', '/');   // an Admin leaves through the main site
    readDoor();
  }, [set, readDoor]);
  useEffect(() => { expireRef.current = (msg) => { signOut(); toast(msg || 'Your session has ended. Please sign in again.'); }; }, [signOut, toast]);

  useEffect(() => {
    readDoor();
    const back = () => { if (!SESS.role) { set({ front: 'home' }); readDoor(); } };   // the address changed (back button or a pasted link)
    window.addEventListener('popstate', back);
    return () => window.removeEventListener('popstate', back);
  }, [readDoor, set]);

  // A household opens the link from its invitation (?invite=...): sign in and land on the household form.
  useEffect(() => {
    const invite = new URLSearchParams(window.location.search).get('invite');
    if (!invite) return;
    window.history.replaceState(null, '', window.location.pathname);   // keep the token out of the address bar and history
    signIn({ role: 'household', invite }).catch((x) => toast(x.message));
  }, [signIn, toast]);

  // The approve/decline link in the household's email (?approve=...): open the confirmation page. No sign-in needed.
  useEffect(() => {
    const tok = new URLSearchParams(window.location.search).get('approve');
    if (!tok) return;
    window.history.replaceState(null, '', window.location.pathname);   // keep the token out of the address bar and history
    set({ front: 'approve', appr: tok });
  }, [set]);

  // The Admin's personal link from the platform (?admin=...): the token names its village, so the right village is used for the sign-in.
  useEffect(() => {
    const tok = new URLSearchParams(window.location.search).get('admin');
    if (!tok) return;
    window.history.replaceState(null, '', window.location.pathname);
    try { SESS.prop = JSON.parse(atob(tok.split('.')[0].replace(/-/g, '+').replace(/_/g, '/'))).p || ''; } catch { /* the server will refuse a broken link */ }
    signIn({ role: 'admin', adminLink: tok }).catch((x) => { SESS.prop = ''; toast(x.message); });
  }, [signIn, toast]);

  useEffect(() => {
    api('/health').then(() => set({ online: true })).catch(() => set({ online: false }));
    api('/config').then((c) => set({ codeReq: c.code_required, accounts: !!c.accounts, authMode: c.auth_mode || '' })).catch(() => {});
  }, [set]);

  // refresh the signed-in dashboard every 15 s (not while a dialog is open)
  useEffect(() => {
    if (S.front || modal || S.role === 'super') return undefined;
    const id = setInterval(() => { load().catch((x) => { if (x.status === 401 && SESS.token) expireRef.current(x.message); }); }, 15000);
    return () => clearInterval(id);
  }, [S.front, S.role, modal, load]);

  useEffect(() => { document.body.style.background = S.front ? '#080d19' : '#F3F4F6'; }, [S.front]);

  const value = { D, S, set, toast, toastMsg, load, run, modal, setModal, closeModal, go, goTab, signIn, signOut, signInPlatform, enterProperty, backToPlatform };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
