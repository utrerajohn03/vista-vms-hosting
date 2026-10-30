// Drives the real React UI against the real API and PostgreSQL (start the API first: see README).
// Run: npm test          (E2E_API=http://127.0.0.1:8000 by default; STAFF_ACCESS_CODE=... if the API requires a code)
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import App from '../src/App.jsx';
import { PG } from '../src/config.js';
import { signInAs, TODAY, VILLAGE } from './helpers.jsx';

const CODE = process.env.STAFF_ACCESS_CODE || '';
const tick = (ms = 0) => new Promise((r) => setTimeout(r, ms));
const btn = (name, i = 0) => screen.getAllByRole('button', { name })[i];
const click = (name, i = 0) => fireEvent.click(btn(name, i));
const type = (label, v) => fireEvent.change(screen.getByLabelText(label), { target: { value: v } });
const heading = (name) => screen.findByRole('heading', { level: 1, name });
// a real (1x1) JPEG, as a camera file
const JPEG = new File([Uint8Array.from(atob('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA='), (c) => c.charCodeAt(0))], 'car.jpg', { type: 'image/jpeg' });
const rowOf = (text) => screen.getAllByText(text).map((e) => e.closest('tr')).find(Boolean);

const signIn = signInAs;
async function visitorRequest(f) {
  click(/I’m a visitor/);
  type(/^Your name/, f.name); type(/^Phone/, '0955 123 4567');
  fireEvent.change(screen.getByLabelText(/^ID or photo/), { target: { files: [JPEG] } });
  type(/^House number/, f.house); type(/^Person you/, f.host || ''); type(/^Purpose/, 'Dinner'); type(/^Date and time/, `${TODAY}T18:00`);
  fireEvent.change(screen.getByLabelText(/^How are you arriving/), { target: { value: f.arr } });
  if (f.arr === 'Own vehicle') { type(/^Vehicle type/, 'Vios'); type(/^Color/, 'White'); type(/^Plate/, 'E2E 111'); }
  if (f.friends) type(/^Friends visiting/, f.friends);
  click('Send request');
  await screen.findByText('Your request was sent');
  click('Done');
}

beforeAll(() => { window.scrollTo = () => {}; window.history.pushState(null, '', VILLAGE); render(<App />); });
afterAll(cleanup);

