// CSV download for the Admin pages that have an Export button. Built in the browser from what is already on screen.
const cell = (v) => {
  const t = String(v ?? '');
  return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
};

export function toCsv(rows) {
  return rows.map((r) => r.map(cell).join(',')).join('\r\n');
}

export function pageRows(page, D) {
  if (page === 'audit') return [['Time', 'Actor', 'Role', 'Action'], ...D.audit.map((a) => [a.time, a.actor, a.role, a.action])];
  if (page === 'reports' && D.report) {
    const r = D.report;
    return [
      ['Report (last 7 days)', 'Value'], ['Visits', r.week], ['Visits the 7 days before', r.prev], ['People including groups', r.people],
      ['Missing flags', r.missing], [],
      ['Day', 'Visits'], ...r.days, [],
      ['Arrival method', 'Visits'], ...r.arr, [],
      ['Exception', 'Count'], ...r.exc,
    ];
  }
  return null;
}

export function downloadCsv(name, rows) {
  const url = URL.createObjectURL(new Blob(['\ufeff' + toCsv(rows)], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
