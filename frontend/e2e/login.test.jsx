// Personal sign-in: email + password, each person gets only the role their account was given.
// Needs a published-mode API whose seeded accounts have a password:
//   AUTO_SEED=1 SEED_PASSWORD=<10+ characters> STAFF_ACCESS_CODE=<code> SECRET_KEY=<key> uvicorn app.main:app
// then:  SEED_PASSWORD=<same> STAFF_ACCESS_CODE=<code> npm test
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { SESS } from '../src/api.js';
import App from '../src/App.jsx';
import { goto, VILLAGE, SLUG } from './helpers.jsx';

const PW = process.env.SEED_PASSWORD || '';
const click = (name, i = 0) => fireEvent.click(screen.getAllByRole('button', { name })[i]);
const type = (label, v) => fireEvent.change(screen.getByLabelText(label), { target: { value: v } });
const heading = (name) => screen.findByRole('heading', { level: 1, name });

async function openStaffDoor() {
  goto(VILLAGE);
  if (!screen.queryByText('Welcome back')) fireEvent.click(await screen.findByRole('button', { name: /I’m staff/ }));
  await screen.findByText('Welcome back');
  await screen.findByLabelText(/^Email/);   // the email-and-password view is the first one a published server shows
}
const signOut = async () => { click('Sign out'); await waitFor(() => expect(SESS.role).toBe('')); };

beforeAll(() => { window.scrollTo = () => {}; window.history.pushState(null, '', VILLAGE); render(<App />); });
afterAll(cleanup);

describe.skipIf(!PW)('Email and password sign-in', () => {
  it('shows an email and a password field and no role to pick', async () => {
    await openStaffDoor();
    expect(screen.getByLabelText(/^Password/)).toBeTruthy();
    expect(screen.queryByLabelText('Sign in as')).toBeNull();
    expect(screen.queryByLabelText(/Staff access code/)).toBeNull();
  });

  it('asks for what is missing before calling the server', async () => {
    click('Sign in');
    expect(await screen.findByText('Enter your email address.')).toBeTruthy();
    type(/^Email/, 'not-an-email'); click('Sign in');
    expect(await screen.findByText('Enter a valid email address.')).toBeTruthy();
    type(/^Email/, 'ramon@greenfield.ph'); click('Sign in');
    expect(await screen.findByText('Enter your password.')).toBeTruthy();
    expect(SESS.role).toBe('');
  });

  it('a wrong password is refused with one plain message and the password is cleared', async () => {
    type(/^Password/, 'not-the-password'); click('Sign in');
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Wrong email or password'));
    expect(screen.getByLabelText(/^Password/).value).toBe('');
    expect(SESS.role).toBe('');
  });

  it('a guard signs in as themselves and gets only the guard’s screens', async () => {
    type(/^Password/, PW); click('Sign in');
    await heading('Gate');
    expect(SESS.role).toBe('guard'); expect(SESS.name).toBe('Ramon Dela Cruz'); expect(SESS.token).toBeTruthy();
    expect(screen.getAllByText('Security guard').length).toBeGreaterThan(0);
    const nav = screen.getByRole('navigation', { name: 'Main' });
    for (const x of ['Gate', 'Walk-in', 'Exit']) expect(within(nav).getByRole('button', { name: new RegExp(x) })).toBeTruthy();
    for (const x of ['Households', 'Settings', 'Verify households']) expect(within(nav).queryByRole('button', { name: new RegExp(x) })).toBeNull();
    expect(screen.getByRole('button', { name: 'Change password' })).toBeTruthy();
    await signOut();
  });

  it('an HOA office account signs in as the HOA office, never as a guard', async () => {
    await screen.findByText('Who are you here as?');
    await openStaffDoor();
    type(/^Email/, 'LORNA@greenfield.ph'); type(/^Password/, PW); click('Sign in');   // the email is not case sensitive
    await heading('Verify households');
    expect(SESS.role).toBe('hoa'); expect(SESS.name).toBe('Lorna Aquino');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    expect(within(nav).queryByRole('button', { name: /Walk-in/ })).toBeNull();
    await signOut();
  });

  it('the Change password dialog checks the two new passwords match', async () => {
    await screen.findByText('Who are you here as?');
    await openStaffDoor();
    type(/^Email/, 'lorna@greenfield.ph'); type(/^Password/, PW); click('Sign in');
    await heading('Verify households');
    click('Change password');
    const dlg = await screen.findByRole('dialog', { name: 'Change password' });
    fireEvent.change(within(dlg).getByLabelText(/^New password/), { target: { value: 'a-new-long-password' } });
    fireEvent.change(within(dlg).getByLabelText(/^Repeat/), { target: { value: 'a-different-one-here' } });
    fireEvent.click(within(dlg).getByRole('button', { name: 'Change password' }));
    await screen.findByText('The two new passwords do not match');
    fireEvent.click(within(dlg).getAllByRole('button', { name: /Cancel|Close/ })[0]);
    await signOut();
  });

  it('the Admin signs in at the main site with the village link, email and password', async () => {
    goto('/');
    fireEvent.change(await screen.findByLabelText(/^Village link/), { target: { value: SLUG } });
    type(/^Email/, 'admin@greenfield.ph'); type(/^Password/, 'wrong-password-here');
    click('Sign in as Admin');
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Wrong email or password'));
    expect(SESS.role).toBe('');
    type(/^Password/, PW); click('Sign in as Admin');
    await heading('Dashboard');
    expect(SESS.role).toBe('admin');
  });

  it('an account the Admin creates with a password can sign in, and gets the role the Admin chose', async () => {
    click('Guards and HOA office');
    await heading('Guards and HOA office');
    click('Add account');
    const dlg = await screen.findByRole('dialog');
    fireEvent.change(within(dlg).getByLabelText(/^Full name/), { target: { value: 'Nico Newhire' } });
    fireEvent.change(within(dlg).getByLabelText(/^Email/), { target: { value: 'nico@greenfield.ph' } });
    fireEvent.change(within(dlg).getByLabelText(/^Role/), { target: { value: 'Guard' } });
    fireEvent.change(within(dlg).getByLabelText(/^First password/), { target: { value: ' spaced password 1 ' } });   // used exactly as typed
    fireEvent.click(within(dlg).getByRole('button', { name: 'Save' }));
    await screen.findAllByText('Nico Newhire');
    await signOut();
    await screen.findByRole('heading', { name: 'Admin sign-in' });
    goto(VILLAGE);
    await openStaffDoor();
    type(/^Email/, 'nico@greenfield.ph'); type(/^Password/, 'spaced password 1'); click('Sign in');   // without the spaces: refused
    await waitFor(() => expect(screen.getByRole('alert').textContent).toBe('Wrong email or password'));
    type(/^Password/, ' spaced password 1 '); click('Sign in');
    await heading('Gate');
    expect(SESS.role).toBe('guard'); expect(SESS.name).toBe('Nico Newhire');
    await signOut();
  });
});
