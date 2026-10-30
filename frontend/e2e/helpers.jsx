// Shared by the UI tests: sign in through the real doors. Admins use the main site ("/"); everyone else uses the village's own page.
import { act, fireEvent, screen, waitFor } from '@testing-library/react';

export const SLUG = 'greenfield-village-7f3a';
export const VILLAGE = '/' + SLUG;
// Today's date (yyyy-mm-dd), so the visits the tests create are always "today" for the HOA's Today's visits page.
// "Today" is the village's today (the API's TIMEZONE, Asia/Manila by default), not the computer's: between 16:00 and 24:00 UTC they are different days.
export const TODAY = new Date().toLocaleDateString('en-CA', { timeZone: process.env.E2E_TZ || 'Asia/Manila' });
export const CODE = process.env.STAFF_ACCESS_CODE || '';
// A complete public visitor request, the way the form sends it: ID photo (a real 1x1 JPEG), purpose and date and time are all required.
export const JPEG_B64 = '/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=';
export const visitBody = (over) => ({ phone: '0900 555 0100', house: 'B1-L4', purpose: 'Visit', when: `${TODAY}T18:00`, arrival: 'Walking', id_photo: JPEG_B64, ...over });
const click = (name, i = 0) => fireEvent.click(screen.getAllByRole('button', { name })[i]);

// Move to another address the way the browser does (back button or a pasted link): the app re-reads the village from the path.
export function goto(path) {
  act(() => { window.history.pushState(null, '', path); window.dispatchEvent(new PopStateEvent('popstate')); });
}

// A server that can sign people in as themselves opens the "email and password" view first. These helpers sign in with the shared
// staff code (the way the older tests do), so switch to that view when the screen offers the switch.
async function useSharedCode() {
  if (!CODE) return;
  await waitFor(() => { if (!screen.queryByLabelText(/Staff access code/) && !screen.queryByRole('button', { name: /staff access code instead/ })) throw new Error('no sign-in form yet'); });
  const sw = screen.queryByRole('button', { name: /staff access code instead/ });
  if (sw) fireEvent.click(sw);
}

export async function signInAs(role, lot) {
  if (screen.queryByRole('button', { name: 'Sign out' })) click('Sign out');
  if (role === 'admin') {
    goto('/');
    fireEvent.change(await screen.findByLabelText(/^Village link/), { target: { value: SLUG } });
    await useSharedCode();
    if (CODE) fireEvent.change(await screen.findByLabelText(/Staff access code/), { target: { value: CODE } });
    click('Sign in as Admin');
  } else {
    goto(VILLAGE);
    if (!screen.queryByText('Welcome back')) fireEvent.click(await screen.findByRole('button', { name: /I’m staff/ }));
    await useSharedCode();
    if (CODE) fireEvent.change(await screen.findByLabelText(/Staff access code/), { target: { value: CODE } });
    fireEvent.change(await screen.findByLabelText('Sign in as'), { target: { value: role } });
    if (role === 'household') fireEvent.change(await screen.findByLabelText('Household'), { target: { value: lot } });
    click('Sign in');
  }
  try { await screen.findByRole('button', { name: 'Sign out' }, { timeout: 5000 }); }
  catch (e) { throw new Error('sign-in as ' + role + ' failed: ' + (screen.queryByRole('alert')?.textContent || 'no message')); }
}
