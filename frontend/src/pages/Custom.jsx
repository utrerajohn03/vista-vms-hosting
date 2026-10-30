import { useEffect, useState } from 'react';
import { api, apiFile, SESS } from '../api.js';
import { checkHousehold, normLot, parseMembers } from '../household.js';
import { printQrPage } from '../qrcore.js';
import { useApp } from '../store.jsx';
import { BO, BP, Badge, Card, INP, Ic, Kpi } from '../ui.jsx';

export function Dash() {
  const { D } = useApp();
  const waiting = D.visits.filter((r) => r.st === 'Waiting at gate'), open = D.alerts.filter((a) => a.st === 'Open');
  const cnt = (f) => D.visits.filter(f).length;
  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi i="clock" c="bg-amber-50 text-amber-600" v={waiting.length} l="Waiting at gate" />
        <Kpi i="user" c="bg-emerald-50 text-emerald-600" v={cnt((r) => ['Inside', 'Arrived'].includes(r.st))} l="Inside now" />
        <Kpi i="clip" c="bg-blue-50 text-blue-600" v={cnt((r) => r.st === 'In HOA queue')} l="In HOA queue" />
        <Kpi i="warn" c="bg-rose-50 text-rose-600" v={cnt((r) => r.st === 'Missing')} l="Missing" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Waiting at gate">
          {waiting.map((r) => (
            <div key={r.ref} className="flex items-center justify-between border-t border-gray-100 py-2.5 first:border-0">
              <div><div className="text-sm font-semibold">{r.visitor}</div><div className="text-xs text-gray-500">House {r.house} · {r.arr}</div></div>
              <Badge v={r.flag} />
            </div>
          ))}
          {!waiting.length && <p className="text-sm text-gray-500">Nobody is waiting.</p>}
        </Card>
        <Card title="Needs attention">
          {open.map((a) => (
            <div key={a.id} className="flex items-start justify-between gap-3 border-t border-gray-100 py-2.5 first:border-0">
              <div><div className="text-sm font-semibold">{a.type}</div><div className="text-xs text-gray-500">{a.detail}</div></div>
              <span className="text-xs text-gray-500">{a.time}</span>
            </div>
          ))}
          {!open.length && <p className="text-sm text-gray-500">All clear.</p>}
        </Card>
      </div>
    </>
  );
}

const MW = 580, MH = 270;   // map canvas; lots and gates are stored as a percentage of it
const BLOCK_RE = /^B(\d+)-L(\d+)$/i;

