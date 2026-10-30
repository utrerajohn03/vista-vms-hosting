import { isValidElement, useEffect, useState } from 'react';
import { api, apiImage, SESS } from './api.js';
import { normLot } from './household.js';
import { photoToJpegBase64 } from './photo.js';
import { useApp } from './store.jsx';
import { BO, BP, Badge, Check, INP, Modal } from './ui.jsx';

// Generic form dialog: add, edit, correct-and-resend, reject.
export function FormModal({ title, fields, initial = {}, note, submit = 'Save', onSubmit }) {
  const { closeModal, setModal, toast } = useApp();
  const [v, setV] = useState(() => Object.fromEntries(fields.map((f) => [f.k, f.t === 'file' ? null : initial[f.k] ?? (f.t === 'select' ? f.o[0] : '')])));
  const [busy, setBusy] = useState(false);
  const save = async () => {
    const raw = new Set(fields.filter((f) => f.t === 'password').map((f) => f.k));   // a password is used exactly as typed
    const out = Object.fromEntries(Object.entries(v).map(([k, x]) => [k, typeof x === 'string' && !raw.has(k) ? x.trim() : x]));
    if (fields.some((f) => (!f.show || f.show(v)) && f.r && !out[f.k])) { toast('Fill in the required fields'); return; }
    setBusy(true);
    const ok = await onSubmit(out);
    setBusy(false);
    if (isValidElement(ok)) setModal(ok);   // onSubmit may return the next dialog to show
    else if (ok) closeModal();
  };
  return (
    <Modal title={title} onClose={closeModal} footer={<button className={BP} disabled={busy} onClick={save}>{submit}</button>}>
      {fields.filter((f) => !f.show || f.show(v)).map((f) => (
        <div key={f.k}>
          <label className="mb-1 mt-3 block text-sm font-medium text-gray-700" htmlFor={`f_${f.k}`}>{f.l}{f.r ? ' *' : ''}</label>
          {f.t === 'select' ? (
            <select id={`f_${f.k}`} className={`h-10 ${INP}`} value={v[f.k]} onChange={(e) => setV({ ...v, [f.k]: e.target.value })}>
              {f.o.map((o) => <option key={o}>{o}</option>)}
            </select>
          ) : f.t === 'textarea' ? (
            <textarea id={`f_${f.k}`} rows="3" className={`${INP} py-2`} placeholder={f.ph || ''} value={v[f.k]} onChange={(e) => setV({ ...v, [f.k]: e.target.value })} />
          ) : f.t === 'file' ? (
            <input id={`f_${f.k}`} type="file" className={`h-10 pt-1.5 ${INP}`} onChange={(e) => setV({ ...v, [f.k]: e.target.files[0] || null })} />
          ) : (
            <input id={`f_${f.k}`} type={f.t || 'text'} className={`h-10 ${INP}`} placeholder={f.ph || ''} value={v[f.k]} onChange={(e) => setV({ ...v, [f.k]: e.target.value })} />
          )}
        </div>
      ))}
      {note && <p className="mt-3 rounded-lg bg-amber-50 p-2.5 text-xs text-amber-700">{note}</p>}
    </Modal>
  );
}

export function DetailsModal({ row, cols }) {
  const { closeModal } = useApp();
  return (
    <Modal title="Details" onClose={closeModal} cancelLabel="Close">
      <dl className="mt-3 divide-y divide-gray-100 text-sm">
        {cols.map((x) => (
          <div key={x[0]} className="flex justify-between gap-4 py-2">
            <dt className="text-gray-500">{x[1]}</dt>
            <dd className="text-right font-medium">{x[2] === 'b' ? <Badge v={row[x[0]]} /> : String(row[x[0]] ?? '')}</dd>
          </div>
        ))}
      </dl>
    </Modal>
  );
}

// Guard: ID check, vehicle check with one real entry photo, mismatch override with a reason, then issue passes.
const VEH = [['plate', 'Plate'], ['color', 'Color'], ['type', 'Type']];

