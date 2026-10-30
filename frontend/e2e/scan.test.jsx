// Gate QR scan against the real API: the guard types or scans the visitor's QR text and lands on the right dialog.
// jsdom has no camera, so this drives the typed-code path (the camera path feeds the same handler).
// Needs the API in demo mode (no STAFF_ACCESS_CODE), like the backend tests.
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { api, SESS } from '../src/api.js';
import App from '../src/App.jsx';
import { passPayload } from '../src/qrcore.js';
import { CODE, signInAs, VILLAGE, visitBody } from './helpers.jsx';

const click = (name, i = 0) => fireEvent.click(screen.getAllByRole('button', { name })[i]);
let tok, ref;

beforeAll(async () => {
  window.scrollTo = () => {};
  window.history.pushState(null, '', VILLAGE);
  await api('/visits', { body: visitBody({ name: 'Scan UI', phone: '0900 555 0101', host: 'Maria Reyes' }) });
  Object.assign(SESS, { role: 'admin', lot: '', name: 'Tester', token: '' });
  const v = (await api('/state')).visits.find((x) => x.visitor.startsWith('Scan UI'));
  ({ tok, ref } = v);
  Object.assign(SESS, { role: 'household', lot: 'B1-L4' });
  await api(`/visits/${ref}/decision`, { body: { approve: true } });
  Object.assign(SESS, { role: '', lot: '', name: '' });
  render(<App />);
});
afterAll(cleanup);

async function signInGuard() {
  await signInAs('guard');
  await screen.findByRole('heading', { level: 1, name: 'Gate' });
}

// Demo mode only: the setup calls the API with the demo role headers, which a server that checks sign-ins ignores.
describe.skipIf(!!CODE)('Gate QR scan', () => {
  it('QR text opens the gate check for an approved visit', async () => {
    await signInGuard();
    click('Scan QR');
    fireEvent.change(await screen.findByLabelText(/Or type the code/), { target: { value: passPayload(tok) } });
    click('Find visit');
    await screen.findByRole('dialog', { name: /Gate check: Scan UI/ });
  });

  it('an unknown code shows a clear message and keeps the scanner open', async () => {
    click('Cancel');
    click('Scan QR');
    fireEvent.change(await screen.findByLabelText(/Or type the code/), { target: { value: 'VISTA:not-a-real-code' } });
    click('Find visit');
    await screen.findByText(/No visit matches/);
    expect(screen.getByRole('dialog', { name: /Scan visitor QR/ })).toBeTruthy();
  });

  it('a visit already inside is not checked in twice', async () => {
    click('Close');
    click('Check in');
    fireEvent.click(await screen.findByLabelText(/ID checked/));
    click('Issue passes');
    await screen.findByText(/Passes issued/);
    click('Scan QR');
    fireEvent.change(await screen.findByLabelText(/Or type the code/), { target: { value: tok } });
    click('Find visit');
    await waitFor(() => expect(within(screen.getByRole('dialog')).getByRole('status').textContent).toMatch(/already inside/));
  });
});
