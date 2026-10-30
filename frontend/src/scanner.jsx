import jsQR from 'jsqr';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api.js';
import { ExitModal, GateModal } from './modals.jsx';
import { parseScan } from './qrcore.js';
import { useApp } from './store.jsx';
import { BP, INP, Modal } from './ui.jsx';

const INSIDE = ['Inside', 'Arrived', 'Missing', 'Wrong destination'];

// Guard: scan a visitor's QR (camera) or type the code, then open the right dialog for that visit.
// mode 'gate' = entering (opens the gate check), mode 'exit' = leaving (opens the exit dialog).
export function ScanModal({ mode = 'gate' }) {
  const { load, setModal, closeModal } = useApp();
  const video = useRef(null);
  const busy = useRef(false);
  const [cam, setCam] = useState('starting');   // starting | on | off
  const [msg, setMsg] = useState('');
  const [typed, setTyped] = useState('');

  const handle = useCallback(async (raw) => {
    const code = parseScan(raw);
    if (!code || busy.current) return;
    busy.current = true;
    setMsg('Checking…');
    try {
      const v = await api('/visits/scan', { body: { code } });
      await load();   // make sure the table has this visit before opening its dialog
      const who = `${v.ref} · ${v.visitor}`;
      if (mode === 'gate' && v.status === 'Waiting at gate') { navigator.vibrate?.(60); setModal(<GateModal vref={v.ref} />); return; }
      if (mode === 'exit' && INSIDE.includes(v.status)) { navigator.vibrate?.(60); setModal(<ExitModal vref={v.ref} />); return; }
      if (INSIDE.includes(v.status)) setMsg(`${who} is already inside. Use the Exit page when they leave.`);
      else if (v.status === 'Waiting at gate') setMsg(`${who} has not entered yet. Use the Gate page.`);
      else if (v.status === 'Left' || v.status === 'Closed') setMsg(`${who}: visit already ${v.status.toLowerCase()}. Do not let in on this code.`);
      else setMsg(`${who} is ${v.status}. Not approved to enter.`);
    } catch (x) {
      setMsg(x.message);
    }
    setTimeout(() => { busy.current = false; }, 1800);   // pause so one bad code does not repeat every frame
  }, [load, mode, setModal]);

  useEffect(() => {
    let stream, raf, stop = false;
    let canvas, g;   // made only once a camera is running
    const tick = () => {
      if (stop) return;
      const v = video.current;
      if (v && v.readyState >= 2 && v.videoWidth && !busy.current) {
        const k = Math.min(1, 720 / v.videoWidth);   // downscale for speed
        canvas.width = Math.round(v.videoWidth * k); canvas.height = Math.round(v.videoHeight * k);
        g.drawImage(v, 0, 0, canvas.width, canvas.height);
        const img = g.getImageData(0, 0, canvas.width, canvas.height);
        const hit = jsQR(img.data, img.width, img.height, { inversionAttempts: 'dontInvert' });
        if (hit && hit.data) handle(hit.data);
      }
      raf = requestAnimationFrame(tick);
    };
    (async () => {
      if (!navigator.mediaDevices?.getUserMedia) { setCam('off'); setMsg('Camera needs a secure (https) page. Type the code below instead.'); return; }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
        if (stop) { stream.getTracks().forEach((t) => t.stop()); return; }
        video.current.srcObject = stream;
        video.current.setAttribute('playsinline', 'true');
        await video.current.play();
        canvas = document.createElement('canvas');
        g = canvas.getContext('2d', { willReadFrequently: true });
        setCam('on');
        raf = requestAnimationFrame(tick);
      } catch (x) {
        setCam('off');
        setMsg(x.name === 'NotAllowedError' ? 'Camera is blocked. Allow it in the browser, or type the code below.' : 'No camera found. Type the code below.');
      }
    })();
    return () => { stop = true; cancelAnimationFrame(raf); stream?.getTracks().forEach((t) => t.stop()); };
  }, [handle]);

  const submit = (e) => { e.preventDefault(); handle(typed); };

  return (
    <Modal title={mode === 'exit' ? 'Scan visitor QR (exit)' : 'Scan visitor QR'} onClose={closeModal} cancelLabel="Close"
      footer={<button className={BP} form="scanform" type="submit" disabled={!typed.trim()}>Find visit</button>}>
      <div className="relative mt-3 aspect-square w-full overflow-hidden rounded-xl bg-slate-900">
        <video ref={video} muted playsInline className={`h-full w-full object-cover ${cam === 'on' ? '' : 'invisible'}`} />
        {cam === 'on' && <div className="pointer-events-none absolute inset-[18%] rounded-2xl border-2 border-white/80" />}
        {cam !== 'on' && <div className="absolute inset-0 grid place-items-center p-6 text-center text-sm text-slate-300">{cam === 'starting' ? 'Starting camera…' : 'Camera is not available'}</div>}
      </div>
      <p role="status" aria-live="polite" className={`mt-2 min-h-[1.25rem] text-sm ${msg && msg !== 'Checking…' ? 'text-rose-600' : 'text-gray-500'}`}>
        {msg || 'Point the camera at the visitor’s QR code.'}
      </p>
      <form id="scanform" onSubmit={submit} className="mt-2">
        <label htmlFor="scancode" className="mb-1 block text-xs font-medium text-gray-500">Or type the code or reference (for example VS-0004)</label>
        <input id="scancode" className={`h-10 ${INP}`} value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" autoCapitalize="off" spellCheck="false" />
      </form>
    </Modal>
  );
}