// The ID or photo the visitor uploaded on the form, shown to the guard to compare with the person at the gate.
function IdPhoto({ vref, has }) {
  const [u, setU] = useState({ url: '', err: '' });
  useEffect(() => {
    if (!has) return undefined;
    let dead = false, made = '';
    apiImage(`/visits/${vref}/id-photo`).then((x) => { made = x; if (!dead) setU({ url: x, err: '' }); else URL.revokeObjectURL(x); })
      .catch((e) => { if (!dead) setU({ url: '', err: e.message }); });
    return () => { dead = true; if (made) URL.revokeObjectURL(made); };
  }, [vref, has]);
  if (!has) return <p className="mt-3 text-xs text-gray-500">No ID photo on file (walk-in or removed after retention). Check the ID in person.</p>;
  return u.url
    ? <img src={u.url} alt="ID or photo from the visitor form" className="mt-3 max-h-40 w-full rounded-lg border border-gray-200 object-contain" />
    : <div className="mt-3 grid h-14 place-items-center rounded-lg border border-dashed border-gray-300 text-xs text-gray-500">{u.err || 'Loading ID photo…'}</div>;
}

export function GateModal({ vref }) {
  const { D, run, closeModal, toast } = useApp();
  const r = D.visits.find((v) => v.ref === vref);
  const [c, setC] = useState({});
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState('');
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  if (!r) return null;
  const up = (k, val) => setC((p) => ({ ...p, [k]: val }));
  const car = r.arr === 'Own vehicle', red = r.flag === 'Red flag', n = r.people.length;
  const av = D.passes.filter((p) => p.st === 'Available').length;
  const answered = VEH.every(([k]) => c[k]);                       // the guard must answer all three: matches or does not match
  const mis = VEH.some(([k]) => c[k] === 'no');
  const vd = !car || (c.photo && answered && (!mis || (c.ovr && (c.why || '').trim())));
  const ok = c.id && (!red || c.xv) && vd && av >= n && !busy;
  const declared = { plate: r.veh?.plate, color: r.veh?.color, type: r.veh?.kind };

  const pick = async (e) => {
    const f = e.target.files?.[0];
    e.target.value = '';
    if (!f) return;
    try {
      const data = await photoToJpegBase64(f);
      try { setPreview(URL.createObjectURL(f)); } catch { /* preview is optional */ }
      up('photo', data);
    } catch (x) { toast(x.message); }
  };
  const issue = async () => {
    setBusy(true);
    const done = await run(() => api(`/visits/${vref}/check-in`, {
      body: {
        id_checked: !!c.id, extra_verification: !!c.xv,
        vehicle: car ? { photo_data: c.photo, plate_ok: c.plate === 'yes', color_ok: c.color === 'yes', type_ok: c.type === 'yes', override: !!c.ovr, reason: (c.why || '').trim() || null } : null,
      },
    }), 'Passes issued. Open the barrier by hand.');
    setBusy(false);
    if (done) closeModal();
  };
  return (
    <Modal title={'Gate check: ' + r.visitor} onClose={closeModal} footer={<button className={BP} disabled={!ok} onClick={issue}>{busy ? 'Issuing…' : 'Issue passes'}</button>}>
      <p className="mt-3 text-xs text-gray-500">{r.people.join(', ')} · House {r.house} · {r.arr}</p>
      {red && (
        <>
          <div className="mt-3 rounded-lg bg-rose-600 p-3 text-sm text-white"><b>Red flag.</b> Host: {r.host}, house {r.house}. Call: {r.call}.</div>
          <Check checked={c.xv} onChange={(x) => up('xv', x)}>Extra verification done with the household</Check>
        </>
      )}
      <IdPhoto vref={vref} has={!!r.idp} />
      <div className="mt-3"><Check checked={c.id} onChange={(x) => up('id', x)}>ID checked against the visitor</Check></div>
      {car && (
        <>
          <h3 className="mt-3 text-sm font-semibold">Vehicle check</h3>
          <p className="text-xs text-gray-500">Declared: {r.veh?.kind || '?'}, {r.veh?.color || '?'}, plate {r.veh?.plate || '?'}</p>
          <div className="mt-2 flex items-center gap-3">
            {preview && <img src={preview} alt="Entry photo of the vehicle" className="h-16 w-24 rounded-lg border border-gray-200 object-cover" />}
            <label className={`${BO} cursor-pointer`}>
              {c.photo ? 'Retake entry photo' : 'Take entry photo'}
              <input type="file" accept="image/*" capture="environment" className="sr-only" aria-label="Entry photo" onChange={pick} />
            </label>
          </div>
          {c.photo && (
            <div className="mt-2 space-y-1.5">
              {VEH.map(([k, l]) => (
                <div key={k} className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="text-gray-600">{l}: <b className="text-gray-900">{declared[k] || '?'}</b></span>
                  <span className="flex gap-3">
                    <label className="flex items-center gap-1.5"><input type="radio" name={`veh_${k}`} checked={c[k] === 'yes'} onChange={() => up(k, 'yes')} />{l} matches</label>
                    <label className="flex items-center gap-1.5"><input type="radio" name={`veh_${k}`} checked={c[k] === 'no'} onChange={() => up(k, 'no')} />{l} does not match</label>
                  </span>
                </div>
              ))}
            </div>
          )}
          {mis && (
            <>
              <div className="mt-2 rounded-lg border-l-4 border-amber-500 bg-amber-50 p-2 text-xs text-amber-800"><b>Mismatch.</b> You decide. The override is logged.</div>
              <Check checked={c.ovr} onChange={(x) => up('ovr', x)}>Override and allow</Check>
              <input className={`mt-1 h-9 ${INP}`} placeholder="Reason for override" aria-label="Reason for override" value={c.why || ''} onChange={(e) => up('why', e.target.value)} />
            </>
          )}
        </>
      )}
      <p className="mt-3 text-sm">Passes to issue: <b>{n}</b> (available: {av}). Open the barrier by hand afterwards.</p>
      {av < n && <p role="alert" className="mt-1 rounded-lg bg-rose-50 p-2 text-xs text-rose-700">Not enough passes: this group needs {n} and {av} {av === 1 ? 'is' : 'are'} available. Ask the Admin to add passes or mark found ones available.</p>}
    </Modal>
  );
}

