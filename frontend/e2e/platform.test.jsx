// Published mode with a Super Admin code. Run: STAFF_ACCESS_CODE=... SUPER_ADMIN_CODE=... npm test
// (API started with STAFF_ACCESS_CODE, SECRET_KEY, SUPER_ADMIN_CODE, FRONTEND_URL)
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterAll, describe, expect, it } from 'vitest';
import App from '../src/App.jsx';
import { goto } from './helpers.jsx';

const SUPER = process.env.SUPER_ADMIN_CODE || '';
const click = (name, i = 0) => fireEvent.click(screen.getAllByRole('button', { name })[i]);
const type = (label, v) => fireEvent.change(screen.getByLabelText(label), { target: { value: v } });

afterAll(cleanup);

describe.skipIf(!SUPER)('Super Admin (platform level)', () => {
  it('signs in at the main site, creates a property and opens it as the Admin, then goes back', async () => {
    window.scrollTo = () => {};
    window.history.pushState(null, '', '/');
    render(<App />);
    fireEvent.click(await screen.findByRole('button', { name: /Super Admin sign-in/ }));
    await screen.findByRole('heading', { name: 'Super Admin sign-in' });
    type(/^Your name/, 'UI Super'); type(/^Super Admin code/, 'wrong');
    click('Sign in as Super Admin');
    await screen.findByRole('alert');                                   // a wrong code is refused
    type(/^Super Admin code/, SUPER);
    click('Sign in as Super Admin');
    await screen.findByRole('heading', { level: 1, name: 'Properties' });
    expect(screen.getByText(/Platform · Super Admin/)).toBeTruthy();

    click('New property');
    type(/^Village name/, 'UI Test Village'); type(/^Admin name/, 'Uma Admin'); type(/^Admin email/, 'uma@ui-test.ph');
    click('Create property');
    const links = await screen.findAllByDisplayValue(/^https?:\/\//);
    expect(links.some((l) => /\/\?admin=/.test(l.value))).toBe(true);     // the Admin's personal link
    expect(links.some((l) => /\/ui-test-village-[0-9a-f]{4}$/.test(l.value))).toBe(true);   // the village link
    click('Close');

    const row = (await screen.findAllByText('UI Test Village')).map((e) => e.closest('tr')).find(Boolean);
    expect(within(row).getByText('Uma Admin')).toBeTruthy();
    fireEvent.click(within(row).getByRole('button', { name: 'Open' }));
    await screen.findByText(/you are working inside/);                  // the Super Admin banner inside the village
    await screen.findByRole('heading', { level: 1, name: 'Dashboard' });
    click('Back to platform');
    await screen.findByRole('heading', { level: 1, name: 'Properties' });
    fireEvent.click(screen.getByRole('button', { name: 'Platform audit' }));
    await screen.findAllByText(/Signed in to the property/);
    click('Sign out');
    goto('/');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Admin sign-in' })).toBeTruthy());
  });
});