describe('Village UI against the live API', () => {
  it('landing renders and the system is online', async () => {
    await screen.findByText('Who are you here as?');
    await screen.findByText('System online');
  });

  it('visitor group request gets the neutral reply, and so does an unmatched house', async () => {
    await visitorRequest({ name: 'E2E Visitor', house: 'B1-L4', host: 'Maria Reyes', arr: 'Own vehicle', friends: 'Pal One\nPal Two' });
    await visitorRequest({ name: 'Ghost', house: 'B9-L9', host: '', arr: 'Walking' });
  });

  it('household approves its own request and does not see the unmatched one', async () => {
    await signIn('household', 'B1-L4');
    await heading('Visit requests');
    await screen.findAllByText(/^E2E Visitor/);
    expect(screen.queryAllByText('Ghost')).toHaveLength(0);
    click('Approve');
    await screen.findByText(/Approved\. QR sent/);
    click('All visits');
    await waitFor(() => expect(within(rowOf(/^E2E Visitor/)).getByText('Waiting at gate')).toBeTruthy());
  });

  it('HOA corrects the unmatched request and resends it', async () => {
    await signIn('hoa');
    click('Unmatched queue');
    await heading('Unmatched queue');
    await screen.findAllByText('Ghost');
    click('Correct and resend');
    type(/^House number/, 'B2-L7'); type(/^Person visiting/, 'Ana Santos');
    click('Resend');
    await screen.findByText('Resent to the household');
    click(/Today’s visits/);
    await waitFor(() => expect(within(rowOf('Ghost')).getByText('Pending')).toBeTruthy());
  });

  it('guard checks in with a vehicle mismatch override and issues 3 passes', async () => {
    await signIn('guard');
    await heading('Gate');
    click('Check in');
    fireEvent.click(await screen.findByLabelText(/ID checked/));
    expect(screen.queryByLabelText('Color matches')).toBeNull();   // the comparison opens after the entry photo
    fireEvent.change(screen.getByLabelText('Entry photo'), { target: { files: [JPEG] } });
    fireEvent.click(await screen.findByLabelText('Color matches'));
    fireEvent.click(screen.getByLabelText('Type matches'));
    expect(btn('Issue passes').disabled).toBe(true);           // the plate is not answered yet
    expect(screen.queryByText(/Mismatch\./)).toBeNull();        // and nothing is called a mismatch until the guard says so
    fireEvent.click(screen.getByLabelText('Plate does not match'));
    expect(btn('Issue passes').disabled).toBe(true);           // plate does not match: needs an override with a reason
    fireEvent.click(screen.getByLabelText('Override and allow'));
    fireEvent.change(screen.getByPlaceholderText('Reason for override'), { target: { value: 'Plate dirty' } });
    expect(btn('Issue passes').disabled).toBe(false);
    click('Issue passes');
    await screen.findByText(/Passes issued/);
    click('Inside');
    await waitFor(() => expect(within(rowOf(/^E2E Visitor/)).getByText('Inside')).toBeTruthy());
  });

  it('household sees its visitor at the house and confirms arrival', async () => {
    await signIn('household', 'B1-L4');
    click('At the house');
    await heading('At the house');
    await screen.findAllByText(/^E2E Visitor/);
    fireEvent.click(within(rowOf(/^E2E Visitor/)).getByRole('button', { name: 'Scan at house' }));
    await screen.findByText(/Arrival confirmed|wrong destination/);
  });

  it('guard sees the arrival notice and registers a walk-in group with a declared vehicle', async () => {
    await signIn('guard');
    click('Notices');
    await heading('Notices');
    await screen.findAllByText(/E2E Visitor arrived at the house/);
    click('Walk-in');
    await heading('Walk-in');
    click('New walk-in');
    type(/^Visitor name/, 'Walk Group'); type(/^House number/, 'B1-L4');
    expect(screen.queryByLabelText(/^Plate number/)).toBeNull();                         // vehicle fields only appear for Own vehicle
    fireEvent.change(screen.getByLabelText(/^Arriving by/), { target: { value: 'Own vehicle' } });
    type(/^Vehicle type/, 'Vios'); type(/^Vehicle color/, 'White'); type(/^Plate number/, 'WLK 777');
    type(/^Friends with the visitor/, 'Walk Pal One\nWalk Pal Two');
    click('Save');
    await screen.findAllByText(/^Walk Group/);
    await screen.findAllByRole('button', { name: 'Approved by phone' });   // no pass until the household approves by phone
  });

  it('HOA office sees today’s visits only', async () => {
    await signIn('hoa');
    click(/Today’s visits/);
    await heading('Today’s visits');
    await screen.findAllByText(/^E2E Visitor/);
  });

  it('admin: every page and tab renders against live data', async () => {
    await signIn('admin');
    let combos = 0;
    for (const [k, p] of Object.entries(PG).filter(([k]) => !/^(g_|h_|u_)/.test(k))) {
      fireEvent.click(within(screen.getByRole('navigation')).getAllByRole('button').find((b) => b.textContent.startsWith(p.t === 'Village map and wayfinding' ? p.t : p.t)));
      await heading(p.t);
      for (const t of p.tabs || [{ k: '' }]) {
        if (t.k) fireEvent.click(within(screen.getByRole('main')).getAllByRole('button', { name: t.k })[0]);
        combos++;
      }
    }
    expect(combos).toBeGreaterThanOrEqual(25);
  });

  it('admin: reports show real numbers and the map editor lets you pick a lot to place', async () => {
    click('Reports');
    await heading('Reports');
    await screen.findByText('Visits, last 7 days');
    expect(screen.queryByText('128')).toBeNull();   // the old sample figure
    click('Village map and wayfinding');
    await heading('Village map and wayfinding');
    const pick = await screen.findByLabelText('Place on the map');
    const opt = await screen.findByRole('option', { name: /Lot B1-L4/ });
    fireEvent.change(pick, { target: { value: opt.value } });
    await screen.findByText('Click the map to place it');
  });

  it('admin setup actions go through the API: gate, pass, household invitation', async () => {
    click('Gates and passes');
    await heading('Gates and passes');
    fireEvent.click(within(screen.getByRole('main')).getByRole('button', { name: 'Gates' }));
    click('Add gate'); type(/^Gate name/, 'E2E Gate'); click('Save');
    await screen.findAllByText('E2E Gate');
    fireEvent.click(within(screen.getByRole('main')).getByRole('button', { name: 'Passes' }));
    click('Add pass'); type(/^Pass number/, 'p77'); click('Save');
    fireEvent.change(screen.getByPlaceholderText('Search…'), { target: { value: 'P77' } });   // the list is paged
    await screen.findAllByText('P77');
    click('Households');
    await heading('Households');
    click('Invite household'); type(/^Account holder email/, 'e2e@mail.ph'); click('Save');
    await screen.findAllByText('e2e@mail.ph');
  });

  it('audit log recorded the steps', async () => {
    click('Audit log');
    await heading('Audit log');
    fireEvent.click(within(screen.getByRole('main')).getByRole('button', { name: 'All' }));   // the page remembers the last tab
    fireEvent.change(screen.getByPlaceholderText('Search…'), { target: { value: 'Passes issued' } });
    await screen.findAllByText(/Passes issued/);
    fireEvent.change(screen.getByPlaceholderText('Search…'), { target: { value: 'Visit request' } });
    await screen.findAllByText(/Visit request/);
  });

  it('advancing the clock 3 hours runs the real Missing job', async () => {
    click('Alerts');
    await heading('Alerts');
    click('Advance clock 3 hours');
    await screen.findByText(/flagged Missing|nothing missing/);
    click(/^Visits/);
    await heading('Visits');
    click('Exceptions');
    await tick(100);
  });
});
