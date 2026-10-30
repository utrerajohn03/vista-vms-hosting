import { api } from './api.js';
import { useApp } from './store.jsx';
import { parseMembers } from './household.js';

const MAP_OK = /^(image\/(png|jpeg|webp)|application\/pdf)$/;
const readDataUrl = (f) => new Promise((ok, no) => { const rd = new FileReader(); rd.onload = () => ok(rd.result); rd.onerror = () => no(new Error('The file could not be read')); rd.readAsDataURL(f); });
import { DetailsModal, ExitModal, FormModal, GateModal, LinkModal, VerifyModal } from './modals.jsx';

const ADD = {
  visits: (v) => {
    const friends = (v.friends || '').split('\n').map((x) => x.trim()).filter(Boolean);
    const own = v.arr === 'Own vehicle';
    return api('/walkins', { body: { visitor: v.visitor, phone: v.phone || '', house: v.house, host: v.host, purpose: v.purpose || '', arr: v.arr, friends,
      kind: own ? v.kind || '' : '', color: own ? v.color || '' : '', plate: own ? v.plate || '' : '' } });
  },
  households: (v) => api('/households/invite', { body: { email: v.holder } }),
  lots: (v) => api('/lots', { body: { lot: v.lot, household: v.household || '' } }),
  gates: (v) => api('/gates', { body: { name: v.name, type: v.type } }),
  passes: (v) => api('/badges', { body: { code: v.no } }),
  staff: (v) => api('/staff', { body: { name: v.name, email: v.email, role: v.role, password: v.password || null } }),
  areas: (v) => api('/areas', { body: { name: v.area, members: v.members || '' } }),
};
const EDIT = {
  visits: { f: [{ k: 'house', l: 'House number', r: 1 }, { k: 'host', l: 'Person visiting' }], go: (r, v) => api(`/visits/${r.ref}/resend`, { body: { house: v.house, host: v.host === 'Any household member' ? '' : v.host } }) },
  households: {
    f: [{ k: 'owner', l: 'Owner name' }, { k: 'lot', l: 'Block and lot or house number' }, { k: 'holder', l: 'Account holder' },
      { k: 'email', l: 'Email', t: 'email' }, { k: 'phone', l: 'Phone' },
      { k: 'mem', l: 'People living here (one per line, add (minor) for minors)', t: 'textarea' }],
    init: (r) => ({ owner: r.owner, lot: r.lot === '-' ? '' : r.lot, holder: r.holder, email: r.email, phone: r.ph, mem: (r.members || []).map((m) => m.n + (m.minor ? ' (minor)' : '')).join('\n') }),
    go: (r, v) => api(`/households/${r.id}`, { method: 'PATCH', body: { owner: v.owner, lot: v.lot, holder: v.holder, email: v.email, phone: v.phone, members: parseMembers(v.mem) } }),
  },
  gates: { f: [{ k: 'name', l: 'Gate name', r: 1 }, { k: 'type', l: 'Used for', t: 'select', o: ['Entry and exit', 'Deliveries', 'Walk-ins'] }], go: (r, v) => api(`/gates/${r.id}`, { method: 'PATCH', body: { name: v.name, type: v.type } }) },
  lots: { f: [{ k: 'lot', l: 'Lot code', r: 1 }, { k: 'household', l: 'Household owner' }], go: (r, v) => api(`/lots/${r.id}`, { method: 'PATCH', body: { lot: v.lot, household: v.household } }) },
  staff: { f: [{ k: 'name', l: 'Full name', r: 1 }, { k: 'email', l: 'Email', t: 'email', r: 1 }, { k: 'password', l: 'New password (leave empty to keep the current one)', t: 'password' }],
    go: (r, v) => api(`/staff/${r.id}`, { method: 'PATCH', body: { name: v.name, email: v.email, password: v.password || null } }) },
  areas: { f: [{ k: 'area', l: 'Area name', r: 1 }, { k: 'members', l: 'Household members', ph: 'Names, comma separated' }], go: (r, v) => api(`/areas/${r.id}`, { method: 'PATCH', body: { name: v.area, members: v.members } }) },
};
const patch = (p) => (r, active) => api(`/${p}/${r.id}`, { method: 'PATCH', body: { active } });
const ROWACT = {
  visits: { 'Mark arrived': (r) => api(`/visits/${r.ref}/status`, { body: { status: 'arrived' } }), 'Flag wrong destination': (r) => api(`/visits/${r.ref}/status`, { body: { status: 'wrong_destination' } }) },
  households: { Verify: (r) => api(`/households/${r.id}/verify`, { method: 'POST' }), 'Resend invitation': (r) => api(`/households/${r.id}/resend-invite`, { method: 'POST' }) },
  gates: { Activate: (r) => patch('gates')(r, true), Deactivate: (r) => patch('gates')(r, false) },
  passes: { 'Mark lost': (r) => api(`/badges/${r.id}/status`, { body: { status: 'lost' } }), 'Mark found': (r) => api(`/badges/${r.id}/status`, { body: { status: 'avail' } }) },
  staff: { Activate: (r) => patch('staff')(r, true), Deactivate: (r) => patch('staff')(r, false) },
  areas: { Deactivate: (r) => patch('areas')(r, false) },
  rm: { Remove: (r) => api(`/areas/${r.area_id}/members/${r.member_id}`, { method: 'DELETE' }) },
  alerts: { Resolve: (r) => api(`/alerts/${r.id}/resolve`, { method: 'POST' }) },
  msgs: { Resend: (r) => api(`/messages/${r.id}/resend`, { method: 'POST' }) },
};

