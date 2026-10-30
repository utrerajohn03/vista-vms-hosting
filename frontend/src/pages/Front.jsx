import { useEffect, useRef, useState } from 'react';
import { api, parseVillageLink, SESS } from '../api.js';
import { photoToJpegBase64 } from '../photo.js';
import { useApp } from '../store.jsx';
import { downloadQrPng, passPayload } from '../qrcore.js';
import { Ic, Qr } from '../ui.jsx';

const DI = 'h-11 w-full rounded-xl border border-white/10 bg-[#0d1424] px-3.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40';
const DB = 'inline-flex h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 hover:bg-blue-500 disabled:opacity-50';
const DG = 'inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-5 text-sm font-medium text-slate-200 hover:bg-white/10';
// Admins sign in at the main site. A village's own page is for visitors and the village's staff and households.
const ROLES = [['guard', 'Security guard'], ['hoa', 'HOA office'], ['household', 'Household account holder']];

function Field({ id, label, req, cls = '', area, select, error, hint, ...p }) {
  const a11y = { 'aria-invalid': error ? 'true' : undefined, 'aria-describedby': error ? `e_${id}` : hint ? `h_${id}` : undefined };
  const bad = error ? ' !border-rose-500/70' : '';
  return (
    <div className={`min-w-0 ${cls}`}>
      <label htmlFor={`d_${id}`} className="mb-1.5 block text-sm font-medium text-slate-300">{label}{req && <span className="text-blue-400"> *</span>}</label>
      {area ? <textarea id={`d_${id}`} rows="3" className={`${DI} py-2.5${bad}`} {...a11y} {...p} />
        : select ? <select id={`d_${id}`} className={`${DI}${bad}`} {...a11y} {...p}>{select.map((x) => (Array.isArray(x) ? <option key={x[0]} value={x[0]}>{x[1]}</option> : <option key={x}>{x}</option>))}</select>
        : <input id={`d_${id}`} className={`${DI} ${p.type === 'file' ? 'pt-2.5' : ''}${bad}`} {...a11y} {...p} />}
      {error ? <p id={`e_${id}`} role="alert" className="mt-1.5 text-xs text-rose-400">{error}</p>
        : hint ? <p id={`h_${id}`} className="mt-1.5 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}
const Err = ({ m }) => (m ? <p role="alert" className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3.5 py-2.5 text-sm text-rose-300">{m}</p> : null);
function Shellcard({ title, sub, children, w = 'max-w-xl' }) {
  const { set } = useApp();
  return (
    <div className={`mx-auto w-full ${w}`}>
      <button onClick={() => set({ front: 'home' })} className="mb-4 inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white"><Ic n="back" /> Back</button>
      <div className="rounded-3xl border border-white/10 bg-[#111827]/80 p-6 shadow-2xl sm:p-8">
        <h1 className="text-2xl font-bold text-white">{title}</h1><p className="mt-1 text-sm text-slate-400">{sub}</p>
        <div className="mt-6">{children}</div>
      </div>
    </div>
  );
}
const Chip = ({ c, children }) => <span className={`rounded-full px-3.5 py-1.5 text-sm font-medium ${c}`}>{children}</span>;

function Home() {
  const { S, set } = useApp();
  return (
    <div className="flex flex-col items-center text-center">
      <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200"><span className="h-2 w-2 rounded-full bg-blue-400" />{S.village?.name}</span>
      <h1 className="mt-12 text-4xl font-extrabold tracking-tight text-white sm:text-[56px] sm:leading-[1.1]">Who are you here as?</h1>
      <p className="mt-4 max-w-md text-lg text-slate-400">Choose your role to get started. Visitors register a pass; staff and households sign in to their dashboard.</p>
      <div className="mt-12 grid w-full max-w-3xl gap-5 text-left sm:grid-cols-2">
        <button onClick={() => set({ front: 'visitor' })} className="rounded-3xl bg-gradient-to-br from-blue-500 to-blue-600 p-8 shadow-[0_24px_60px_-20px_rgba(37,99,235,.8)] transition hover:-translate-y-0.5">
          <span className="flex h-[60px] w-[60px] items-center justify-center rounded-2xl bg-white/20 text-indigo-950"><Ic n="user" c="h-8 w-8" /></span>
          <span className="mt-8 block text-2xl font-bold text-white">I’m a visitor</span>
          <span className="mt-2 block text-[17px] leading-snug text-blue-100">Register your visit, get a QR pass, and present it at the gate.</span>
          <span className="mt-6 inline-flex items-center gap-2 font-semibold text-white">Register now <Ic n="arrow" /></span>
        </button>
        <button onClick={() => set({ front: 'login' })} className="rounded-3xl border border-white/10 bg-[#1a1f2c] p-8 transition hover:-translate-y-0.5 hover:border-white/20">
          <span className="flex h-[60px] w-[60px] items-center justify-center rounded-2xl bg-white/10 text-sky-400"><Ic n="shield" c="h-8 w-8" /></span>
          <span className="mt-8 block text-2xl font-bold text-white">I’m staff</span>
          <span className="mt-2 block text-[17px] leading-snug text-slate-400">Sign in to approve visits, check visitors in and out, and view reports.</span>
          <span className="mt-6 inline-flex items-center gap-2 font-semibold text-slate-200">Sign in <Ic n="arrow" /></span>
        </button>
      </div>
      <div className="mt-9 flex flex-wrap justify-center gap-3">
        <Chip c="bg-emerald-500/15 text-emerald-300">Security</Chip>
        <Chip c="bg-blue-500/15 text-blue-300">HOA office</Chip><Chip c="bg-slate-500/20 text-slate-300">Household</Chip>
      </div>
      <button onClick={() => set({ front: 'retrieve' })} className="mt-8 inline-flex items-center gap-3 rounded-full border border-white/10 px-6 py-3 text-slate-300 hover:bg-white/5">
        <span className="text-amber-400"><Ic n="ticket" c="h-5 w-5" /></span>Already registered? Retrieve your QR pass
      </button>
    </div>
  );
}

// Limits are the API's own (VisitIn): name 120, phone 3 to 40, house 40.
const FIELD_ORDER = ['n', 'p', 'e', 'i', 'h', 't', 'u', 'w', 'a', 'f'];

function Visitor() {
  const { set } = useApp();
  const [v, setV] = useState({ n: '', p: '', e: '', h: '', t: '', u: '', w: '', a: 'Walking', k: '', c: '', l: '', f: '' });
  const [file, setFile] = useState(null);
  const [errs, setErrs] = useState({});
  const [formErr, setFormErr] = useState('');
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);   // blocks a second submit before React has re-rendered the disabled button
  const up = (k) => (e) => { const val = e.target.value; setV((o) => ({ ...o, [k]: val })); if (errs[k]) setErrs((o) => ({ ...o, [k]: '' })); };
  const focusFirst = (found) => { const k = FIELD_ORDER.find((x) => found[x]); if (k) document.getElementById(`d_${k}`)?.focus(); };
  const friends = v.f.split('\n').map((x) => x.trim()).filter(Boolean);
  const car = v.a === 'Own vehicle';

  const pickFile = (e) => {
    const f = e.target.files?.[0] || null;
    if (f && !/^image\//.test(f.type || '')) { setFile(null); e.target.value = ''; setErrs((o) => ({ ...o, i: 'Choose a photo or a picture of your ID (an image file).' })); return; }
    setFile(f); setErrs((o) => ({ ...o, i: '' }));
  };

  const validate = () => {
    const g = (k) => v[k].trim(), found = {};
    if (!g('n')) found.n = 'Enter your name.'; else if (g('n').length > 120) found.n = 'Use 120 characters or fewer.';
    if (!g('p')) found.p = 'Enter your phone number.'; else if (g('p').length < 3 || g('p').length > 40) found.p = 'Enter a valid phone number.';
    if (g('e') && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(g('e'))) found.e = 'Enter a valid email address, or leave it blank.';
    if (!file) found.i = 'Add your ID or a photo of yourself.';
    if (!g('h')) found.h = 'Enter the house number or block and lot.'; else if (g('h').length > 40) found.h = 'Use 40 characters or fewer.';
    if (!g('u')) found.u = 'Enter the purpose of your visit.';
    if (!g('w')) found.w = 'Choose the date and time of your visit.'; else if (Number.isNaN(new Date(g('w')).getTime())) found.w = 'Enter a valid date and time.';
    const seen = new Set([g('n').toLowerCase()]);
    for (const f of friends) {
      if (f.length > 120) { found.f = `“${f.slice(0, 20)}…” is too long. Use 120 characters or fewer per name.`; break; }
      if (seen.has(f.toLowerCase())) { found.f = `“${f}” is listed twice. Write each person once (you are already included).`; break; }
      seen.add(f.toLowerCase());
    }
    return found;
  };

  const submit = async (e) => {
    e.preventDefault();
    if (sending.current) return;
    const found = validate();
    setErrs(found);
    if (Object.keys(found).length) { setFormErr('Please fix the highlighted fields.'); focusFirst(found); return; }
    sending.current = true; setBusy(true); setFormErr('');
    const g = (k) => v[k].trim();
    try {
      let id_photo;
      try { id_photo = await photoToJpegBase64(file); } catch (x) { setErrs({ i: x.message }); setFormErr('Please fix the highlighted fields.'); focusFirst({ i: 1 }); return; }
      // One request for the whole group: the lead's name plus `friends`; the guard issues one pass per person.
      await api('/visits', { body: {
        name: g('n'), phone: g('p'), email: g('e'), id_photo, house: g('h'), host: g('t'), purpose: g('u'), when: g('w'), arrival: v.a,
        kind: car ? g('k') : '', color: car ? g('c') : '', plate: car ? g('l') : '', friends,
      } });
      set({ front: 'vdone' });
    } catch (x) {
      if (/ID or photo/i.test(x.message)) { setErrs({ i: x.message }); focusFirst({ i: 1 }); }
      setFormErr(x.network ? x.message : `Your request was not sent. ${x.message}`);
    } finally { sending.current = false; setBusy(false); }
  };

  return (
    <Shellcard title="Register your visit" sub="One form covers everyone visiting the same person. The group shares one request, one approval and one QR code.">
      <form onSubmit={submit} noValidate aria-busy={busy} className="grid gap-4 sm:grid-cols-2">
        <Field id="n" label="Your name" req autoComplete="name" maxLength={120} value={v.n} onChange={up('n')} error={errs.n} />
        <Field id="p" label="Phone" req type="tel" autoComplete="tel" maxLength={40} value={v.p} onChange={up('p')} error={errs.p} />
        <Field id="e" label="Email (optional)" type="email" autoComplete="email" maxLength={120} cls="sm:col-span-2" value={v.e} onChange={up('e')} error={errs.e}
          hint="We will email your QR code once the household approves. You can also get it here with your name and phone." />
        <Field id="i" label="ID or photo" req type="file" accept="image/*" cls="sm:col-span-2" onChange={pickFile} error={errs.i}
          hint={file ? `Selected: ${file.name}` : 'A picture of a valid ID, or a clear photo of yourself.'} />
        <Field id="h" label="House number" req placeholder="Block and lot (B1-L4) or house number" maxLength={40} value={v.h} onChange={up('h')} error={errs.h} />
        <Field id="t" label="Person you’re visiting" placeholder="Blank = any household member" value={v.t} onChange={up('t')} error={errs.t} />
        <Field id="u" label="Purpose" req value={v.u} onChange={up('u')} error={errs.u} />
        <Field id="w" label="Date and time" req type="datetime-local" value={v.w} onChange={up('w')} error={errs.w} />
        <Field id="a" label="How are you arriving?" select={['Walking', 'Own vehicle', 'Ride']} cls="sm:col-span-2" value={v.a} onChange={up('a')} error={errs.a} />
        {car && (
          <div className="grid gap-4 sm:col-span-2 sm:grid-cols-3">
            <Field id="k" label="Vehicle type (optional)" placeholder="e.g. Sedan, SUV" value={v.k} onChange={up('k')} />
            <Field id="c" label="Color (optional)" value={v.c} onChange={up('c')} />
            <Field id="l" label="Plate number (optional)" value={v.l} onChange={up('l')} />
          </div>
        )}
        <Field id="f" label="Friends visiting with you" area placeholder="One name per line" cls="sm:col-span-2" value={v.f} onChange={up('f')} error={errs.f}
          hint={friends.length ? `${friends.length + 1} people in this request (you and ${friends.length} ${friends.length === 1 ? 'friend' : 'friends'}). Each person gets their own pass at the gate.` : 'Optional. Add one name per line; each person gets their own pass at the gate.'} />
        {formErr && <div className="sm:col-span-2"><Err m={formErr} /></div>}
        <div className="flex flex-col-reverse gap-3 sm:col-span-2 sm:flex-row">
          <button type="button" disabled={busy} onClick={() => set({ front: 'home' })} className={`${DG} w-full sm:w-auto`}>Cancel</button>
          <button type="submit" disabled={busy} className={`${DB} w-full sm:w-auto`}>{busy ? 'Sending…' : 'Send request'}</button>
        </div>
      </form>
    </Shellcard>
  );
}

// The page behind the approve/decline link in the household's email. The link itself is the key, so there is no sign-in.
function Approve() {
  const { S } = useApp();
  const [info, setInfo] = useState(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState('');
  useEffect(() => {
    api(`/approval/${encodeURIComponent(S.appr)}`).then(setInfo).catch((x) => setErr(x.message));
  }, [S.appr]);
  const answer = async (action) => {
    setBusy(true); setErr('');
    try {
      await api(`/approval/${encodeURIComponent(S.appr)}`, { body: { action } });
      setDone({ approve: 'Approved. The visitor can now get their QR code.', decline: 'Declined. The visitor has been told the request was not approved.', not_for_me: 'Thank you. The request was sent to the HOA office to find the right person.' }[action]);
    } catch (x) { setErr(x.message); }
    setBusy(false);
  };
  const row = (l, val) => <div className="flex justify-between gap-4 border-t border-white/5 py-2 text-sm first:border-0"><dt className="text-slate-400">{l}</dt><dd className="text-right text-slate-100">{val || '-'}</dd></div>;
  return (
    <Shellcard title="Visit request" sub={info ? `${info.ref} · ${info.village}` : 'Approve or decline this visit'}>
      {!info && !err && <p className="text-sm text-slate-400">Loading…</p>}
      {err && !info && <Err m={err} />}
      {info && (
        <>
          <dl>
            {row('Visitor', info.visitor)}{row('People', info.people.length > 1 ? info.people.join(', ') : '1 person')}{row('Visiting', info.visiting)}
            {row('Purpose', info.purpose)}{row('When', info.when)}{row('Arriving', info.arrival)}
          </dl>
          {done ? <p role="status" className="mt-5 rounded-xl bg-emerald-500/10 p-3 text-sm text-emerald-300">{done}</p>
            : !info.verified ? <p className="mt-5 rounded-xl bg-amber-500/10 p-3 text-sm text-amber-200">Your household has not been verified by the HOA office yet, so it cannot approve visits. Please contact the HOA office.</p>
              : !info.can_decide ? <p className="mt-5 rounded-xl bg-white/5 p-3 text-sm text-slate-300">This request was already answered (now: {info.status}). Nothing more to do.</p>
                : (
                  <>
                    <Err m={err} />
                    <div className="mt-5 flex flex-col gap-3 sm:flex-row">
                      <button className={DB} disabled={busy} onClick={() => answer('approve')}>Approve</button>
                      <button className={DG} disabled={busy} onClick={() => answer('decline')}>Decline</button>
                    </div>
                    <button className="mt-4 text-sm text-slate-400 underline hover:text-white" disabled={busy} onClick={() => answer('not_for_me')}>Not for me: I do not know this person or house</button>
                  </>
                )}
        </>
      )}
    </Shellcard>
  );
}

function Done() {
  const { set } = useApp();
  return (
    <Shellcard title="Your request was sent" sub="You’ll see the status here. Once the household approves, your QR code is ready.">
      <div className="flex gap-3"><button onClick={() => set({ front: 'retrieve' })} className={DB}>Check status</button><button onClick={() => set({ front: 'home' })} className={DG}>Done</button></div>
    </Shellcard>
  );
}

function Retrieve() {
  const { set } = useApp();
  const [n, setN] = useState(''), [p, setP] = useState(''), [err, setErr] = useState('');
  const submit = async (e) => {
    e.preventDefault();
    if (!n.trim() || !p.trim()) { setErr('Enter your name and phone number.'); return; }
    try { set({ res: await api('/visits/lookup', { body: { name: n.trim(), phone: p.trim() } }), front: 'rres' }); } catch (x) { setErr(x.message); }
  };
  return (
    <Shellcard title="Retrieve your QR pass" sub="Enter the name and phone number you used when you registered.">
      <form onSubmit={submit} noValidate className="grid gap-4">
        <Field id="rn" label="Full name" req value={n} onChange={(e) => setN(e.target.value)} />
        <Field id="rp" label="Phone" req type="tel" value={p} onChange={(e) => setP(e.target.value)} />
        <Err m={err} /><button className={DB}>Find my pass</button>
      </form>
    </Shellcard>
  );
}

function Results() {
  const { S, set } = useApp();
  return (
    <Shellcard title="Your requests" sub={S.res.length ? 'Show the QR code at the gate. One code covers the whole group.' : 'If a matching request exists, it appears here.'}>
      {S.res.map((r, i) => (
        <div key={r.qr || i} className="mb-3 rounded-2xl border border-white/10 bg-[#0d1424] p-4">
          <div className="flex items-center justify-between"><b className="text-white">House {r.house} · {r.when}</b><span className="rounded-full border border-white/15 px-2.5 py-0.5 text-xs text-slate-300">{r.status}</span></div>
          <p className="mt-1 text-sm text-slate-400">{r.people} {r.people > 1 ? 'people' : 'person'} in this request</p>
          {r.qr && <><div className="mt-4 flex justify-center"><Qr t={r.qr} /></div><p className="mt-2 text-center font-mono text-xs text-slate-400">{r.qr}</p>
            <div className="mt-2 flex justify-center"><button type="button" className={DG} onClick={() => downloadQrPng(passPayload(r.qr), `visit-pass-${r.qr.slice(0, 6)}.png`).catch(() => {})}>Save QR image</button></div></>}
          {r.directions && <p className="mt-3 rounded-lg bg-blue-500/10 p-2.5 text-sm text-blue-200">Directions: {r.directions}.</p>}
        </div>
      ))}
      {!S.res.length && <p className="text-sm text-slate-400">Nothing found for that name and number yet.</p>}
      <button onClick={() => set({ front: 'retrieve' })} className={`${DG} mt-2`}>Search again</button>
    </Shellcard>
  );
}

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Sign in as yourself: your own email and password (POST /api/session). The server decides the role from the account
// (guard, HOA office or Admin), so there is no role to pick and nobody can sign in as a role they were not given.
function AccountForm({ onSwitch, noCode }) {
  const { signIn } = useApp();
  const [f, setF] = useState({ email: '', password: '' });
  const [errs, setErrs] = useState({});
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);   // blocks a second submit before React has re-rendered the disabled button
  const up = (k) => (e) => { const val = e.target.value; setF((o) => ({ ...o, [k]: val })); if (errs[k]) setErrs((o) => ({ ...o, [k]: '' })); };
  const submit = async (e) => {
    e.preventDefault();
    if (sending.current) return;
    const email = f.email.trim(), found = {};
    if (!email) found.email = 'Enter your email address.'; else if (!EMAIL_RE.test(email)) found.email = 'Enter a valid email address.';
    if (!f.password) found.password = 'Enter your password.';
    setErrs(found); setErr('');
    if (found.email || found.password) { document.getElementById(found.email ? 'd_ae' : 'd_ap')?.focus(); return; }
    sending.current = true; setBusy(true);
    try { await signIn({ email, password: f.password }); }
    catch (x) { setErr(x.message); setF((o) => ({ ...o, password: '' })); document.getElementById('d_ap')?.focus(); }
    finally { sending.current = false; setBusy(false); }
  };
  return (
    <form onSubmit={submit} noValidate aria-busy={busy} className="grid gap-4">
      <p className="rounded-xl bg-white/5 p-3 text-xs text-slate-400">Sign in with your own email and password. You get the role your account was given. The Admin creates guard and HOA office accounts.</p>
      <Field id="ae" label="Email" req type="email" autoComplete="username" value={f.email} onChange={up('email')} error={errs.email} />
      <Field id="ap" label="Password" req type="password" autoComplete="current-password" value={f.password} onChange={up('password')} error={errs.password} />
      <Err m={err} />
      <button className={DB} disabled={busy}>{busy ? 'Signing in…' : 'Sign in'} <Ic n="arrow" /></button>
      {onSwitch && <button type="button" onClick={onSwitch} className="text-sm text-slate-400 underline hover:text-white">Household, or use the staff access code instead</button>}
      {noCode && <p className="text-xs text-slate-500">Households sign in with the personal link in their invitation email.</p>}
    </form>
  );
}

// The shared staff access code (and, in demo mode, a plain role picker). Households use it to choose their house.
function CodeForm({ signup, onSwitch }) {
  const { S, signIn } = useApp();
  const [f, setF] = useState({ code: '', role: 'guard', lot: '', name: '' });
  const [hh, setHh] = useState(null);
  const [err, setErr] = useState('');
  const up = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const pickRole = async (e) => {
    const role = e.target.value;
    if (role !== 'household') { setHh(null); setF({ ...f, role }); return; }
    try {
      const h = await api('/dev/households', { h: { 'X-Access-Code': f.code } });
      setHh(h); setF({ ...f, role, lot: h[0]?.lot || '' });
    } catch (x) { setErr(x.message); setF({ ...f, role: 'guard' }); }
  };
  const submit = async (e) => {
    e.preventDefault();
    try { await signIn({ role: f.role, lot: f.lot, name: signup ? f.name.trim() : '', code: f.code }); } catch (x) { setErr(x.message); }
  };
  return (
    <form onSubmit={submit} noValidate className="grid gap-4">
      {S.codeReq
        ? <p className="rounded-xl bg-white/5 p-3 text-xs text-slate-400">Enter the staff access code you were given, then pick your role.</p>
        : <p className="rounded-xl bg-amber-500/10 p-3 text-xs text-amber-300">Authentication is switched off in this build. Pick a role and continue, and nothing is checked.</p>}
      {signup && <Field id="sn" label="Full name" placeholder="optional" value={f.name} onChange={up('name')} />}
      {S.codeReq && <Field id="lc" label="Staff access code" req type="password" value={f.code} onChange={up('code')} />}
      <Field id="lr" label={signup ? 'Role' : 'Sign in as'} select={ROLES} value={f.role} onChange={pickRole} />
      {hh && <Field id="lh" label="Household" select={hh.map((x) => [x.lot, `${x.holder} (${x.lot})`])} value={f.lot} onChange={up('lot')} />}
      <Err m={err} />
      <button className={DB}>{signup ? 'Create account' : 'Sign in'} <Ic n="arrow" /></button>
      {onSwitch && <button type="button" onClick={onSwitch} className="text-sm text-slate-400 underline hover:text-white">Use your own email and password instead</button>}
    </form>
  );
}

function Auth({ signup }) {
  const { S, set } = useApp();
  const canAccount = !!S.accounts;                   // the server can sign people in as themselves
  const canCode = S.codeReq || S.authMode !== 'code';   // the shared code still signs people in (or demo mode: nothing is checked)
  const [pick, setPick] = useState('');
  const view = signup ? 'code' : pick || (canAccount ? 'account' : 'code');
  let body;
  if (view === 'account') body = <AccountForm onSwitch={canCode ? () => setPick('code') : null} noCode={!canCode} />;
  else if (canCode) body = <CodeForm signup={signup} onSwitch={canAccount && !signup ? () => setPick('account') : null} />;
  else body = <p className="rounded-xl bg-white/5 p-3 text-sm text-slate-300">Accounts are created by the village Admin. Ask the Admin for your email and password, then sign in.</p>;
  return (
    <Shellcard title={signup ? 'Create your account' : 'Welcome back'} sub={signup ? 'Choose your role to continue.' : 'Sign in to your dashboard.'} w="max-w-md">
      <div role="tablist" className="mb-6 grid grid-cols-2 rounded-xl bg-[#0d1424] p-1">
        {[['login', 'Sign in'], ['signup', 'Sign up']].map(([x, l]) => (
          <button key={x} role="tab" aria-selected={(signup ? 'signup' : 'login') === x} onClick={() => set({ front: x })} className={`h-10 rounded-lg text-sm font-semibold ${(signup ? 'signup' : 'login') === x ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'}`}>{l}</button>
        ))}
      </div>
      {body}
    </Shellcard>
  );
}

// Main site: only for Admins. They name their village by its link, so nobody can browse a list of villages.
function MainDoor() {
  const { S, signIn, signInPlatform } = useApp();
  const [mode, setMode] = useState('admin');   // 'admin' | 'super'
  const [how, setHow] = useState('');          // 'account' | 'code'; empty = what this server prefers
  const [f, setF] = useState({ link: '', code: '', name: '', email: '', password: '' });
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const sup = mode === 'super';
  const canCode = S.codeReq || S.authMode !== 'code';
  const acct = !sup && (how ? how === 'account' : !!S.accounts);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true); setErr('');
    if (sup) {
      if (!f.code) { setErr('Enter the Super Admin code.'); setBusy(false); return; }
      try { await signInPlatform({ code: f.code, name: f.name.trim() }); } catch (x) { setErr(x.message); }
      setBusy(false);
      return;
    }
    const slug = parseVillageLink(f.link);
    if (!slug) { setErr('Enter your village link.'); setBusy(false); return; }
    if (acct) {
      const email = f.email.trim();
      if (!email || !EMAIL_RE.test(email)) { setErr('Enter your email address.'); setBusy(false); return; }
      if (!f.password) { setErr('Enter your password.'); setBusy(false); return; }
      SESS.prop = slug;
      try { await signIn({ email, password: f.password }); }
      catch (x) { SESS.prop = ''; setF((o) => ({ ...o, password: '' })); setErr(x.network ? x.message : x.message === 'Unknown property' ? 'That village link is not valid.' : x.message); }
      setBusy(false);
      return;
    }
    SESS.prop = slug;
    try { await signIn({ role: 'admin', code: f.code }); }
    catch (x) { SESS.prop = ''; setErr(x.network ? x.message : 'Could not sign in. Check the village link and the access code.'); }
    setBusy(false);
  };
  return (
    <div className="mx-auto w-full max-w-md">
      <div className="rounded-3xl border border-white/10 bg-[#111827]/80 p-6 shadow-2xl sm:p-8">
        <h1 className="text-2xl font-bold text-white">{sup ? 'Super Admin sign-in' : 'Admin sign-in'}</h1>
        <p className="mt-1 text-sm text-slate-400">{sup
          ? 'For the platform owner. Create villages, assign each its Admin and monitor the platform.'
          : 'For village Admins. Open the personal link the platform sent you, or sign in with your village link and your own email and password. Visitors, guards, the HOA office and households use their village’s own link instead.'}</p>
        <form onSubmit={submit} noValidate className="mt-6 grid gap-4">
          {sup ? (
            <>
              <Field id="sn" label="Your name" placeholder="optional, shown in the audit" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoComplete="name" />
              <Field id="sc" label="Super Admin code" req type="password" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} autoComplete="off" />
            </>
          ) : (
            <>
              <Field id="ml" label="Village link" req placeholder="e.g. greenfield-village-7f3a" value={f.link} onChange={(e) => setF({ ...f, link: e.target.value })} autoComplete="off" autoCapitalize="off" spellCheck="false" />
              {acct ? (
                <>
                  <Field id="me" label="Email" req type="email" autoComplete="username" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
                  <Field id="mp" label="Password" req type="password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
                </>
              ) : S.codeReq
                ? <Field id="mc" label="Staff access code" req type="password" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} />
                : <p className="rounded-xl bg-amber-500/10 p-3 text-xs text-amber-300">Authentication is switched off in this build. Enter the village link and continue, and nothing is checked.</p>}
            </>
          )}
          <Err m={err} />
          <button className={DB} disabled={busy}>{busy ? 'Signing in…' : sup ? 'Sign in as Super Admin' : 'Sign in as Admin'} <Ic n="arrow" /></button>
        </form>
        {!sup && S.accounts && canCode && (
          <button type="button" onClick={() => { setHow(acct ? 'code' : 'account'); setErr(''); }} className="mt-5 block text-sm text-slate-400 underline hover:text-white">
            {acct ? 'Use the staff access code instead' : 'Use your email and password instead'}
          </button>
        )}
        <button type="button" onClick={() => { setMode(sup ? 'admin' : 'super'); setErr(''); setF({ link: f.link, code: '', name: f.name, email: '', password: '' }); }} className="mt-5 block text-sm text-slate-400 underline hover:text-white">
          {sup ? 'Back to Admin sign-in' : 'Platform owner? Super Admin sign-in'}
        </button>
      </div>
    </div>
  );
}

