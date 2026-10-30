// Visitor registration form: validation beside each field, the ID/photo reaching the API, one request for a group,
// optional vehicle fields, and no double submit. Runs against the real API (demo mode), like the other UI tests.
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import App from '../src/App.jsx';
import { goto, TODAY, VILLAGE } from './helpers.jsx';

const JPEG = new File([Uint8Array.from(atob('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA='), (c) => c.charCodeAt(0))], 'id.jpg', { type: 'image/jpeg' });
const type = (label, v) => fireEvent.change(screen.getByLabelText(label), { target: { value: v } });
const send = () => fireEvent.click(screen.getByRole('button', { name: /Send request|Sending/ }));
const posts = [];
const realFetch = globalThis.fetch;

function fillRequired(extra = {}) {
  type(/^Your name/, extra.name || 'Form Tester'); type(/^Phone/, '0955 777 0001');
  fireEvent.change(screen.getByLabelText(/^ID or photo/), { target: { files: [JPEG] } });
  type(/^House number/, 'B1-L4'); type(/^Purpose/, 'Dinner'); type(/^Date and time/, `${TODAY}T18:00`);
}

beforeAll(() => {
  window.scrollTo = () => {};
  window.history.pushState(null, '', '/');
  vi.spyOn(globalThis, 'fetch').mockImplementation((url, init) => {
    if (String(url).endsWith('/api/visits') && init?.method === 'POST') posts.push(JSON.parse(init.body));
    return realFetch(url, init);
  });
  render(<App />);
});
afterEach(() => { posts.length = 0; });
afterAll(() => { vi.restoreAllMocks(); cleanup(); });

async function openForm() {
  goto(VILLAGE);
  fireEvent.click(await screen.findByRole('button', { name: /I’m a visitor/ }));
  await screen.findByRole('heading', { name: 'Register your visit' });
}

describe('Visitor registration form', () => {
  it('shows an error beside every missing required field and sends nothing', async () => {
    await openForm();
    send();
    for (const re of [/Enter your name/, /Enter your phone number/, /Add your ID or a photo/, /Enter the house number/, /purpose of your visit/, /date and time of your visit/])
      expect(await screen.findByText(re)).toBeTruthy();
    expect(screen.getByLabelText(/^Your name/).getAttribute('aria-invalid')).toBe('true');
    expect(screen.getByLabelText(/^ID or photo/).getAttribute('aria-describedby')).toBe('e_i');
    expect(posts.length).toBe(0);
    // the person to visit is not required: blank means any household member
    expect(screen.queryByText(/Person you.re visiting.*\*/)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  });

  it('vehicle fields appear only for Own vehicle and are optional', async () => {
    await openForm();
    expect(screen.queryByLabelText(/^Vehicle type/)).toBeNull();
    fireEvent.change(screen.getByLabelText(/^How are you arriving/), { target: { value: 'Own vehicle' } });
    for (const re of [/^Vehicle type \(optional\)/, /^Color \(optional\)/, /^Plate number \(optional\)/]) expect(screen.getByLabelText(re)).toBeTruthy();
    fillRequired({ name: 'Car No Details' });
    send();
    await screen.findByText('Your request was sent');
    expect(posts.length).toBe(1);
    expect(posts[0]).toMatchObject({ arrival: 'Own vehicle', kind: '', color: '', plate: '' });
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
  });

  it('submits the ID photo and the whole group in one request, and ignores a double click', async () => {
    await openForm();
    fillRequired({ name: 'Group Lead' });
    type(/^Person you/, 'Maria Reyes');
    type(/^Friends visiting/, 'Friend One\nFriend Two\n');
    expect(screen.getByText(/3 people in this request/)).toBeTruthy();
    send(); send();
    await screen.findByText('Your request was sent');
    expect(posts.length).toBe(1);
    const b = posts[0];
    expect(b.friends).toEqual(['Friend One', 'Friend Two']);
    expect(b.id_photo).toMatch(/^\/9j\//);          // base64 JPEG, no data: prefix
    expect(b).toMatchObject({ name: 'Group Lead', house: 'B1-L4', host: 'Maria Reyes', purpose: 'Dinner', arrival: 'Walking', kind: '', color: '', plate: '' });
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
  });

  it('rejects a repeated group member name beside the field', async () => {
    await openForm();
    fillRequired({ name: 'Dup Lead' });
    type(/^Friends visiting/, 'Pat Lee\npat lee');
    send();
    expect((await screen.findByText(/listed twice/)).textContent).toMatch(/Pat Lee|pat lee/);
    expect(posts.length).toBe(0);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  });

  it('shows a clear message when the server cannot be reached, and lets the visitor retry', async () => {
    await openForm();
    fillRequired({ name: 'Offline Person' });
    globalThis.fetch.mockImplementationOnce(() => Promise.reject(new TypeError('Failed to fetch')));
    send();
    expect((await screen.findByRole('alert', {}, { timeout: 3000 })).textContent).toMatch(/Cannot reach the server/);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Send request' }).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  });
});