// Guard: scan each person's pass out (type or scan the pass number), confirm the vehicle left, mark Left, or close with a reason code.
export function ExitModal({ vref }) {
  const { D, run, load, toast, closeModal } = useApp();
  const r = D.visits.find((v) => v.ref === vref);
  const [vl, setVl] = useState(false);
  const [reason, setReason] = useState('Vehicle not left');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [photo, setPhoto] = useState({ url: '', err: '' });
  const hasPhoto = !!r?.chk?.photo;
  useEffect(() => {
    if (!hasPhoto) return undefined;
    let dead = false, made = '';
    apiImage(`/visits/${vref}/entry-photo`).then((u) => { made = u; if (!dead) setPhoto({ url: u, err: '' }); else URL.revokeObjectURL(u); })
      .catch((x) => { if (!dead) setPhoto({ url: '', err: x.message }); });
    return () => { dead = true; if (made) URL.revokeObjectURL(made); };
  }, [vref, hasPhoto]);
  if (!r) return null;
  const car = r.arr === 'Own vehicle', all = r.people.every((p) => r.out[p]);
  const scanOut = async (body) => {
    try {
      const x = await api(`/visits/${vref}/exit-scan`, { body });
      await load();
      toast(x.already ? `${x.person} was already scanned out` : `${x.person} scanned out`);
      return true;
    } catch (e) { toast(e.message); return false; }
  };
  const byCode = async (e) => { e.preventDefault(); if (!code.trim()) return; if (await scanOut({ pass_code: code.trim() })) setCode(''); };
  const leave = async () => { setBusy(true); const ok = await run(() => api(`/visits/${vref}/left`, { body: { vehicle_left: vl } }), 'Marked Left. Passes available again.'); setBusy(false); if (ok) closeModal(); };
  const close = async () => { setBusy(true); const ok = await run(() => api(`/visits/${vref}/close`, { body: { reason } }), 'Visit closed'); setBusy(false); if (ok) closeModal(); };
  return (
    <Modal title={'Exit: ' + r.visitor} onClose={closeModal} footer={<button className={BP} disabled={busy || !(all && (!car || vl))} onClick={leave}>Mark left</button>}>
      {hasPhoto && (
        <div className="mt-3">
          {photo.url ? <img src={photo.url} alt="Entry photo of the vehicle" className="h-28 w-full rounded-lg border border-gray-200 object-cover" />
            : <div className="grid h-14 place-items-center rounded-lg border border-dashed border-gray-300 text-xs text-gray-500">{photo.err || 'Loading entry photo…'}</div>}
          <p className="mt-1 text-xs text-gray-500">Entry photo from the gate check. Compare it with the vehicle leaving.</p>
        </div>
      )}
      <form onSubmit={byCode} className="mt-3 flex gap-2">
        <input id="passcode" aria-label="Pass number" autoFocus autoComplete="off" autoCapitalize="characters" className={`h-9 ${INP}`} placeholder="Scan or type the pass number" value={code} onChange={(e) => setCode(e.target.value)} />
        <button className={BO} type="submit" disabled={!code.trim()}>Scan out</button>
      </form>
      <div className="mt-2 divide-y divide-gray-100">
        {r.people.map((p) => (
          <div key={p} className="flex items-center justify-between py-2 text-sm">
            <span>{p} <span className="text-gray-400">{r.pass[p] || ''}</span></span>
            {r.out[p] ? <Badge v="Left" /> : <button className={`${BO} !h-8`} onClick={() => scanOut({ person: p })}>Scan pass out</button>}
          </div>
        ))}
      </div>
      {car && <div className="mt-2"><Check checked={vl} onChange={setVl}>Vehicle left</Check></div>}
      <div className="mt-4 border-t border-gray-100 pt-3">
        <label className="mb-1 block text-xs font-medium text-gray-500" htmlFor="xr">Close with reason instead</label>
        <div className="flex gap-2">
          <select id="xr" className="h-9 flex-1 rounded-lg border border-gray-300 px-2 text-sm" value={reason} onChange={(e) => setReason(e.target.value)}>
            <option>Vehicle not left</option><option>Overstay</option><option>Pass not returned</option>
          </select>
          <button className={`${BO} !text-rose-600`} disabled={busy} onClick={close}>Close</button>
        </div>
        {reason === 'Pass not returned' && <p className="mt-1 text-xs text-gray-500">Only passes that were not scanned out are marked Lost.</p>}
      </div>
    </Modal>
  );
}

