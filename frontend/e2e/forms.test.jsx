// Household form, HOA review, gate check and exit, against the real API in demo mode (no staff code).
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { api, SESS } from '../src/api.js';
import App from '../src/App.jsx';
import { CODE, signInAs, VILLAGE, visitBody } from './helpers.jsx';

const click = (name, i = 0) => fireEvent.click(screen.getAllByRole('button', { name })[i]);
const JPEG = new File([Uint8Array.from(atob('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA='), (c) => c.charCodeAt(0))], 'car.jpg', { type: 'image/jpeg' });
const as = (role, lot = '') => Object.assign(SESS, { role, lot, name: 'Tester', token: '' });

async function signIn(role, heading, lot) {
  await signInAs(role, lot);
  await screen.findByRole('heading', { level: 1, name: heading });
}

beforeAll(() => { window.scrollTo = () => {}; window.history.pushState(null, '', VILLAGE); as(''); render(<App />); });
afterAll(cleanup);

describe('Household form', () => {
  it('shows a plain message for a bad form and saves a good one', async () => {
    await signIn('household', 'Visit requests', 'B3-L5');
    click('Household form'); await screen.findByRole('heading', { level: 1, name: 'Household form' });
    expect(screen.getByLabelText(/^Owner name/).value).toBe('Garcia');
    fireEvent.change(screen.getByLabelText(/^Block and lot/), { target: { value: '###' } });
    click('Save household');
    expect((await screen.findByRole('alert')).textContent).toMatch(/house number/);
    fireEvent.change(screen.getByLabelText(/^Block and lot/), { target: { value: 'b3 - l5' } });
    fireEvent.change(screen.getByLabelText(/^Account holder/), { target: { value: 'Somebody Else' } });
    click('Save household');
    expect((await screen.findByRole('alert')).textContent).toMatch(/one of the people listed/);
    fireEvent.change(screen.getByLabelText(/^Account holder/), { target: { value: 'Pia Garcia' } });
    fireEvent.change(screen.getByLabelText(/^Email/), { target: { value: 'pia@mail.ph' } });
    click('Save household');
    await screen.findByText('Household saved');
    expect(screen.getByLabelText(/^Block and lot/).value).toBe('B3-L5');   // loose input normalised
  });

  it('a verified household that moves lot is told it needs the HOA again', async () => {
    await signIn('household', 'Visit requests', 'B2-L7');
    click('Household form'); await screen.findByRole('heading', { level: 1, name: 'Household form' });
    expect(screen.getByText(/Verified by the HOA office/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/^Block and lot/), { target: { value: 'B2-L9' } });
    click('Save household');
    await screen.findByText(/must verify this household again/);
    await waitFor(() => expect(screen.getByText(/cannot approve visits/)).toBeTruthy());
  });
});

describe('HOA verification', () => {
  it('the HOA sees the people before verifying', async () => {
    await signIn('hoa', 'Verify households');
    const row = await waitFor(() => { const r = screen.getAllByText('B2-L9').map((e) => e.closest('tr')).find(Boolean); expect(r).toBeTruthy(); return r; });
    fireEvent.click(within(row).getByRole('button', { name: 'Verify' }));
    const dlg = await screen.findByRole('dialog', { name: /Verify household B2-L9/ });
    expect(within(dlg).getByText('Jun Santos')).toBeTruthy();
    expect(within(dlg).getByText(/account holder is listed as an adult/)).toBeTruthy();
    click('Verify household');
    await screen.findByText(/Household B2-L9 verified/);
  });
});

// Demo mode only: the setup calls the API with the demo role headers, which a server that checks sign-ins ignores.
describe.skipIf(!!CODE)('Guard gate and exit', () => {
  let ref;
  it('a car needs a real photo, and a visitor with a car can leave by pass number', async () => {
    as('');
    await api('/visits', { body: visitBody({ name: 'Forms Car', phone: '0900 777 0001', host: 'Maria Reyes', arrival: 'Own vehicle', plate: 'ABC 123', color: 'White', kind: 'Sedan' }) });
    as('admin'); ref = (await api('/state')).visits.find((v) => v.visitor.startsWith('Forms Car')).ref;
    as('household', 'B1-L4'); await api(`/visits/${ref}/decision`, { body: { approve: true } });
    await signIn('guard', 'Gate');
    fireEvent.click(within(rowOfText('Forms Car')).getByRole('button', { name: 'Check in' }));
    fireEvent.click(await screen.findByLabelText('ID checked against the visitor'));
    expect(screen.getByRole('button', { name: 'Issue passes' }).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText('Entry photo'), { target: { files: [JPEG] } });
    for (const l of ['Plate matches', 'Color matches', 'Type matches']) fireEvent.click(await screen.findByLabelText(l));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Issue passes' }).disabled).toBe(false));
    click('Issue passes');
    await screen.findByText(/Passes issued/);
  });

  it('exit: scan the pass number, tick vehicle left, mark left', async () => {
    await signIn('guard', 'Gate');
    click('Exit'); // sidebar
    await screen.findByRole('heading', { level: 1, name: 'Exit' });
    fireEvent.click(within(rowOfText('Forms Car')).getByRole('button', { name: 'Scan out' }));
    const dlg = await screen.findByRole('dialog', { name: /Exit: Forms Car/ });
    await within(dlg).findByAltText(/Entry photo/, {}, { timeout: 4000 }).catch(() => {});   // photo loads when the browser can make object URLs
    fireEvent.change(within(dlg).getByLabelText('Pass number'), { target: { value: 'nope' } });
    fireEvent.click(within(dlg).getAllByRole('button', { name: 'Scan out' })[0]);
    await screen.findByText(/not on this visit/);
    const code = within(dlg).getByText(/^P\d+/).textContent.trim();
    fireEvent.change(within(dlg).getByLabelText('Pass number'), { target: { value: code.toLowerCase() } });
    fireEvent.click(within(dlg).getAllByRole('button', { name: 'Scan out' })[0]);
    await screen.findByText(/scanned out/);
    fireEvent.click(within(dlg).getByLabelText('Vehicle left'));
    fireEvent.click(within(dlg).getByRole('button', { name: 'Mark left' }));
    await screen.findByText(/Marked Left/);
  });
});

function rowOfText(text) { return screen.getAllByText(new RegExp(text)).map((e) => e.closest('tr')).find(Boolean); }
