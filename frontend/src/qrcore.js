import qrcode from 'qrcode-generator';

// What a visitor's QR holds. The prefix lets the gate tell a Vista pass from any other QR code.
export const QR_PREFIX = 'VISTA:';
export const passPayload = (token) => QR_PREFIX + String(token || '').trim();

// Real QR matrix (error correction M, version picked automatically). Returns an array of rows of booleans.
export function qrMatrix(text) {
  const q = qrcode(0, 'M');
  q.addData(String(text));
  q.make();
  const n = q.getModuleCount();
  return Array.from({ length: n }, (_, r) => Array.from({ length: n }, (_, c) => q.isDark(r, c)));
}

// One SVG path for all dark modules (small and crisp at any size). `quiet` = white border in modules (the QR spec needs 4).
export function qrSvgParts(text, quiet = 4) {
  const m = qrMatrix(text), n = m.length;
  let d = '';
  for (let r = 0; r < n; r++) {
    let c = 0;
    while (c < n) {
      if (!m[r][c]) { c++; continue; }
      let e = c;
      while (e < n && m[r][e]) e++;
      d += `M${c + quiet} ${r + quiet}h${e - c}v1h${-(e - c)}z`;
      c = e;
    }
  }
  const size = n + quiet * 2;
  return { d, size };
}

// Full standalone SVG markup (used for download and printing).
export function qrSvgString(text, px = 320) {
  const { d, size } = qrSvgParts(text);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="${px}" height="${px}" shape-rendering="crispEdges">` +
    `<rect width="${size}" height="${size}" fill="#fff"/><path d="${d}" fill="#000"/></svg>`;
}

// Turn whatever the guard scanned or typed into a lookup code: Vista pass, bare token, or a VS-0001 reference.
export function parseScan(raw) {
  let s = String(raw || '').trim();
  if (!s) return '';
  if (s.toUpperCase().startsWith(QR_PREFIX)) s = s.slice(QR_PREFIX.length).trim();
  return s;
}

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Open a print-ready page with one big QR code. Returns false when the browser blocked the pop-up.
export function printQrPage(title, subtitle, text) {
  const w = window.open('', '_blank', 'width=640,height=840');
  if (!w) return false;
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${esc(title)}</title>
<style>body{font-family:system-ui,sans-serif;text-align:center;padding:48px 24px;color:#0f172a}h1{font-size:28px;margin:0 0 6px}
p{margin:6px 0;color:#475569}svg{width:420px;max-width:100%;height:auto;margin:28px auto 12px;display:block}small{color:#64748b;word-break:break-all}
@media print{body{padding:16mm}}</style></head><body><h1>${esc(title)}</h1><p>${esc(subtitle)}</p>${qrSvgString(text, 420)}<small>${esc(text)}</small>
<script>window.onload=function(){setTimeout(function(){window.print()},250)}</script></body></html>`);
  w.document.close();
  return true;
}

// Save a QR code as a PNG image (so a visitor can keep it in their photos).
export function downloadQrPng(text, filename = 'visit-qr.png', px = 640) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = c.height = px;
      const g = c.getContext('2d');
      g.imageSmoothingEnabled = false;
      g.fillStyle = '#fff'; g.fillRect(0, 0, px, px);
      g.drawImage(img, 0, 0, px, px);
      c.toBlob((b) => {
        if (!b) { reject(new Error('Could not make the image')); return; }
        const a = document.createElement('a');
        a.href = URL.createObjectURL(b); a.download = filename;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
        resolve(true);
      }, 'image/png');
    };
    img.onerror = () => reject(new Error('Could not make the image'));
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(qrSvgString(text, px));
  });
}