// HOA office: review what the household submitted, then verify. The API repeats the same checks.
export function VerifyModal({ hid }) {
  const { D, run, closeModal } = useApp();
  const h = D.households.find((x) => x.id === hid);
  const [busy, setBusy] = useState(false);
  if (!h) return null;
  const adultHolder = h.members.some((m) => !m.minor && m.n.toLowerCase() === (h.holder || '').toLowerCase());
  const checks = [
    [!!normLot(h.lot), 'Block and lot or house number is filled in'],
    [h.members.length > 0, 'People living here are listed'],
    [adultHolder, 'The account holder is listed as an adult'],
    [!!(h.email && h.ph), 'The account holder’s email and phone are filled in'],
  ];
  const ready = checks.every((x) => x[0]);
  const verify = async () => { setBusy(true); const ok = await run(() => api(`/households/${h.id}/verify`, { method: 'POST' }), `Household ${h.lot} verified`); setBusy(false); if (ok) closeModal(); };
  const row = (l, v) => <div className="flex justify-between gap-4 py-2"><dt className="text-gray-500">{l}</dt><dd className="text-right font-medium">{v || '-'}</dd></div>;
  return (
    <Modal title={`Verify household ${h.lot}`} onClose={closeModal} cancelLabel={h.st === 'Verified' ? 'Close' : 'Cancel'}
      footer={h.st === 'Verified' ? null : <button className={BP} disabled={!ready || busy} onClick={verify}>Verify household</button>}>
      <dl className="mt-3 divide-y divide-gray-100 text-sm">
        {row('Block and lot', h.lot)}{row('Owner', h.owner)}{row('Account holder', h.holder)}{row('Email', h.email)}{row('Phone', h.ph)}
        <div className="flex justify-between gap-4 py-2"><dt className="text-gray-500">Status</dt><dd><Badge v={h.st} /></dd></div>
        {h.st === 'Verified' && row('Verified by', h.vby ? `${h.vby}, ${h.vat}` : '')}
      </dl>
      <h3 className="mt-3 text-sm font-semibold">People living here ({h.members.length})</h3>
      <ul className="mt-1 divide-y divide-gray-100 rounded-lg border border-gray-200 text-sm">
        {h.members.map((m) => <li key={m.n} className="flex justify-between px-3 py-1.5"><span>{m.n}</span>{m.minor ? <span className="text-xs text-amber-700">Minor</span> : <span className="text-xs text-gray-400">Adult</span>}</li>)}
        {!h.members.length && <li className="px-3 py-2 text-gray-500">Nobody listed yet</li>}
      </ul>
      {h.st !== 'Verified' && (
        <ul className="mt-3 space-y-1 text-xs">
          {checks.map(([good, l]) => <li key={l} className={good ? 'text-emerald-700' : 'text-rose-700'}>{good ? '✓' : '✗'} {l}</li>)}
        </ul>
      )}
      {h.st !== 'Verified' && !ready && <p className="mt-2 rounded-lg bg-amber-50 p-2 text-xs text-amber-800">The household has to correct its form before it can be verified.</p>}
    </Modal>
  );
}

