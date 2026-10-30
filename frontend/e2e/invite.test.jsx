// Published mode only (needs STAFF_ACCESS_CODE): Admin invites a household, the household opens its link and fills the form,
// the HOA office verifies it. Run: STAFF_ACCESS_CODE=... npm test   (API started with STAFF_ACCESS_CODE, SECRET_KEY, FRONTEND_URL)
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterAll, describe, expect, it } from 'vitest';
import App from '../src/App.jsx';
import { signInAs, VILLAGE } from './helpers.jsx';

const CODE = process.env.STAFF_ACCESS_CODE || '';
const btn = (name, i = 0) => screen.getAllByRole('button', { name })[i];
const click = (name, i = 0) => fireEvent.click(btn(name, i));
const type = (label, v) => fireEvent.change(screen.getByLabelText(label), { target: { value: v } });

const staffSignIn = signInAs;

afterAll(cleanup);

describe.skipIf(!CODE)('Household invitation link (published mode)', () => {
  let link = '';

  it('Admin invites a household and gets the sign-in link', async () => {
    window.scrollTo = () => {};
    window.history.pushState(null, '', '/');
    render(<App />);
    await screen.findByRole('heading', { name: 'Admin sign-in' });   // the Admin's door is the main site
    await staffSignIn('admin');
    click('Households');
    await screen.findByRole('heading', { level: 1, name: 'Households' });
    click('Invite household');
    type(/^Account holder email/, 'ui-invite@example.com');
    click('Save');
    const box = await screen.findByDisplayValue(/\?invite=/);
    link = box.value;
    expect(link).toMatch(/^https?:\/\/[^/]+\/greenfield-village-7f3a\?invite=.+/);   // the household lands on its village's own page
  });

  it('the household opens the link, fills the form, and the token leaves the address bar', async () => {
    cleanup();
    const u = new URL(link);
    window.history.pushState({}, '', u.pathname + u.search);
    render(<App />);
    await screen.findByRole('heading', { level: 1, name: 'Household form' }, { timeout: 5000 });
    expect(window.location.search).toBe('');
    expect(window.location.pathname).toBe(VILLAGE);
    type(/^Owner name/, 'Rivera'); type(/^Block and lot/, 'B8-L8'); type(/^Account holder/, 'Rosa Rivera'); type(/^Phone/, '0917 555 0123');
    fireEvent.change(screen.getByLabelText(/^People living here/), { target: { value: 'Rosa Rivera\nMico (minor)' } });
    click('Save household');
    await screen.findByText('Household saved');
  });

  it('the HOA office verifies it, and the household can now approve visits', async () => {
    await staffSignIn('hoa');
    await screen.findByRole('heading', { level: 1, name: 'Verify households' });
    await waitFor(() => expect(screen.getAllByText('B8-L8').length).toBeGreaterThan(0));
    const row = screen.getAllByText('B8-L8').map((e) => e.closest('tr')).find(Boolean);
    fireEvent.click(within(row).getByRole('button', { name: 'Verify' }));
    await screen.findByRole('dialog', { name: /Verify household B8-L8/ });   // the HOA reviews the details first
    await screen.findByText('Rosa Rivera', { selector: 'li span' });
    click('Verify household');
    await screen.findByText(/Household B8-L8 verified/);
  });
});