const Notice = ({ title, children }) => (
  <div className="mx-auto w-full max-w-md rounded-3xl border border-white/10 bg-[#111827]/80 p-8 text-center shadow-2xl">
    <h1 className="text-2xl font-bold text-white">{title}</h1><p className="mt-2 text-sm text-slate-400">{children}</p>
  </div>
);

export default function Front() {
  const { S } = useApp();
  let page;
  if (S.door === 'main') page = <MainDoor />;
  else if (S.door === 'invalid') page = <Notice title="This village link is not valid">Check the link you were given, or ask your village office for the right one.</Notice>;
  else if (S.door === 'offline') page = <Notice title="Cannot reach the server">Check your connection and reload the page.</Notice>;
  else if (S.door !== 'village') page = <Notice title="Loading…">One moment.</Notice>;
  else page = { home: <Home />, visitor: <Visitor />, vdone: <Done />, approve: <Approve />, retrieve: <Retrieve />, rres: <Results />, login: <Auth key="login" />, signup: <Auth key="signup" signup /> }[S.front];
  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-[#080d19]">
      <div className="pointer-events-none absolute -left-40 -top-32 h-[520px] w-[520px] rounded-full" style={{ background: 'radial-gradient(closest-side,rgba(37,99,235,.28),transparent)' }} />
      <div className="pointer-events-none absolute -bottom-40 -right-40 h-[560px] w-[560px] rounded-full" style={{ background: 'radial-gradient(closest-side,rgba(79,70,229,.22),transparent)' }} />
      <HomeHeader />
      <main className="relative z-10 flex-1 px-5 py-10 sm:py-14">{page}</main>
      <footer className="relative z-10 border-t border-white/5 py-6 text-center text-sm text-slate-600">Vista VMS · Village visitor management</footer>
    </div>
  );
}

function HomeHeader() {
  const { S, set } = useApp();
  return (
    <header className="relative z-10 flex items-center justify-between border-b border-white/5 px-5 sm:px-9" style={{ paddingTop: 'env(safe-area-inset-top,0px)', height: 'calc(72px + env(safe-area-inset-top,0px))' }}>
      <button onClick={() => set({ front: 'home' })} className="flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-600 text-white shadow-lg shadow-blue-600/40"><Ic n="idc" c="h-6 w-6" /></span>
        <span className="text-lg font-bold text-white">Vista VMS</span>
      </button>
      {S.door === 'village' && S.village?.name && <span className="hidden text-sm text-slate-400 sm:block">{S.village.name}</span>}
      <span className="flex items-center gap-2 text-sm text-slate-400">
        <span className={`h-2.5 w-2.5 rounded-full ${S.online === false ? 'bg-rose-500' : 'bg-emerald-500'}`} />{S.online === false ? 'System offline' : 'System online'}
      </span>
    </header>
  );
}
