import { useCallback, useEffect, useState } from 'react';
import { api } from '../api.js';
import { FormModal } from '../modals.jsx';
import { useApp } from '../store.jsx';
import { BO, BP, Badge, Card, INP, Ic, Kpi, Modal } from '../ui.jsx';

// Platform level: the Super Admin. No village here. Create properties, assign one Admin to each, watch the platform,
// switch a village off, or open one as its Admin (always audited as "Super Admin").

function LinksModal({ title, intro, items }) {
  const { closeModal, toast } = useApp();
  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); toast('Link copied'); } catch { toast('Select the link and press Ctrl+C'); }
  };
  return (
    <Modal title={title} onClose={closeModal} cancelLabel="Close">
      <p className="mt-3 text-sm text-gray-600">{intro}</p>
      {items.filter((x) => x.link).map((x) => (
        <div key={x.label} className="mt-3">
          <label className="mb-1 block text-sm font-medium text-gray-700" htmlFor={`lk_${x.label}`}>{x.label}</label>
          <div className="flex gap-2">
            <input id={`lk_${x.label}`} readOnly value={x.link} onFocus={(e) => e.target.select()} className={`h-10 ${INP}`} />
            <button className={BO} onClick={() => copy(x.link)}>Copy</button>
          </div>
          {x.note && <p className="mt-1 text-xs text-gray-500">{x.note}</p>}
        </div>
      ))}
    </Modal>
  );
}

