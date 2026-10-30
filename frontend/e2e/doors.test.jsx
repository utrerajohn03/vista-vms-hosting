// The two doors: the main site ("/") is for Admins, and each village has its own page at "/<village-link>".
// Runs against the real API in demo mode (no staff code).
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { SESS, parseVillageLink } from '../src/api.js';
import App from '../src/App.jsx';
import { CODE, goto, signInAs, SLUG, VILLAGE } from './helpers.jsx';

beforeAll(() => { window.scrollTo = () => {}; window.history.pushState(null, '', '/'); render(<App />); });
afterAll(cleanup);

describe('Village link parsing', () => {
  it('accepts a pasted link, a path or just the code', () => {
    for (const x of [SLUG, '/' + SLUG, `https://vms.example.ph/${SLUG}`, `https://vms.example.ph/${SLUG}/?invite=abc#x`, `  ${SLUG.toUpperCase()}  `])
      expect(parseVillageLink(x)).toBe(SLUG);
    expect(parseVillageLink('')).toBe('');
    expect(parseVillageLink('https://vms.example.ph/')).toBe('');
  });
});

describe('Main site door', () => {
  it('offers Admin sign-in only: no visitor form and no list of villages', async () => {
    await screen.findByRole('heading', { name: 'Admin sign-in' });
    expect(screen.queryByText(/I’m a visitor/)).toBeNull();
    expect(screen.queryByText(/Greenfield Village/)).toBeNull();
  });

  it('an unknown village link or a blank one does not sign in', async () => {
    fireEvent.click(screen.getByRole('button', { name: /Sign in as Admin/ }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/Enter your village link/);
    fireEvent.change(screen.getByLabelText(/^Village link/), { target: { value: 'no-such-village-0000' } });
    if (CODE) {   // a published server opens the email and password view first: an unknown village is refused there as well
      fireEvent.change(await screen.findByLabelText(/^Email/), { target: { value: 'admin@greenfield.ph' } });
      fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'whatever-password' } });
      fireEvent.click(screen.getByRole('button', { name: /Sign in as Admin/ }));
      await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/village link is not valid/));
      fireEvent.click(screen.getByRole('button', { name: /staff access code instead/ }));
    }
    fireEvent.click(await screen.findByRole('button', { name: /Sign in as Admin/ }));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/Could not sign in/));
    expect(SESS.role).toBe('');
  });

  it('an Admin signs in with the village link and sees that village by name', async () => {
    await signInAs('admin');
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    expect(screen.getAllByText('Greenfield Village').length).toBeGreaterThan(0);     // header brand comes from the server
    expect(screen.getByText('Today at Greenfield Village')).toBeTruthy();
    expect(SESS.prop).toBe(SLUG);
  });

  it('Settings shows this village’s real link, and signing out returns to the main site', async () => {
    fireEvent.click(screen.getAllByRole('button', { name: 'Settings' })[0]);
    const link = await screen.findByLabelText('Village link');
    await waitFor(() => expect(link.value).toBe(`${window.location.origin}/${SLUG}`));
    expect(link.readOnly).toBe(true);
    fireEvent.click(screen.getAllByRole('button', { name: 'Sign out' })[0]);
    await screen.findByRole('heading', { name: 'Admin sign-in' });
    expect(window.location.pathname).toBe('/');
    expect(SESS.prop).toBe('');
  });
});

describe('Village door', () => {
  it('shows the village’s name with visitor and staff doors, and no Admin option', async () => {
    goto(VILLAGE);
    await screen.findByText('Who are you here as?');
    expect(screen.getAllByText('Greenfield Village').length).toBeGreaterThan(0);
    expect(screen.getByText(/I’m a visitor/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /I’m staff/ }));
    await screen.findByText('Welcome back');
    // a server that signs people in as themselves shows the email and password first: there is no role to pick, so no Admin to pick
    const sw = await waitFor(() => { const b = screen.queryByRole('button', { name: /staff access code instead/ }); if (!b && !screen.queryByLabelText('Sign in as')) throw new Error('no form yet'); return b; });
    if (sw) { expect(screen.queryByLabelText('Sign in as')).toBeNull(); fireEvent.click(sw); }
    const opts = [...(await screen.findByLabelText('Sign in as')).querySelectorAll('option')].map((o) => o.textContent);
    expect(opts).toEqual(['Security guard', 'HOA office', 'Household account holder']);
  });

  it('a wrong village link shows one plain page and leaks nothing', async () => {
    goto('/not-a-real-village-0000');
    await screen.findByRole('heading', { name: 'This village link is not valid' });
    expect(screen.queryByText(/Greenfield/)).toBeNull();
    expect(screen.queryByText(/I’m a visitor/)).toBeNull();
    goto('/Bad_Link');
    await screen.findByRole('heading', { name: 'This village link is not valid' });
  });

  it('the village link is matched in capitals too, and staff sign out stays on the village page', async () => {
    goto('/' + SLUG.toUpperCase());
    await screen.findByText('Who are you here as?');
    await signInAs('guard');
    fireEvent.click(screen.getAllByRole('button', { name: 'Sign out' })[0]);
    await screen.findByText('Who are you here as?');
    expect(window.location.pathname.toLowerCase()).toBe(VILLAGE);
  });
});