export function MapEd() {
  const { D, run, toast } = useApp();
  const [src, setSrc] = useState('');
  const [sel, setSel] = useState(null);        // the lot or gate whose details are open: { kind, id }
  const [placing, setPlacing] = useState(null); // the next click on the map places this one: { kind, id }
  const map = D.map || {};
  useEffect(() => {
    if (!map.has) { setSrc(''); return undefined; }
    let dead = false, made = '';
    apiFile('/map').then((u) => { made = u; if (!dead) setSrc(u); else URL.revokeObjectURL(u); }).catch(() => setSrc(''));
    return () => { dead = true; if (made) URL.revokeObjectURL(made); };
  }, [map.has, map.v]);

  // A placed lot or gate uses its saved spot. One that is not placed yet gets a tidy spot of its own, drawn dashed.
  const lotAt = (l, i) => {
    if (l.x != null && l.y != null) return { x: (l.x / 100) * MW, y: (l.y / 100) * MH, auto: false };
    const m = BLOCK_RE.exec(l.lot);
    const bi = m ? Math.max(0, +m[1] - 1) % 3 : 2, k = m ? (+m[2] || 1) - 1 : i;
    return { x: 20 + bi * 190 + (k % 4) * 38, y: 50 + Math.floor(k / 4 % 4) * 34, auto: true };
  };
  let nextFreeX = 12;   // unplaced gates line up along the bottom edge, side by side
  const gateAt = (g) => {
    if (g.x != null && g.y != null) return { x: (g.x / 100) * MW, y: (g.y / 100) * MH, auto: false };
    const x = nextFreeX; nextFreeX += Math.max(44, g.name.length * 6 + 12) + 8;
    return { x, y: 238, auto: true };
  };
  const lots = D.lots.map((l, i) => ({ ...l, ...lotAt(l, i) }));
  const gates = D.gates.map((g) => ({ ...g, ...gateAt(g) }));
  // Blocks are marked from the lots that carry the block in their code (B1-L4 belongs to Block 1).
  const blocks = {};
  lots.forEach((l) => { const m = BLOCK_RE.exec(l.lot); if (m) { const b = (blocks[m[1]] ||= { x0: 1e9, y0: 1e9, x1: -1e9, y1: -1e9 }); b.x0 = Math.min(b.x0, l.x); b.y0 = Math.min(b.y0, l.y); b.x1 = Math.max(b.x1, l.x + 34); b.y1 = Math.max(b.y1, l.y + 28); } });

  const place = async (e) => {
    if (!placing) { setSel(null); return; }
    const r = e.currentTarget.getBoundingClientRect();
    const x = Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100 - 3)), y = Math.min(100, Math.max(0, ((e.clientY - r.top) / r.height) * 100 - 5));
    const p = placing;
    setPlacing(null);
    await run(() => api(`/${p.kind === 'lot' ? 'lots' : 'gates'}/${p.id}/pos`, { method: 'PUT', body: { x: +x.toFixed(2), y: +y.toFixed(2) } }), 'Placed on the map');
  };
  const chosen = sel && (sel.kind === 'lot' ? lots.find((l) => l.id === sel.id) : gates.find((g) => g.id === sel.id));
  const restrictedTies = chosen && sel.kind === 'lot' ? D.rm.filter((m) => m.household === chosen.household) : [];
  const unplaced = [...D.lots.filter((l) => l.x == null).map((l) => ({ kind: 'lot', id: l.id, label: `Lot ${l.lot}` })), ...D.gates.filter((g) => g.x == null).map((g) => ({ kind: 'gate', id: g.id, label: `Gate ${g.name}` }))];
  const remove = () => run(() => api('/map', { method: 'DELETE' }), 'Map removed');

  return (
    <Card title="Village map">
      <p className="mb-3 text-sm text-gray-500">
        Import a map image or PDF (top right), or draw the village here: pick a lot or gate, then click the map to place it. Blocks are marked from the lot codes. Nothing here is shown to visitors except the route after check-in.
      </p>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label htmlFor="mapPlace" className="text-sm font-medium text-gray-700">Place on the map</label>
        <select id="mapPlace" className={`h-9 w-56 ${INP}`} value={placing ? `${placing.kind}:${placing.id}` : ''}
          onChange={(e) => { const [kind, id] = e.target.value.split(':'); setPlacing(id ? { kind, id } : null); setSel(null); }}>
          <option value="">Choose a lot or gate…</option>
          {D.lots.map((l) => <option key={l.id} value={`lot:${l.id}`}>Lot {l.lot}{l.x == null ? ' (not placed)' : ''}</option>)}
          {D.gates.map((g) => <option key={g.id} value={`gate:${g.id}`}>Gate {g.name}{g.x == null ? ' (not placed)' : ''}</option>)}
        </select>
        {placing && <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-xs text-amber-700">Click the map to place it</span>}
        {!placing && unplaced.length > 0 && <span className="text-xs text-gray-500">{unplaced.length} not placed yet</span>}
        {map.has && <button className={`${BO} ml-auto h-9`} onClick={remove}>Remove imported map</button>}
      </div>
      <div className={`relative w-full overflow-hidden rounded-lg border border-gray-200 bg-gray-50 ${placing ? 'cursor-crosshair' : ''}`} style={{ aspectRatio: `${MW} / ${MH}` }}>
        {src && (map.type === 'application/pdf'
          ? <embed src={src} type="application/pdf" className="pointer-events-none absolute inset-0 h-full w-full opacity-60" />
          : <img src={src} alt="Imported village map" className="pointer-events-none absolute inset-0 h-full w-full object-contain opacity-60" />)}
        <svg viewBox={`0 0 ${MW} ${MH}`} className="absolute inset-0 h-full w-full" role="img" aria-label="Village map" onClick={place}>
          {Object.entries(blocks).map(([n, b]) => (
            <g key={n}>
              <rect x={b.x0 - 8} y={b.y0 - 18} width={b.x1 - b.x0 + 16} height={b.y1 - b.y0 + 26} rx="8" fill="none" stroke="#9CA3AF" strokeDasharray="4" />
              <text x={b.x0 - 2} y={b.y0 - 6} fontSize="10" fontWeight="600" fill="#374151">Block {n}</text>
            </g>
          ))}
          {lots.map((l) => {
            const rs = l.household !== '-' && D.rm.some((m) => m.household === l.household);
            const on = sel && sel.kind === 'lot' && sel.id === l.id;
            return (
              <g key={l.id} onClick={(e) => { if (placing) return; e.stopPropagation(); setSel({ kind: 'lot', id: l.id }); }} className="cursor-pointer" role="button" aria-label={`Lot ${l.lot}`}>
                <rect x={l.x} y={l.y} width="34" height="28" rx="4" fill={l.st === 'Unlinked' ? '#E5E7EB' : rs ? '#FECDD3' : '#DBEAFE'} stroke={on ? '#111827' : rs ? '#E11D48' : '#2563EB'}
                  strokeWidth={on ? 2 : 1} strokeDasharray={l.auto ? '3' : undefined} />
                <text x={l.x + 3} y={l.y + 12} fontSize="8" fill="#111827">{l.lot.replace(/^B\d+-/i, '')}</text>
                <text x={l.x + 3} y={l.y + 23} fontSize="8" fill="#6B7280">{(l.household === '-' ? '' : l.household).slice(0, 6)}</text>
              </g>
            );
          })}
          {gates.map((g) => {
            const on = sel && sel.kind === 'gate' && sel.id === g.id;
            return (
              <g key={g.id} onClick={(e) => { if (placing) return; e.stopPropagation(); setSel({ kind: 'gate', id: g.id }); }} className="cursor-pointer" role="button" aria-label={`Gate ${g.name}`}>
                <rect x={g.x} y={g.y} width={Math.max(44, g.name.length * 6 + 12)} height="22" rx="6" fill={g.st === 'Active' ? '#0F172A' : '#6B7280'} stroke={on ? '#2563EB' : 'none'} strokeWidth="2" strokeDasharray={g.auto ? '3' : undefined} />
                <text x={g.x + 8} y={g.y + 15} fontSize="10" fill="#fff">{g.name}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-600">
        <span className="rounded-full border border-blue-200 bg-blue-50 px-2.5 py-0.5">Household lot</span>
        <span className="rounded-full border border-rose-200 bg-rose-50 px-2.5 py-0.5">Restricted (admin only)</span>
        <span className="rounded-full border border-gray-200 bg-gray-50 px-2.5 py-0.5">Unlinked lot</span>
        <span className="rounded-full border border-gray-200 bg-white px-2.5 py-0.5">Dashed = not placed yet</span>
      </div>
      {chosen && (
        <div className="mt-4 rounded-lg border border-gray-200 p-3 text-sm" aria-live="polite">
          {sel.kind === 'lot' ? (
            <>
              <div className="flex items-center justify-between"><b>Lot {chosen.lot}</b><Badge v={chosen.st} /></div>
              <p className="mt-1 text-gray-600">Household: {chosen.household}</p>
              <p className="text-gray-600">People living here: {chosen.people}</p>
              {restrictedTies.length > 0 && <p className="mt-1 text-rose-700">Restricted: {restrictedTies.map((m) => `${m.member} (${m.area})`).join(', ')}</p>}
              <p className="mt-1 text-gray-600">Route: {(D.routes.find((r) => r.id === chosen.id) || {}).route || 'Link a household to give this lot a route'}</p>
            </>
          ) : (
            <><div className="flex items-center justify-between"><b>Gate {chosen.name}</b><Badge v={chosen.st} /></div><p className="mt-1 text-gray-600">Used for: {chosen.type}</p></>
          )}
          <button className={`${BO} mt-2 h-8`} onClick={() => { setPlacing({ kind: sel.kind, id: sel.id }); }}>Move on the map</button>
        </div>
      )}
    </Card>
  );
}

const Bars = ({ d }) => {
  const m = Math.max(1, ...d.map((x) => x[1]));
  return (
    <div className="flex h-44 items-end gap-3">
      {d.map((x) => (
        <div key={x[0]} className="flex flex-1 flex-col items-center gap-1">
          <span className="text-xs font-medium text-gray-700">{x[1]}</span>
          <div className="w-full rounded-t-md bg-blue-600" style={{ height: `${(x[1] / m) * 100}%` }} />
          <span className="text-xs text-gray-500">{x[0]}</span>
        </div>
      ))}
    </div>
  );
};
const HBars = ({ d }) => {
  const m = Math.max(1, ...d.map((x) => x[1]));
  return d.map((x) => (
    <div key={x[0]} className="mb-3">
      <div className="mb-1 flex justify-between text-sm"><span>{x[0]}</span><b>{x[1]}</b></div>
      <div className="h-2 rounded-full bg-gray-100"><div className="h-2 rounded-full bg-blue-600" style={{ width: `${(x[1] / m) * 100}%` }} /></div>
    </div>
  ));
};

export function Rep() {
  const { S, D } = useApp();
  const t = S.tab.reports || 0;
  const r = D.report;
  if (!r) return <Card title="Reports"><p className="text-sm text-gray-500">Loading…</p></Card>;
  const change = r.prev > 0 ? Math.round(((r.week - r.prev) / r.prev) * 100) : null;
  const none = (d) => d.every((x) => !x[1]);
  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi i="clip" c="bg-blue-50 text-blue-600" v={r.week} l="Visits, last 7 days"
          x={change === null ? null : <span className={`rounded-full px-1.5 text-xs ${change >= 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>{change >= 0 ? '+' : ''}{change}%</span>} />
        <Kpi i="people" c="bg-emerald-50 text-emerald-600" v={r.people} l="People incl. groups" />
        <Kpi i="clock" c="bg-amber-50 text-amber-600" v={r.avg_entry_min == null ? '-' : r.avg_entry_min >= 120 ? `${Math.round(r.avg_entry_min / 60)}h` : `${r.avg_entry_min}m`} l="Avg request to entry" />
        <Kpi i="warn" c="bg-rose-50 text-rose-600" v={r.missing} l="Missing flags" />
      </div>
      {t === 0 && <Card title="Visits per day">{r.week ? <Bars d={r.days} /> : <p className="text-sm text-gray-500">No visits in the last 7 days.</p>}</Card>}
      {t === 1 && <Card title="Arrival method">{none(r.arr) ? <p className="text-sm text-gray-500">No visits in the last 7 days.</p> : <HBars d={r.arr} />}</Card>}
      {t === 2 && <Card title="Exceptions, last 7 days">{none(r.exc) ? <p className="text-sm text-gray-500">No exceptions. Lost passes and vehicle overrides are counted here too.</p> : <HBars d={r.exc} />}</Card>}
    </>
  );
}

const SET_DEFAULTS = [
  ['', ''],
  ['Only visits to minors', 'HOA office', 'Same pass as a normal visit', 'Red banner with host details and extra verification tick', '3', '30'],
  [true, true, true, true],
];
const Lbl = ({ children, htmlFor }) => <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium text-gray-700">{children}</label>;

export function Sett() {
  const { S, D, run, toast } = useApp();
  const t = S.tab.settings || 0;
  // The village's name and link belong to the village itself (not to a saved form value), so they always come from the server.
  const link = D.prop?.slug ? `${window.location.origin}/${D.prop.slug}` : '';
  const withVillage = (v) => v.map((row, i) => (i === 0 ? [D.prop?.name || row[0], link] : row));
  const [vals, setVals] = useState(() => withVillage(SET_DEFAULTS));
  useEffect(() => { // show what was saved last time
    api('/settings').then((s) => setVals((v) => withVillage(v.map((d, i) => (Array.isArray(s?.['tab' + i]) && s['tab' + i].length === d.length ? s['tab' + i] : d))))).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [D.prop?.slug]);
  const put = (i, val) => setVals((v) => v.map((row, ti) => (ti === t ? row.map((x, j) => (j === i ? val : x)) : row)));
  const V = vals[t];
  const text = (i, l, ro) => <div key={i}><Lbl htmlFor={`set_${i}`}>{l}</Lbl><input id={`set_${i}`} className={`h-10 ${INP}`} value={V[i]} readOnly={ro} onChange={(e) => put(i, e.target.value)} /></div>;
  const sel = (i, l, o) => <div key={i}><Lbl htmlFor={`set_${i}`}>{l}</Lbl><select id={`set_${i}`} className={`h-10 ${INP}`} value={V[i]} onChange={(e) => put(i, e.target.value)}>{o.map((x) => <option key={x}>{x}</option>)}</select></div>;
  const chk = (i, l) => (
    <label key={i} className="flex items-center gap-3 border-t border-gray-100 py-3 text-sm first:border-0">
      <input type="checkbox" checked={!!V[i]} onChange={(e) => put(i, e.target.checked)} className="h-4 w-4 rounded border-gray-300 text-blue-600" />{l}
    </label>
  );
  const body = [
    <>
      <div className="grid gap-4 md:grid-cols-2">{text(0, 'Village name')}{text(1, 'Village link', true)}</div>
      <p className="mt-3 text-sm text-gray-500">Visitors, guards, the HOA office and households open this link. It is printed as a QR code at the gate. Keep it to the people who need it.</p>
      <button className={`${BO} mt-3`} onClick={() => (printQrPage(vals[0][0], 'Scan to register your visit', link) ? toast('QR ready to print') : toast('Allow pop-ups to print the gate QR'))}><Ic n="dl" /> Print gate QR</button>
    </>,
    <div className="grid gap-4 md:grid-cols-2">
      {sel(0, 'Primary adult sees other adults’ visitors', ['Only visits to minors', 'All visits'])}
      {sel(1, 'Who verifies households', ['HOA office', 'Admin'])}
      {sel(2, 'Restricted badge color', ['Same pass as a normal visit', 'Distinct color'])}
      {sel(3, 'Red flag at gate', ['Red banner with host details and extra verification tick'])}
      {text(4, 'Missing after (hours)')}{text(5, 'Entry photo retention (days)')}
    </div>,
    <>
      {chk(0, 'Notify the household when a visitor enters')}{chk(1, 'Notify the guard when a visitor arrives at the house')}
      {chk(2, 'Alert guard and Admin when a visit is Missing')}{chk(3, 'Email QR codes to visitors')}
    </>,
  ][t];
  return (
    <Card title={['General', 'Visit rules', 'Notifications'][t]}>
      {body}
      <div className="mt-4 flex justify-end"><button className={BP} onClick={() => run(() => api('/settings', { method: 'PUT', body: { ['tab' + t]: V } }), 'Settings saved')}>Save changes</button></div>
    </Card>
  );
}

export function HForm() {
  const { D, load, set, toast } = useApp();
  const h = D.households[0] || { members: [] };
  const [f, setF] = useState(null);          // null = showing what is saved; an object = the person is editing
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const saved = {
    owner: h.owner || '', lot: h.lot && h.lot !== '-' ? h.lot : '', holder: h.holder && h.holder !== h.email ? h.holder : '', em: h.email || '', ph: h.ph || '',
    mem: (h.members || []).map((m) => m.n + (m.minor ? ' (minor)' : '')).join('\n'),
  };
  const form = f || saved;
  const up = (k, v) => { setF({ ...form, [k]: v }); setErr(''); };
  const save = async () => {
    const bad = checkHousehold(form);
    if (bad) { setErr(bad); return; }
    setBusy(true); setErr('');
    try {
      const lot = normLot(form.lot);
      const r = await api('/me/household', {
        method: 'PUT',
        body: { owner: form.owner.trim(), lot, holder: form.holder.trim(), email: form.em.trim(), phone: form.ph.trim(), members: parseMembers(form.mem) },
      });
      SESS.lot = lot; SESS.name = form.holder.trim();     // demo-mode headers follow the saved lot and name
      set({ me: SESS.name });
      await load();
      setF(null);
      toast(r.reverify ? 'Saved. The lot changed, so the HOA office must verify this household again.' : 'Household saved');
    } catch (x) { setErr(x.message); }
    setBusy(false);
  };
  const field = (k, l, req, ph) => (
    <div><Lbl htmlFor={`hf_${k}`}>{l}{req ? ' *' : ''}</Lbl>
      <input id={`hf_${k}`} value={form[k]} placeholder={ph || ''} onChange={(e) => up(k, e.target.value)} className={`h-10 ${INP}`} aria-required={req ? 'true' : undefined} /></div>
  );
  const banner = h.st === 'Verified'
    ? <p className="mb-3 rounded-lg bg-emerald-50 p-2.5 text-xs text-emerald-800">Verified by the HOA office{h.vat ? ` on ${h.vat}` : ''}. If you change the block and lot, the HOA office must verify this household again before you can approve visits.</p>
    : h.st === 'Awaiting HOA'
      ? <p className="mb-3 rounded-lg bg-amber-50 p-2.5 text-xs text-amber-800">Sent to the HOA office for review. Until it verifies this household, you cannot approve visits.</p>
      : <p className="mb-3 rounded-lg bg-amber-50 p-2.5 text-xs text-amber-800">Fill in this form and save it. The HOA office will then review it. Until it verifies this household, you cannot approve visits.</p>;
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-[15px] font-semibold">{saved.owner ? `${saved.owner} household` : 'Your household'}{saved.lot ? `, ${saved.lot}` : ''}</h2><Badge v={h.st || 'Invited'} />
      </div>
      {banner}
      <div className="grid gap-4 md:grid-cols-2">
        {field('owner', 'Owner name', true)}{field('lot', 'Block and lot or house number', true, 'e.g. B1-L4 or 25')}{field('holder', 'Account holder', true)}{field('em', 'Email', true)}{field('ph', 'Phone', true)}
      </div>
      <label className="mb-1 mt-4 block text-sm font-medium text-gray-700" htmlFor="hf_mem">People living here * (one per line, add (minor) for minors)</label>
      <textarea id="hf_mem" rows="4" className={`${INP} py-2`} value={form.mem} onChange={(e) => up('mem', e.target.value)} aria-required="true" />
      <p className="mt-1 text-xs text-gray-500">The account holder must be on this list as an adult. Visitors can only ask for people listed here.</p>
      {err && <p role="alert" className="mt-3 rounded-lg bg-rose-50 p-2.5 text-sm text-rose-700">{err}</p>}
      <div className="mt-4 flex justify-end gap-2">
        {f && <button className={BO} disabled={busy} onClick={() => { setF(null); setErr(''); }}>Discard changes</button>}
        <button className={BP} onClick={save} disabled={busy || !f}>{busy ? 'Saving…' : 'Save household'}</button>
      </div>
    </div>
  );
}
