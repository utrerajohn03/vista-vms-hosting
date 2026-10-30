import { api } from '../api.js';
import { useActions } from '../actions.jsx';
import Table from '../components/Table.jsx';
import { NAVS, PG, RL } from '../config.js';
import { useApp } from '../store.jsx';
import { PasswordModal } from '../modals.jsx';
import { ScanModal } from '../scanner.jsx';
import { BO, BP, Ic } from '../ui.jsx';
import { downloadCsv, pageRows } from '../export.js';
import { Dash, HForm, MapEd, Rep, Sett } from './Custom.jsx';

const CUSTOM = { dash: Dash, mapEd: MapEd, rep: Rep, sett: Sett, hform: HForm };

export default function Shell() {
  const { D, S, set, go, goTab, signOut, backToPlatform, run, toast, setModal } = useApp();
  const { openAdd } = useActions();
  const P = PG[S.page] || PG.dashboard;
  const vname = D.prop?.name || S.village?.name || 'the village';
  const tabs = P.tabs || [];
  const ti = S.tab[S.page] || 0;
  const c = { ...P, ...(tabs[ti] || {}) };
  const waiting = D.visits.filter((r) => r.st === 'Waiting at gate').length;
  const openAlerts = D.alerts.filter((a) => a.st === 'Open').length;
  const Body = c.cust ? CUSTOM[c.cust] : null;
  const advance = () => run(() => api('/jobs/missing?simulate_hours=3', { method: 'POST' }), (r) => (r.flagged ? r.flagged + ' visit(s) flagged Missing' : 'Clock advanced 3 hours, nothing missing'));
  const initials = (S.me || '').split(' ').map((w) => w[0]).slice(0, 2).join('').toUpperCase();
  const safeTop = { paddingTop: 'env(safe-area-inset-top,0px)' };

  return (
    <div className="min-h-screen">
      {S.sa && (
        <div className="relative z-50 flex flex-wrap items-center justify-between gap-2 bg-indigo-600 px-4 py-2 text-sm text-white lg:pl-64" role="status">
          <span>Super Admin: you are working inside <b>{vname}</b> as its Admin. Everything you do is logged as Super Admin.</span>
          <button className="rounded-md border border-white/40 px-2.5 py-1 text-xs font-medium hover:bg-white/10" onClick={backToPlatform}>Back to platform</button>
        </div>
      )}
      <aside className={`fixed inset-y-0 left-0 z-40 flex w-60 flex-col bg-slate-900 transition-transform lg:translate-x-0 ${S.side ? '' : '-translate-x-full'}`}>
        <div className="flex h-16 items-center gap-3 border-b border-slate-800 px-4" style={safeTop}>
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600 text-white"><Ic n="house" c="h-5 w-5" /></div>
          <span className="font-semibold text-white">Village VMS</span>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 pb-4" aria-label="Main">
          {NAVS[S.role].map(([g, items]) => (
            <div key={g || 'x'} className={g ? 'mt-5' : 'mt-5 border-t border-slate-800 pt-3'}>
              {g && <div className="px-3 pb-2 text-[11px] font-bold uppercase tracking-wider text-slate-500">{g}</div>}
              {items.map(([k, l, i]) => (
                <button key={k} onClick={() => go(k)} className={`mb-0.5 flex h-10 w-full items-center gap-3 rounded-lg px-3 text-left text-sm font-medium ${k === S.page ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-800/60 hover:text-white'}`}>
                  <Ic n={i} /><span className="flex-1 truncate">{l}</span>
                  {(k === 'visits' || k === 'g_gate') && <span className="rounded-full bg-blue-600 px-2 py-0.5 text-xs text-white">{waiting}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="border-t border-slate-800 px-4 py-3 text-xs text-slate-500">Vista VMS</div>
      </aside>
      {S.side && <div className="fixed inset-0 z-30 bg-slate-900/50 lg:hidden" onClick={() => set({ side: false })} />}

      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between bg-slate-900 px-4 lg:px-6" style={{ ...safeTop, height: 'calc(4rem + env(safe-area-inset-top,0px))' }}>
          <div className="flex items-center gap-3">
            <button className="text-slate-300 lg:hidden" aria-label="Menu" onClick={() => set({ side: true })}><Ic n="menu" c="h-6 w-6" /></button>
            <div className="flex items-center gap-2 rounded-lg bg-slate-800 px-3 py-1.5">
              <span className="flex h-6 w-6 items-center justify-center rounded bg-indigo-600 text-xs font-semibold text-white">{(vname[0] || 'V').toUpperCase()}</span>
              <span className="text-sm text-white">{vname}</span>
            </div>
          </div>
          <div className="flex items-center gap-4 text-slate-300">
            <button aria-label="Mail" className="hidden sm:block"><Ic n="mail" c="h-5 w-5" /></button>
            <button aria-label="Alerts" onClick={() => { if (S.role === 'admin' || S.role === 'guard') go('alerts'); }} className="relative">
              <Ic n="bell" c="h-5 w-5" />
              <span className="absolute -right-1.5 -top-1.5 rounded-full bg-rose-600 px-1 text-[10px] font-semibold text-white">{openAlerts}</span>
            </button>
            <span className="hidden text-xs text-slate-400 sm:block">{D.now || ''}</span>
            <span className="hidden text-xs text-white sm:block">{RL[S.role]}</span>
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-500 text-xs font-semibold text-white" title={S.me}>{initials}</span>
            {S.acct && <button onClick={() => setModal(<PasswordModal />)} className="hidden rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800 sm:block">Change password</button>}
            <button onClick={signOut} className="rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800">Sign out</button>
          </div>
        </header>

        <main className="space-y-4 p-5 lg:p-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h1 className="text-xl font-semibold text-gray-900">{P.t}</h1><p className="text-sm text-gray-500">{P.cust === 'dash' ? `Today at ${vname}` : P.s}</p></div>
            <div className="flex flex-wrap gap-2">
              {P.scan && <button className={BP} onClick={() => setModal(<ScanModal mode={P.scan} />)}><Ic n="qr" /> Scan QR</button>}
              {c.add ? <button className={BP} onClick={() => openAdd(c)}><Ic n="plus" /> {c.add.l}</button>
                : P.adv ? <button className={BO} onClick={advance}><Ic n="clock" /> Advance clock 3 hours</button>
                : P.export ? <button className={BO} onClick={() => { const rows = pageRows(S.page, D); if (!rows) { toast('Nothing to export yet'); return; } downloadCsv(`${S.page}-${new Date().toLocaleDateString('en-CA')}.csv`, rows); toast('Export downloaded'); }}><Ic n="dl" /> Export</button> : null}
            </div>
          </div>
          {tabs.length > 0 && (
            <div className="inline-flex max-w-full overflow-x-auto rounded-lg border border-gray-200 bg-white p-1">
              {tabs.map((t, i) => (
                <button key={t.k} onClick={() => goTab(i)} className={`h-8 whitespace-nowrap rounded-md px-3 text-sm font-medium ${i === ti ? 'bg-gray-100 text-gray-900' : 'text-gray-600 hover:text-gray-900'}`}>{t.k}</button>
              ))}
            </div>
          )}
          {Body ? <Body /> : <Table c={c} />}
        </main>
      </div>
    </div>
  );
}