export default function Platform() {
  const { S, signOut, enterProperty, setModal, toast } = useApp();
  const [ov, setOv] = useState(null);
  const [err, setErr] = useState('');
  const [tab, setTab] = useState(0);
  const [busy, setBusy] = useState('');
  const load = useCallback(async () => {
    try { setOv(await api('/platform/overview')); setErr(''); } catch (x) { setErr(x.message); }
  }, []);
  useEffect(() => { load(); const id = setInterval(load, 20000); return () => clearInterval(id); }, [load]);

  // One call, then reload what the page shows. Returns true when it worked.
  const run = async (fn, ok) => {
    try { const r = await fn(); await load(); if (ok) toast(ok); return r ?? true; } catch (x) { toast(x.message); return false; }
  };
  const types = ov?.types || ['village'];
  const adminLinks = (r, link) => <LinksModal title={`Admin link for ${r.name}`} intro={`Send this to ${r.admin || 'the Admin'}. It signs them in as the Admin of ${r.name}. It is personal and works for a limited time. It was also emailed when email is set up.`} items={[{ label: 'Admin sign-in link', link }]} />;

  const create = () => setModal(
    <FormModal title="New property" submit="Create property"
      note="The village link is made from the name plus a random code. The Admin gets a personal sign-in link by email."
      fields={[{ k: 'name', l: 'Village name', r: 1 }, { k: 'type', l: 'Village type', t: 'select', o: types },
        { k: 'admin_name', l: 'Admin name', r: 1 }, { k: 'admin_email', l: 'Admin email', t: 'email', r: 1 }]}
      onSubmit={async (v) => {
        const r = await run(() => api('/platform/properties', { body: v }));
        if (!r || r === true) return false;
        return <LinksModal title="Property created" intro="Give the Admin their sign-in link. The village link is for visitors, guards, the HOA office and households: the Admin prints it as the gate QR."
          items={[{ label: 'Admin sign-in link', link: r.admin_link, note: 'Personal. Works once the Admin opens it on the main site.' }, { label: 'Village link', link: r.village_link }]} />;
      }} />,
  );
  const edit = (r) => setModal(
    <FormModal title={`Edit ${r.name}`} submit="Save changes" note="The village link never changes, so printed gate QR codes keep working."
      fields={[{ k: 'name', l: 'Village name', r: 1 }, { k: 'type', l: 'Village type', t: 'select', o: types }]} initial={{ name: r.name, type: r.type }}
      onSubmit={(v) => run(() => api(`/platform/properties/${r.id}`, { method: 'PATCH', body: { name: v.name, type: v.type } }), 'Saved')} />,
  );
  const assign = (r) => setModal(
    <FormModal title={`Assign Admin: ${r.name}`} submit="Assign Admin" note={r.admin ? `There is one Admin per property. This replaces ${r.admin}, and their old link stops working.` : 'There is one Admin per property.'}
      fields={[{ k: 'name', l: 'Admin name', r: 1 }, { k: 'email', l: 'Admin email', t: 'email', r: 1 }]} initial={{ name: '', email: '' }}
      onSubmit={async (v) => {
        const r2 = await run(() => api(`/platform/properties/${r.id}/admin`, { method: 'PUT', body: v }));
        return r2 && r2 !== true ? adminLinks({ ...r, admin: v.name }, r2.admin_link) : false;
      }} />,
  );
  const link = async (r) => {
    setBusy(r.id);
    try { const x = await api(`/platform/properties/${r.id}/admin-link`, { method: 'POST' }); await load(); setModal(adminLinks(r, x.admin_link)); } catch (x) { toast(x.message); }
    setBusy('');
  };
  const toggle = (r) => setModal(
    <FormModal title={`${r.active ? 'Switch off' : 'Switch on'} ${r.name}?`} submit={r.active ? 'Switch off' : 'Switch on'} fields={[]}
      note={r.active ? 'Nobody can open this village until you switch it on again: not visitors, staff, households or its Admin. Its data is kept.' : 'The village opens for everyone again.'}
      onSubmit={() => run(() => api(`/platform/properties/${r.id}`, { method: 'PATCH', body: { active: !r.active } }), r.active ? 'Village switched off' : 'Village switched on')} />,
  );
  const open = async (r) => {
    setBusy(r.id);
    try { await enterProperty(r.id); } catch (x) { toast(x.message); }
    setBusy('');
  };

  const T = ov?.totals;
  const th = 'px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-gray-500';
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between bg-slate-900 px-4 lg:px-6" style={{ paddingTop: 'env(safe-area-inset-top,0px)', height: 'calc(4rem + env(safe-area-inset-top,0px))' }}>
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white"><Ic n="shield" c="h-5 w-5" /></div>
          <span className="font-semibold text-white">Vista VMS</span>
          <span className="rounded-full bg-indigo-500/20 px-2.5 py-0.5 text-xs font-medium text-indigo-200">Platform · Super Admin</span>
        </div>
        <div className="flex items-center gap-4 text-slate-300">
          <span className="hidden text-xs text-white sm:block">{S.me}</span>
          <button onClick={signOut} className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800">Sign out</button>
        </div>
      </header>
      <main className="space-y-4 p-5 lg:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h1 className="text-xl font-semibold text-gray-900">Properties</h1><p className="text-sm text-gray-500">Create villages, assign each its one Admin, and monitor the platform. You are not part of any village.</p></div>
          <button className={BP} onClick={create}><Ic n="plus" /> New property</button>
        </div>
        {err && <p role="alert" className="rounded-lg bg-rose-50 p-2.5 text-sm text-rose-700">{err}</p>}
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
          <Kpi i="house" c="bg-blue-50 text-blue-600" v={T ? T.properties : '-'} l="Properties" />
          <Kpi i="shield" c="bg-emerald-50 text-emerald-600" v={T ? T.active : '-'} l="Active" />
          <Kpi i="people" c="bg-indigo-50 text-indigo-600" v={T ? T.households : '-'} l="Households" />
          <Kpi i="clip" c="bg-amber-50 text-amber-600" v={T ? T.today : '-'} l="Visits today" />
          <Kpi i="user" c="bg-emerald-50 text-emerald-600" v={T ? T.inside : '-'} l="Inside now" />
          <Kpi i="warn" c="bg-rose-50 text-rose-600" v={T ? T.alerts : '-'} l="Open alerts" />
        </div>
        {T && T.no_admin > 0 && <p className="rounded-lg bg-amber-50 p-2.5 text-sm text-amber-800">{T.no_admin} {T.no_admin === 1 ? 'property has' : 'properties have'} no Admin yet. Use Assign Admin.</p>}
        <div className="inline-flex rounded-lg border border-gray-200 bg-white p-1">
          {['Properties', 'Platform audit'].map((t, i) => (
            <button key={t} onClick={() => setTab(i)} className={`h-8 rounded-md px-3 text-sm font-medium ${i === tab ? 'bg-gray-100 text-gray-900' : 'text-gray-600 hover:text-gray-900'}`}>{t}</button>
          ))}
        </div>
        {tab === 0 && (
          <Card title="All properties">
            {!ov ? <p className="text-sm text-gray-500">Loading…</p> : !ov.properties.length ? <p className="text-sm text-gray-500">No properties yet. Create the first one.</p> : (
              <div className="-mx-5 overflow-x-auto">
                <table className="w-full min-w-[960px] text-sm">
                  <thead><tr className="border-b border-gray-200"><th className={th}>Village</th><th className={th}>Admin</th><th className={th}>Households</th><th className={th}>Today</th><th className={th}>Inside</th><th className={th}>Alerts</th><th className={th}>Status</th><th className={th}>Actions</th></tr></thead>
                  <tbody>
                    {ov.properties.map((r) => (
                      <tr key={r.id} className="border-b border-gray-100 align-top">
                        <td className="px-4 py-3"><div className="font-medium text-gray-900">{r.name}</div><div className="text-xs text-gray-500">/{r.slug} · {r.type}</div></td>
                        <td className="px-4 py-3">{r.admin ? <><div>{r.admin}</div><div className="text-xs text-gray-500">{r.admin_email}</div></> : <span className="text-amber-700">No Admin</span>}</td>
                        <td className="px-4 py-3">{r.verified}/{r.households} verified</td>
                        <td className="px-4 py-3">{r.today}</td><td className="px-4 py-3">{r.inside}</td>
                        <td className="px-4 py-3">{r.alerts ? <span className="font-semibold text-rose-600">{r.alerts}</span> : 0}</td>
                        <td className="px-4 py-3"><Badge v={r.active ? 'Active' : 'Inactive'} /></td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1.5">
                            <button className={`${BP} !h-8 !px-3`} disabled={busy === r.id} onClick={() => open(r)}>Open</button>
                            <button className={`${BO} !h-8`} onClick={() => edit(r)}>Edit</button>
                            <button className={`${BO} !h-8`} onClick={() => assign(r)}>{r.admin ? 'Change Admin' : 'Assign Admin'}</button>
                            {r.admin && <button className={`${BO} !h-8`} disabled={busy === r.id} onClick={() => link(r)}>Admin link</button>}
                            <button className={`${BO} !h-8 ${r.active ? '!text-rose-600' : ''}`} onClick={() => toggle(r)}>{r.active ? 'Switch off' : 'Switch on'}</button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}
        {tab === 1 && (
          <Card title="Platform audit">
            <p className="mb-3 text-sm text-gray-500">Every Super Admin action. Signing in to a property is also written in that property&apos;s own audit log as Super Admin.</p>
            <div className="-mx-5 overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead><tr className="border-b border-gray-200"><th className={th}>Time</th><th className={th}>Actor</th><th className={th}>Property</th><th className={th}>Action</th></tr></thead>
                <tbody>
                  {(ov?.audit || []).map((a, i) => <tr key={i} className="border-b border-gray-100"><td className="px-4 py-2.5 text-gray-500">{a.time}</td><td className="px-4 py-2.5">{a.actor}</td><td className="px-4 py-2.5">{a.property}</td><td className="px-4 py-2.5">{a.action}</td></tr>)}
                  {ov && !ov.audit.length && <tr><td className="px-4 py-3 text-gray-500" colSpan="4">Nothing yet.</td></tr>}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </main>
    </div>
  );
}
