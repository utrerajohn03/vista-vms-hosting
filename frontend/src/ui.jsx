import { useEffect, useRef, useState } from 'react';
import { ICON } from './icons.js';
import { BADGE, BC } from './config.js';
import { passPayload, qrSvgParts } from './qrcore.js';

export const BP = 'inline-flex h-9 items-center gap-2 rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50';
export const BO = 'inline-flex h-9 items-center gap-2 rounded-md border border-gray-300 bg-white px-3 text-sm font-medium text-gray-700 hover:bg-gray-50';
export const INP = 'w-full rounded-lg border border-gray-300 bg-white px-3 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/40';

export function Ic({ n, c = 'h-4 w-4' }) {
  return (
    <svg className={`${c} shrink-0`} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: ICON[n] }} />
  );
}

export function Badge({ v }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium ${BADGE[BC[v] || 'n']}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />{String(v ?? '')}
    </span>
  );
}

export function Card({ title, children }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm lg:p-5">
      <h2 className="mb-3 text-[15px] font-semibold text-gray-900">{title}</h2>
      {children}
    </div>
  );
}

export function Kpi({ i, c, v, l, x }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition hover:shadow-md lg:p-5">
      <div className="flex items-center gap-3">
        <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${c}`}><Ic n={i} c="h-5 w-5" /></div>
        <div>
          <div className="text-2xl font-semibold text-gray-900">{v}</div>
          <div className="text-sm text-gray-500">{l} {x}</div>
        </div>
      </div>
    </div>
  );
}

// Draggable dialog. `footer` sits next to the Cancel button; pass cancelLabel="Close" for read-only dialogs.
export function Modal({ title, onClose, footer, cancelLabel = 'Cancel', children }) {
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const drag = useRef(null);
  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-900/40 p-4" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="w-full max-w-md rounded-xl bg-white shadow-2xl" role="dialog" aria-modal="true" aria-label={title} style={{ transform: `translate(${pos.x}px,${pos.y}px)` }}>
        <div className="flex cursor-move select-none items-center justify-between border-b border-gray-200 px-5 py-4"
          onPointerDown={(e) => { if (e.target.closest('button')) return; drag.current = { sx: e.clientX - pos.x, sy: e.clientY - pos.y }; e.currentTarget.setPointerCapture(e.pointerId); }}
          onPointerMove={(e) => { if (drag.current) setPos({ x: e.clientX - drag.current.sx, y: e.clientY - drag.current.sy }); }}
          onPointerUp={() => { drag.current = null; }}>
          <h2 className="text-[15px] font-semibold text-gray-900">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="text-gray-400 hover:text-gray-600"><Ic n="x" c="h-5 w-5" /></button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto px-5 pb-4 pt-1">{children}</div>
        <div className="sticky bottom-0 flex justify-end gap-2 rounded-b-xl border-t border-gray-200 bg-gray-50 px-5 py-3">
          <button className={BO} onClick={onClose}>{cancelLabel}</button>{footer}
        </div>
      </div>
    </div>
  );
}

export function Check({ checked, onChange, children }) {
  return (
    <label className="flex items-center gap-2 py-1.5 text-sm">
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 rounded border-gray-300 text-blue-600" /> {children}
    </label>
  );
}

// Real, scannable QR code. White background with the 4-module quiet zone the QR spec needs, so it reads on dark pages too.
// `t` is the pass token; the code holds "VISTA:<token>". Pass raw=true to encode `t` exactly as given.
export function Qr({ t, raw = false, size = 'h-44 w-44' }) {
  const { d, size: vb } = qrSvgParts(raw ? t : passPayload(t));
  return (
    <svg viewBox={`0 0 ${vb} ${vb}`} className={`${size} rounded-xl bg-white`} shapeRendering="crispEdges" role="img" aria-label="QR pass">
      <rect width={vb} height={vb} fill="#fff" /><path d={d} fill="#000" />
    </svg>
  );
}
