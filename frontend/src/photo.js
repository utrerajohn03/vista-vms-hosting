// Entry photo helpers: shrink a camera photo to a small JPEG so it uploads quickly on mobile data.
const toB64 = (blob) => new Promise((res, rej) => {
  const r = new FileReader();
  r.onload = () => res(String(r.result).split(',')[1] || '');
  r.onerror = () => rej(new Error('Could not read the photo'));
  r.readAsDataURL(blob);
});

// Returns base64 JPEG (no data: prefix), longest side at most `max` pixels.
export async function photoToJpegBase64(file, max = 1280, quality = 0.72) {
  if (!file || !/^image\//.test(file.type || '')) throw new Error('Choose a photo');
  try {
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, max / Math.max(bmp.width, bmp.height));
    const c = document.createElement('canvas');
    c.width = Math.max(1, Math.round(bmp.width * k)); c.height = Math.max(1, Math.round(bmp.height * k));
    c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
    bmp.close?.();
    const blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', quality));
    if (blob) return await toB64(blob);
  } catch { /* no canvas or unsupported format: fall through */ }
  if (file.type === 'image/jpeg' && file.size <= 1_400_000) return toB64(file);   // already a small JPEG: send as is
  throw new Error('Could not use that photo. Take it again');
}