// Row actions, the "add" dialog, and the details dialog. Every call goes to the API, then the state reloads.
export function useActions() {
  const { run, toast, setModal } = useApp();

  const decide = (r, ok) => run(() => api(`/visits/${r.ref}/decision`, { body: { approve: ok } }), ok ? 'Approved. QR sent to the visitor' : 'Declined');
  const walkin = (r, ok) => run(() => api(`/visits/${r.ref}/walkin-decision`, { body: { approve: ok } }), ok ? 'Approved. Now check in at the gate' : 'Declined');

  const X = {
    Approve: (r) => decide(r, true),
    Decline: (r) => decide(r, false),
    'Not for me': (r) => run(() => api(`/visits/${r.ref}/not-for-me`, { method: 'POST' }), 'Sent to the HOA queue'),
    'Approved by phone': (r) => walkin(r, true),
    'Declined by phone': (r) => walkin(r, false),
    'Correct and resend': (r) => setModal(
      <FormModal title="Correct and resend" submit="Resend" fields={[{ k: 'fh', l: 'House number', r: 1 }, { k: 'fn', l: 'Person visiting' }]}
        initial={{ fh: r.house, fn: r.host === 'Any household member' ? '' : r.host }}
        onSubmit={(v) => run(() => api(`/visits/${r.ref}/resend`, { body: { house: v.fh, host: v.fn } }), 'Resent to the household')} />),
    Reject: (r) => setModal(
      <FormModal title="Reject request" submit="Reject" fields={[{ k: 'rr', l: 'Reason', r: 1 }]}
        onSubmit={(v) => run(() => api(`/visits/${r.ref}/reject`, { body: { reason: v.rr } }), 'Rejected')} />),
    'Mark left': (r) => run(() => api(`/visits/${r.ref}/left`, { body: { vehicle_left: true } }), 'Marked Left. Passes available again.'),
    Verify: (r) => setModal(<VerifyModal hid={r.id} />),
    'Check in': (r) => setModal(<GateModal vref={r.ref} />),
    'Scan out': (r) => setModal(<ExitModal vref={r.ref} />),
    'Close with reason': (r) => setModal(<ExitModal vref={r.ref} />),
    'Copy sign-in link': async (r) => {
      try {
        const { link } = await api(`/households/${r.id}/link`, { method: 'POST' });
        if (link) setModal(<LinkModal title="Household sign-in link" link={link} who={r.holder || 'the account holder'} />);
        else toast('Sign-in links need STAFF_ACCESS_CODE and SECRET_KEY on the server (published mode)');
      } catch (x) { toast(x.message); }
    },
    'Edit route': (r) => setModal(
      <FormModal title={`Route to ${r.lot}`} submit="Save route" note="Shown to the visitor only after the pass is issued. Never mention restricted areas. Leave blank to use the automatic route."
        fields={[{ k: 'route', l: 'Directions from the gate', t: 'textarea', ph: r.custom ? '' : r.route }]} initial={{ route: r.custom ? r.route : '' }}
        onSubmit={(v) => run(() => api(`/lots/${r.id}/route`, { method: 'PUT', body: { route: v.route } }), 'Route saved')} />),
    'Scan at house': (r) => run(() => api(`/passes/${r.pass}/arrived`, { method: 'POST' }), (x) => (x.flag ? 'Flagged: wrong destination' : 'Arrival confirmed')),
  };

  const act = (r, a, c) => {
    if (X[a]) { X[a](r); return; }
    const k = c.d;
    if (a === 'Edit' && EDIT[k]) {
      const E = EDIT[k];
      setModal(<FormModal title="Edit" submit="Save changes" fields={E.f} initial={E.init ? E.init(r) : r} onSubmit={(v) => run(() => E.go(r, v), 'Changes saved')} />);
      return;
    }
    const fn = (ROWACT[k] || {})[a];
    if (fn) run(() => fn(r), a + ' done'); else toast(a + ' is not available here');
  };

  const openAdd = (c) => {
    const a = c.add;
    setModal(
      <FormModal title={a.l} fields={a.f} note={a.note}
        onSubmit={async (v) => {
          if (a.imp) { // the map is stored on the server, so every Admin device sees the same one
            const f = v.file;
            if (!f) { toast('Choose a file'); return false; }
            if (!MAP_OK.test(f.type)) { toast('The map must be a PNG, JPEG or WebP image, or a PDF'); return false; }
            if (f.size > 8 * 1024 * 1024) { toast('The map file is too large (8 MB at most)'); return false; }
            try { const data = await readDataUrl(f); return await run(() => api('/map', { method: 'PUT', body: { data } }), 'Map imported'); } catch (x) { toast(x.message); return false; }
          }
          const fn = ADD[c.d];
          if (!fn) return false;
          const r = await run(() => fn(v), 'Saved');
          if (r && r.link && c.d === 'households') return <LinkModal title="Invitation link" link={r.link} who={v.holder} />;
          return r;
        }} />,
    );
  };

  const view = (r, c) => setModal(<DetailsModal row={r} cols={c.cols} />);
  return { act, openAdd, view };
}
