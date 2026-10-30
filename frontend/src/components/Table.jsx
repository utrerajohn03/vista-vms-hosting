import { useEffect, useState } from 'react';
import { useActions } from '../actions.jsx';
import { useApp } from '../store.jsx';
import { BO, Badge, INP, Ic } from '../ui.jsx';

// Search, status filter, paging, desktop table and mobile cards for any list in the state snapshot.
export default function Table({ c }) {
  const { D, S, set, toast } = useApp();
  const { act, view } = useActions();
  const [menu, setMenu] = useState(null);
  useEffect(() => {
    const close = () => setMenu(null);
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, []);
  if (!c.d) return null;

  const fk = c.fk || 'st', q = S.q.toLowerCase();
  const all = (D[c.d] || []).filter(c.f || (() => true));
  const options = [...new Set(all.map((r) => r[fk]).filter(Boolean))];
  const cur = all.filter((r) => (!S.sf || r[fk] === S.sf) && (!q || Object.values(r).join(' ').toLowerCase().includes(q)));
  const n = cur.length, pp = Math.max(1, Math.ceil(n / S.size)), pg = Math.min(S.pg, pp);
  const a = (pg - 1) * S.size, rows = cur.slice(a, a + S.size);
  const hasA = !!c.acts;
  const main = (r) => (c.main ? c.main(r) : '');
  const badgeCol = c.cols.find((x) => x[2] === 'b' && x[0] !== 'flag')?.[0] || 'st';

  const filters = (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-gray-200 bg-white p-3">
      <select className="h-9 rounded-lg border border-gray-300 bg-white px-3 text-sm" aria-label="Filter" value={S.sf} onChange={(e) => set({ sf: e.target.value, pg: 1 })}>
        <option value="">All {fk === 'st' ? 'statuses' : 'roles'}</option>
        {options.map((o) => <option key={o}>{o}</option>)}
      </select>
      <div className="relative min-w-[180px] flex-1 sm:max-w-md">
        <span className="absolute left-3 top-2.5 text-gray-400"><Ic n="search" /></span>
        <input id="sq" value={S.q} placeholder="Search…" onChange={(e) => set({ q: e.target.value, pg: 1 })} className={`h-9 pl-9 ${INP}`} />
      </div>
      <div className="ml-auto flex gap-2">
        <button className={BO} onClick={() => toast('Filters applied')}><Ic n="funnel" /> Filters</button>
        <button className={BO} onClick={() => toast('Export started')}><Ic n="dl" /> Export</button>
      </div>
    </div>
  );

  if (!n) {
    return (
      <>
        {filters}
        <div className="rounded-2xl border border-gray-200 bg-white py-16 text-center">
          <Ic n="win" c="mx-auto h-9 w-9 text-gray-400" />
          <div className="mt-3 font-semibold text-gray-700">Nothing in “{c.k || c.t}” yet</div>
          <div className="text-sm text-gray-500">New records will appear here.</div>
        </div>
      </>
    );
  }

  const openMenu = (e, r) => {
    e.stopPropagation();
    const b = e.currentTarget.getBoundingClientRect();
    setMenu({ r, top: b.bottom + 4, left: Math.max(8, Math.min(b.right - 208, window.innerWidth - 216)) });
  };

  return (
    <>
      {filters}
      <div className="hidden overflow-x-auto rounded-xl border border-gray-200 bg-white md:block">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
            <tr>{c.cols.map((x) => <th key={x[0]} className="px-4 py-3">{x[1]}</th>)}{hasA && <th className="px-4 py-3 text-right">Actions</th>}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.id || r.ref || r.pass || i} className="border-t border-gray-100 hover:bg-gray-50">
                {c.cols.map((x, j) => (
                  <td key={x[0]} className="px-4 py-3.5">
                    {x[2] === 'b' ? <Badge v={r[x[0]]} /> : <span className={j ? 'text-gray-700' : 'font-semibold text-gray-900'}>{String(r[x[0]] ?? '')}</span>}
                  </td>
                ))}
                {hasA && (
                  <td className="px-4 py-3.5">
                    <div className="flex items-center justify-end gap-2">
                      {main(r) && <button className="inline-flex h-8 items-center rounded-md bg-blue-600 px-3 text-xs font-medium text-white hover:bg-blue-700" onClick={() => act(r, main(r), c)}>{main(r)}</button>}
                      <button className="text-xs font-medium text-blue-600 hover:underline" onClick={() => view(r, c)}>View</button>
                      {c.acts(r).length > 0 && (
                        <button aria-label="More actions" onClick={(e) => openMenu(e, r)} className="rounded p-1 text-gray-400 hover:bg-gray-100">
                          <svg className="h-4 w-4" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="3" r="1.3" /><circle cx="8" cy="8" r="1.3" /><circle cx="8" cy="13" r="1.3" /></svg>
                        </button>
                      )}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-2 md:hidden">
        {rows.map((r, i) => (
          <div key={r.id || r.ref || r.pass || i} className="rounded-xl border border-gray-200 bg-white p-3.5" onClick={() => view(r, c)}>
            <div className="flex items-start justify-between gap-2">
              <span className="font-semibold">{String(r[c.cols[0][0]] ?? '')}</span>
              <Badge v={r[badgeCol] || ''} />
            </div>
            <div className="mt-1 text-sm text-gray-500">{c.cols.slice(1).filter((x) => x[2] !== 'b').map((x) => String(r[x[0]] ?? '')).join(' · ')}</div>
            {main(r) && <button className="mt-2 h-8 rounded-md bg-blue-600 px-3 text-xs font-medium text-white" onClick={(e) => { e.stopPropagation(); act(r, main(r), c); }}>{main(r)}</button>}
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-gray-600">
        <div className="flex flex-wrap items-center gap-3">
          <span>Show</span>
          <select className="h-9 rounded-lg border border-gray-300 bg-white px-2" value={S.size} onChange={(e) => set({ size: +e.target.value, pg: 1 })}>
            {[5, 10, 20, 50].map((x) => <option key={x}>{x}</option>)}
          </select>
          <span>entries</span>
          <span>Showing <b>{a + 1}–{a + rows.length}</b> of <b>{n}</b></span>
        </div>
        <div className="flex gap-1">
          <button disabled={pg < 2} onClick={() => set({ pg: pg - 1 })} className="h-9 rounded-md border border-gray-300 bg-white px-3 disabled:text-gray-400">Previous</button>
          {Array.from({ length: Math.min(pp, 5) }, (_, i) => i + 1).map((i) => (
            <button key={i} onClick={() => set({ pg: i })} className={`h-9 min-w-9 rounded-md border px-3 text-sm ${i === pg ? 'border-blue-600 bg-blue-600 text-white' : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'}`}>{i}</button>
          ))}
          <button disabled={pg >= pp} onClick={() => set({ pg: pg + 1 })} className="h-9 rounded-md border border-gray-300 bg-white px-3 disabled:text-gray-400">Next</button>
        </div>
      </div>

      {menu && (
        <div className="fixed z-50 w-52 rounded-lg border border-gray-200 bg-white py-1 shadow-lg" style={{ top: menu.top, left: menu.left }}>
          {c.acts(menu.r).map((x) => (
            <button key={x} className={`block w-full px-3 py-2 text-left text-sm hover:bg-gray-50 ${/Decline|Reject|Remove|Deactivate|lost/.test(x) ? 'text-rose-600' : 'text-gray-700'}`}
              onClick={() => { setMenu(null); act(menu.r, x, c); }}>{x}</button>
          ))}
        </div>
      )}
    </>
  );
}
