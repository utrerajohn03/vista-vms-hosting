// QR codes: what we draw must be readable by a real QR decoder, and the gate must understand what it reads.
// No API needed. Run: npm test
import jsQR from 'jsqr';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { QR_PREFIX, parseScan, passPayload, qrMatrix } from '../src/qrcore.js';
import { Qr } from '../src/ui.jsx';

// Draw the matrix as pixels (with the 4-module quiet zone) and decode it like a camera frame.
function decode(text, scale = 6) {
  const m = qrMatrix(text), n = m.length, quiet = 4, W = (n + quiet * 2) * scale;
  const px = new Uint8ClampedArray(W * W * 4).fill(255);
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) {
    if (!m[r][c]) continue;
    for (let y = 0; y < scale; y++) for (let x = 0; x < scale; x++) {
      const o = (((r + quiet) * scale + y) * W + (c + quiet) * scale + x) * 4;
      px[o] = px[o + 1] = px[o + 2] = 0;
    }
  }
  return jsQR(px, W, W)?.data;
}

describe('QR pass', () => {
  it('round-trips real server-style tokens through a decoder', () => {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
    for (let i = 0; i < 60; i++) {
      const tok = Array.from({ length: 12 }, (_, j) => chars[(i * 7 + j * 13 + i * j) % chars.length]).join('');
      expect(decode(passPayload(tok))).toBe(QR_PREFIX + tok);
      expect(parseScan(decode(passPayload(tok)))).toBe(tok);
    }
  });

  it('parseScan accepts the Vista code, a bare token and a reference, and ignores blanks', () => {
    expect(parseScan('VISTA:abc_-123')).toBe('abc_-123');
    expect(parseScan('  vista: abc ')).toBe('abc');
    expect(parseScan('abc')).toBe('abc');
    expect(parseScan('VS-0004')).toBe('VS-0004');
    expect(parseScan('   ')).toBe('');
    expect(parseScan(null)).toBe('');
  });

  it('draws different codes for different tokens, not a placeholder', () => {
    const a = render(<Qr t="tokenAAAAAAAA" />).container.querySelector('path').getAttribute('d');
    const b = render(<Qr t="tokenBBBBBBBB" />).container.querySelector('path').getAttribute('d');
    expect(a).not.toBe(b);
    expect(a.length).toBeGreaterThan(200);
  });
});