// Shows a household sign-in link for the Admin to copy and hand over (the email has the same link when EmailJS is set up).
export function LinkModal({ title, link, who }) {
  const { closeModal, toast } = useApp();
  const copy = async () => {
    try { await navigator.clipboard.writeText(link); toast('Link copied'); }
    catch { document.getElementById('lnk')?.select(); toast('Press Ctrl+C to copy'); }
  };
  return (
    <Modal title={title} onClose={closeModal} cancelLabel="Close" footer={<button className={BP} onClick={copy}>Copy link</button>}>
      <p className="mt-3 text-sm text-gray-600">Send this link to {who}. It signs them in to their household form. It is personal, works for a limited time, and you can issue a new one any time.</p>
      <input id="lnk" readOnly value={link} onFocus={(e) => e.target.select()} className={`mt-3 h-10 ${INP}`} />
    </Modal>
  );
}

// A signed-in person (Admin, guard or HOA office) changes their own password. The first time (an Admin who came by the platform link) no current one is needed.
export function PasswordModal() {
  const { toast } = useApp();
  return (
    <FormModal title="Change password" submit="Change password"
      fields={[{ k: 'current', l: 'Current password', t: 'password' }, { k: 'next', l: 'New password (at least 10 characters)', t: 'password', r: 1 }, { k: 'again', l: 'Repeat the new password', t: 'password', r: 1 }]}
      note="Leave the current password empty only if you have not set one yet."
      onSubmit={async (v) => {
        if (v.next !== v.again) { toast('The two new passwords do not match'); return false; }
        try {
          const r = await api('/me/password', { method: 'PUT', body: { current: v.current || '', new: v.next } });
          if (r?.token) SESS.token = r.token;   // changing the password ends every other sign-in; this device keeps working with the new token
          toast('Password changed'); return true;
        } catch (x) { toast(x.message); return false; }
      }} />
  );
}
