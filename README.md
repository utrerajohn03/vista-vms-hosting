# Vista VMS: Village system

React (Vite) + Tailwind frontend, and a FastAPI + asyncpg + PostgreSQL backend.
Everything the UI shows comes from PostgreSQL. Every action calls the API and writes an audit row.

```
vista-vms/
  backend/                    FastAPI API (Render)
    app/            main.py, api.py (village routes), superadmin.py (platform routes), core.py (auth, rules, Missing job),
                    snapshot.py, seed.py, db.py (migration runner), config.py
    migrations/     0001 to 0010, numbered, applied once each (foundation, village, rls, entry photos, visitor ID photos,
                    village map and routes, visitor email, platform, staff passwords, token version)
    tests/          101 API tests against real PostgreSQL
    migrate.py      python migrate.py
  frontend/                   React + Vite + Tailwind (Vercel)
    src/            App.jsx, store.jsx (state + API calls), api.js, config.js (pages and menus), actions.jsx,
                    modals.jsx (gate check, exit, forms), components/Table.jsx, pages/ (Front, Shell, Custom)
    e2e/            UI end-to-end tests (Vitest + Testing Library) against the real API and database
    vercel.json     SPA rewrite so every property path loads the app
  Dockerfile, docker-compose.yml, render.yaml   (API + database only)
```

The API serves no HTML. The browser loads the React app from Vercel, and the app calls the Render API
(`VITE_API_URL`). The API allows only the origins listed in `CORS_ORIGINS`.

## Run it on your computer

Terminal 1, the API:

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://vista:vista@localhost:5432/vista   # any PostgreSQL 14+, create the database first
AUTO_SEED=1 uvicorn app.main:app --reload                           # migrates and loads demo data on start
```

Terminal 2, the UI (Node 18+):

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 ; Vite forwards /api to http://127.0.0.1:8000
```

Or `docker compose up --build` for PostgreSQL and the API together (demo mode, `AUTO_SEED=1`), then run the UI as above.
`python migrate.py` applies migrations alone (it exits with code 1 and a plain message if the database does not fit, see *Migrations*).
`python -m app.seed --empty` creates a clean village (one gate, 20 passes) without demo people.

**Demo mode** is what you get when `STAFF_ACCESS_CODE` is empty: the API believes the `X-Role` header, so anyone can be any role.
It exists for local work only. On Render the API refuses to start in that state unless `ALLOW_DEMO_AUTH=1`.

## The village link and the two doors

One deployment serves many villages. The address decides what you see:

- **`/` (the main site)** is for **Admins** and the **Super Admin**. An Admin signs in with email and password, or with the personal link the Super Admin sent. The village link plus the shared staff access code still works while `STAFF_CODE_LOGIN=1`. There is no list of villages, so nobody can browse them.
- **`/<village-link>`**, for example `/greenfield-village-7f3a`, is **one village's own page**: visitors register and retrieve their QR there, and the village's guards, HOA office and households sign in there. The Admin option is not offered on this page. A wrong link shows one plain "not valid" page and reveals nothing.
- A village link is the village name plus a random code (`greenfield-village-7f3a`). The random part keeps it from being guessed, so treat the link like a key for who may open the page: print it as the gate QR and give it to the people who need it. Anyone with the link can reach the visitor form, but nobody can sign in without a password, the staff access code or a personal link.
- Household invitation links point at the village's own page: `https://your-app/<village-link>?invite=...`.
- The village name and link shown in the app (header, Settings, Print gate QR) come from the server. Renaming the village in Settings changes its name, never its link.
- `vercel.json` sends every path to the app, so these addresses work after a refresh. `GET /api/property/{link}` is the one public call a village page makes before sign-in (it returns the village name only).
- Another village is created by the Super Admin (next section). From the command line: `cd backend && python -m app.seed --empty --name "Palm Grove Village" --new-link` (prints the link).

## Super Admin (platform level)

The Super Admin is outside every village. Set `SUPER_ADMIN_CODE` (its own code, not the staff code) and `SECRET_KEY` on the API, then open the **main site** (`/`) and choose **Platform owner? Super Admin sign-in**.

- **Create a property**: name, village type and the one Admin (name and email). The system makes the village link from the name plus a random code (`/palm-grove-village-7f3a`), adds a Main gate and a pass inventory, and emails the Admin a personal sign-in link (`/?admin=...`, `ADMIN_LINK_DAYS`, default 14). The page also shows both links so you can copy them if EmailJS is not set up.
- **One Admin per property** (enforced in the database). **Change Admin** replaces the Admin: the old Admin's session and link stop working at once. **Admin link** sends a fresh link.
- **The Admin link is spent once the Admin sets a password.** It signs the Admin in until then (it can be opened on more than one device before a password exists). After a password is set it is refused, and the Admin signs in with email and password.
- **Switch off / on** a village: nobody can open it (visitors, staff, households, its Admin) until it is switched on again. Its data is kept. The village link never changes.
- **Overview**: properties, households (verified), visits today, people inside, open alerts, and properties with no Admin.
- **Audit**: everything the Super Admin does is in *Platform audit*. **Open** works inside a village as its Admin; that sign-in, and every action taken there, is written in the village's own Audit log with the role **Super Admin**. A banner shows *Back to platform*.

## Accounts, passwords and sessions

Guards, HOA office and the Admin can have personal accounts (email + password). Households sign in with their own signed link.

- **Sign in:** `POST /api/session` with `{email, password}`. The server decides the role from the account. Passwords are scrypt-hashed, at least 10 characters (`MIN_PASSWORD`), used exactly as typed. Guesses are limited per account (10 a minute) and per address (`LOGIN_RATE_LIMIT_PER_MIN`). A wrong password, an unknown email and a switched-off account all get the same reply.
- **Set or reset a password:** the Admin adds staff with a password (Admin > Guards, HOA office > *Add account*) and can set a new one later with *Edit*. A person with no password cannot sign in.
- **Change your own:** the **Change password** button, `PUT /api/me/password`. Needs the current password (an Admin who just arrived by the Super Admin's link and has no password yet needs none). Guesses at the current password are limited to 10 a minute per account.
- **Sessions end when they should.** Each personal account has a counter (`users.vista_token_version`, migration `0010`) that every sign-in token and every Admin link carries. A password change or reset, and switching the account off or on, add 1, so every token issued before stops working at once. Reactivating an account does not bring old tokens back. Changing your own password ends your other devices and returns a fresh token, so this device stays signed in. When the server ends a session, the app signs the person out with a message.
- **Shared staff code:** while `STAFF_CODE_LOGIN=1`, a staff access code signs in a guard, HOA or Admin without a personal account (a 12-hour token with no account behind it, so it cannot be switched off individually). With `STAFF_CODE_LOGIN=0` the code signs nobody in **and sessions already made with it end too**. Personal accounts and household links are not affected.
- **Keep `STAFF_ACCESS_CODE` set even when `STAFF_CODE_LOGIN=0`.** Published mode is decided by `STAFF_ACCESS_CODE`: with it empty, the API trusts the `X-Role` header (demo mode). `STAFF_CODE_LOGIN` only controls whether the code itself signs people in.
- **Known gap: Admin password recovery.** An Admin who forgot their password can be sent a fresh link by the Super Admin, which signs them in, but *Change password* still asks for the current password. Until that is changed, a forgotten Admin password is fixed by the Super Admin using *Change Admin* (a new Admin account), not by a reset.

## Household approval by email link

- When a visitor's request matches a household, the account holder gets an email (EmailJS) with a link: `https://your-app/<village-link>?approve=<token>`. It opens a confirmation page with **Approve**, **Decline** and **Not for me**. No sign-in is needed: the signed link is the key, it opens only that one request in that village, and it expires after `APPROVAL_DAYS` (default 7).
- The page shows the visitor, the group, purpose, time and arrival method, never restricted areas. A household the HOA has not verified yet cannot approve, from the link or from the app.
- Needs `SECRET_KEY` (and `FRONTEND_URL` so the link points at the Vercel site). Without `SECRET_KEY` (demo mode) there is no link and the household approves in the app under Visit requests.
- The visitor form has an optional **Email**. When the household approves, the QR code (as a picture) is emailed there (Settings > Email QR codes to visitors), and a copy goes to the household's account holder too. See EMAIL-SETUP.md.

## Admin: map, wayfinding, settings, reports

- **Village map**: Import a PNG, JPEG, WebP or PDF (8 MB at most). It is stored in the database (`village_maps`), so every Admin device sees it. Pick a lot or gate, click the map to place it as a pin. Blocks are marked from the lot codes (B1-L4 is in Block 1). There is no capacity limit on the map. There are no drawing tools and no route graph.
- **Wayfinding**: each lot has an automatic text route (gate, road, block, lot). **Edit route** writes your own directions; visitors see them only after the pass is issued, and restricted areas are never shown.
- **Settings** are saved per village (`PUT /api/settings`) and the server uses them: *Missing after (hours)* and *Entry photo retention (days)* (the environment variables `MISSING_HOURS` and `PHOTO_RETENTION_DAYS` are only the defaults), *Primary adult sees other adults' visitors*, *Who verifies households*, and the notification switches.
- **Reports** are computed from the visits, alerts and vehicle checks of the last 7 days. **Export** on Reports and Audit log downloads a CSV.

## QR passes and the gate scanner

- A visitor's QR is a real, standard QR code holding `VISTA:<token>` (the token is the visit's `qr_token`). Any phone camera can read it. The visitor can also tap **Save QR image** on the pass page.
- Guards and admins get a **Scan QR** button on the **Gate** page (opens the gate check for an approved visit) and on the **Exit** page (opens the exit dialog for a visitor who is inside). It uses the phone or laptop camera. If there is no camera, or the page is not on https, the same dialog accepts the typed code or a reference such as `VS-0004`.
- The camera only works on **https** pages or `localhost` (the browser blocks it on plain `http://192.168...`). Vercel is https, so the deployed app is fine. For phone testing on your Wi-Fi, use the typed code, or an https tunnel.
- `POST /api/visits/scan` (guard and admin) finds the visit for a code. It is read-only: check-in still needs the ID, vehicle and pass checks.
- **Settings > Print gate QR** opens a print page with a QR of the village link.

## Deploy: Vercel (UI), Render (API) and Supabase (PostgreSQL)

The UI and the API are two sites, so the API must allow the UI's address (`CORS_ORIGINS`) and the UI must know the API's address (`VITE_API_URL`). Do the steps in this order.

### 1. Supabase (database)
1. supabase.com, **New project**. Pick the region closest to your users (Singapore for the Philippines) and set a database password. A plain letters-and-numbers password avoids URL-encoding problems.
2. Open the project, click **Connect**, choose **Session pooler**, and copy the URI. It looks like
   `postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres`.
   Replace `[YOUR-PASSWORD]` with your password (percent-encode `@ : / ? #` if you used them).
   Use the pooler, not the "Direct connection": the direct host is IPv6-only on Supabase unless you buy the IPv4 add-on, and most hosts connect over IPv4.
   The Transaction pooler (port 6543) also works: the app switches off prepared statements by itself, and migrations use transaction-level locks that work through it.
3. That is all. Do not create tables by hand: the app creates them on first start. It also turns on row level security for the tables it creates, so Supabase's public REST API cannot read them (check: Table Editor shows "RLS enabled"). It does not touch tables it did not create, see *Migrations*.

### 2. Render (API)
1. Push this folder to a GitHub repository (the folder that contains `backend/`, `frontend/` and `render.yaml`).
2. render.com, **New > Blueprint**, pick the repository. Render reads `render.yaml`.
3. When asked, fill in:
   - `DATABASE_URL`: the Supabase URI from step 1
   - `STAFF_ACCESS_CODE`: the code staff will type to sign in (make it long)
   - `SUPER_ADMIN_CODE`: the platform owner's own code, different from the staff code
   - `FRONTEND_URL`: the same Vercel address (invitation and approval links are built from it)
   - `CORS_ORIGINS`: your Vercel address, for example `https://vista-vms.vercel.app` (you get it in step 3: put a placeholder now and edit it after the Vercel deploy; do the same for `FRONTEND_URL`)
   `SECRET_KEY` and `CRON_KEY` are generated for you.
4. Deploy. On the first start the app creates the tables and an empty village (`AUTO_BOOTSTRAP=1`: one gate, 20 passes).
   No Blueprint? Create a **Web Service** instead: build `pip install -r backend/requirements.txt`, start `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check path `/api/health`, and the same environment variables as `backend/.env.example`.
5. Open `https://<your-service>.onrender.com/api/health` (expect `{"ok":true}`).

### 3. Vercel (React app)
1. vercel.com, **Add New > Project**, pick the same GitHub repository.
2. Set **Root Directory** to `frontend`. Vercel detects Vite (build `npm run build`, output `dist`; `frontend/vercel.json` already says so).
3. Add the environment variable `VITE_API_URL` = your Render address, for example `https://vista-vms.onrender.com` (no trailing slash). Deploy.
4. Copy the Vercel address (for example `https://vista-vms.vercel.app`), go back to Render, and put it in `CORS_ORIGINS` (comma separated if you have more than one) and in `FRONTEND_URL`. Render restarts by itself.
5. Open the Vercel address. The top right of the first screen says **System online** when the UI can reach the API. If it says offline, `VITE_API_URL` or `CORS_ORIGINS` is wrong. Changing `VITE_API_URL` needs a redeploy because it is read at build time.
6. Vercel preview deployments get their own addresses. To allow them, set `CORS_ORIGIN_REGEX` on Render, for example `https://vista-vms-.*\.vercel\.app`.

### 4. First use (the order that works)
1. Open the Vercel address and choose **Platform owner? Super Admin sign-in** with `SUPER_ADMIN_CODE`. Create the property with its Admin (name and email). Copy the Admin link if EmailJS is not set up.
   (Without `SUPER_ADMIN_CODE`: **I'm staff**, enter the staff access code, sign in as **Admin** on the empty village that `AUTO_BOOTSTRAP=1` created.)
2. The Admin opens the link, then sets a password (**Change password**). The link stops working from then on; the Admin signs in with email and password.
3. **Households > Invite household**, type the account holder's email. A dialog shows their **invitation link**: copy it and send it to them (the same link is emailed if EmailJS is set up). Use **Copy sign-in link** on any household row to get a fresh link later.
4. The account holder opens the link (no code, no password), fills in the **Household form** (owner, block and lot, people living there) and saves. The household is now *Awaiting HOA*.
5. The **HOA office** verifies the household. Until then it cannot approve visits.
6. Add gates and passes, guard and HOA accounts **with passwords**, restricted areas (Admin). Print the village link as a QR code for the gate (Settings > General); visitors open that link and register, no account needed.
7. When every staff member has a password, set `STAFF_CODE_LOGIN=0` (keep `STAFF_ACCESS_CODE` set).
8. To try everything with demo people first, set `AUTO_SEED=1` and `AUTO_BOOTSTRAP=0` on a throwaway database.

The household link is that household's only credential, so treat it like a password. It lasts 30 days (`INVITE_DAYS`); the Admin can issue a new one at any time.

### Emails (optional)
Email works by EmailJS (the platform's email tool; HOSTING.md step 3), or by SMTP on a laptop only (EMAIL-SETUP.md). EmailJS is used first when it is set. Everything works without email, because the Admin and the Super Admin can hand over links. To also email them, create an EmailJS service and template with the variables `{{to_email}}`, `{{subject}}`, `{{message}}`, `{{qr_code}}` and `<img src="{{qr_url}}">`, turn on **Account > Security > allow API calls from non-browser apps**, and set `EMAILJS_SERVICE_ID`, `EMAILJS_TEMPLATE_ID`, `EMAILJS_PUBLIC_KEY` and `EMAILJS_PRIVATE_KEY` on Render. Emails that carry a link: household invitation and reminder, the Admin's sign-in link, and the household's approval link. The visitor's QR email is sent when the visitor gave an email and the household approved. Other notices are subject-only. If EmailJS refuses a message, the reason is written to the Render log.

### 5. Keep it awake (free plan only)
Render's free plan sleeps after about 15 minutes without traffic, which pauses the Missing check and makes the first visit slow.
Fix: create a free job at cron-job.org that sends **POST** `https://<your-service>.onrender.com/api/cron/missing?key=<CRON_KEY>` every 5 minutes. It keeps the service awake and runs the Missing check. A paid plan does not need this.

## Environment variables

UI (Vercel): `VITE_API_URL` only (see `frontend/.env.example`). Leave it empty when running locally.

API (Render), all read in `backend/app/config.py`; the same list with comments is in `backend/.env.example`:

| Variable | Default | What it does |
|---|---|---|
| `DATABASE_URL` | `postgresql://vista:vista@localhost:5432/vista` | PostgreSQL. Supabase: use the Session pooler URI |
| `DB_SSL` | `auto` | `auto` = SSL for Supabase hosts, or `require` / `disable` |
| `DB_PGBOUNCER` | empty | `1` for the transaction pooler without `?pgbouncer=true` |
| `DB_POOL_MAX` | `8` | connection pool size |
| `STAFF_ACCESS_CODE` | empty | **Decides published vs demo mode.** Set = role headers are ignored. Empty = demo mode (any role by header) |
| `STAFF_CODE_LOGIN` | `1` | `0` = the shared code signs nobody in and ends sessions made with it. Keep `STAFF_ACCESS_CODE` set |
| `SECRET_KEY` | empty | Signs tokens and links. Required when `STAFF_ACCESS_CODE` or `SUPER_ADMIN_CODE` is set; use 16+ random characters |
| `SUPER_ADMIN_CODE` | empty | Platform owner's sign-in. Must differ from `STAFF_ACCESS_CODE`; needs `SECRET_KEY` |
| `SESSION_HOURS` | `12` | how long a sign-in token lasts |
| `ADMIN_LINK_DAYS` | `14` | the Admin's first sign-in link |
| `INVITE_DAYS` | `30` | household sign-in link |
| `APPROVAL_DAYS` | `7` | approve/decline link in the household email |
| `FRONTEND_URL` | empty | the Vercel address; links in emails are built from it |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | allowed UI origins, comma separated |
| `CORS_ORIGIN_REGEX` | empty | also allow origins matching this (Vercel previews) |
| `ALLOW_DEMO_AUTH` | `0` | `1` lets the API start on Render without `STAFF_ACCESS_CODE` (throwaway demos only) |
| `AUTH_MODE` | `dev` | leave as is. With no `STAFF_ACCESS_CODE`, any other value makes role headers fail with 501 (a hook for plugging in platform auth in `core.ctx`) |
| `LOGIN_RATE_LIMIT_PER_MIN` | `20` | sign-in attempts per address per minute. Per-account limits are fixed at 10 a minute |
| `RATE_LIMIT_PER_MIN` | `60` | limit on public endpoints |
| `TRUST_PROXY_HOPS` | `1` | proxies in front of the API (Render = 1) for `X-Forwarded-For` |
| `AUTO_MIGRATE` | `1` | apply migrations on start |
| `AUTO_BOOTSTRAP` | `0` | create an empty village (one gate, `PASS_COUNT` passes) if missing. `render.yaml` sets it to `1` |
| `AUTO_SEED` | `0` | load demo households and visits (testing only) |
| `SEED_PASSWORD` | empty | with `AUTO_SEED=1`, gives the seeded Admin, guard and HOA accounts this password (10+ characters). Demo and tests only |
| `DEFAULT_PROPERTY`, `VILLAGE_NAME`, `PASS_COUNT` | `greenfield-village-7f3a`, `Greenfield Village`, `20` | the first village |
| `MISSING_HOURS` | `3` | default for *Missing after (hours)*; Settings overrides it per village |
| `PHOTO_RETENTION_DAYS` | `30` | default for entry and ID photo retention; Settings overrides it per village |
| `TIMEZONE` | `Asia/Manila` | |
| `CRON_KEY` | empty | key for `POST /api/cron/missing` |
| `ENABLE_RLS` | `1` | close the Supabase REST API on the tables this app created |
| `SCHEMA_CHECK` | `1` | at start, check that tables a platform already owns have what Vista needs. `0` skips it |
| `EMAILJS_SERVICE_ID`, `EMAILJS_TEMPLATE_ID`, `EMAILJS_PUBLIC_KEY`, `EMAILJS_PRIVATE_KEY` | empty | email (all four needed; EmailJS is tried first, then SMTP) |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` | empty | optional, laptop only (Render free blocks SMTP) |

The API refuses to start if: `STAFF_ACCESS_CODE` or `SUPER_ADMIN_CODE` is set without `SECRET_KEY`; `SUPER_ADMIN_CODE` equals `STAFF_ACCESS_CODE`; or it runs on Render without `STAFF_ACCESS_CODE` and without `ALLOW_DEMO_AUTH=1`.

Other security facts: the sign-in rate limit counts the address your host's proxy reports (`TRUST_PROXY_HOPS`), so a made-up `X-Forwarded-For` does not bypass it. The "advance the clock" button only works in demo mode; with `STAFF_ACCESS_CODE` set the API ignores `simulate_hours`.

## Migrations and a shared database

`migrations/NNNN_*.sql` are applied in order, once each, each inside a transaction. `0001_foundation.sql` creates `properties`, `users`, `visits`, `badges`, `audit_log`, `notifications`, `alerts`, `gates` and `settings` only if they do not exist, so it can run next to a platform that already owns them.

- **Own bookkeeping.** The log is `vista_schema_migrations` (not `schema_migrations`, which another system may use). A v13 database that logged into `schema_migrations` is imported automatically, only when that table is clearly Vista's (our first two file names and our village tables); the old table is left alone.
- **Table ownership.** Every table a Vista migration creates is recorded in `vista_owned_tables`. Row level security and the revoke from `anon` / `authenticated` (`0003_rls.sql`, also re-applied at each start) are applied **only** to those tables, `village_*` and `platform_audit`. A table the platform already owned keeps its own protection and grants, so make sure the platform has protected it.
- **Village tables the platform already made.** The brief says the village households tables come from the platform's own migration (its 0003) and the Village group *extends* them. `0002_village.sql` therefore only creates `village_households`, `village_members` and `village_lots` if they are missing, and otherwise **adds each column the app uses that is missing** (existing rows keep their data). Right after `0002`, inside its transaction, the runner checks the columns and that `village_households.status` allows `invited`, `awaiting` and `verified`; if not, `0002` is undone and the message says what to change. The platform's real column names were not available, so a platform column that means the same thing under another name is **not** recognised: Vista would add its own column next to it.
- **Start-up check.** After `0001`, after `0002` and again at the end, the runner checks that existing tables have the columns the app uses and that CHECK lists or enums allow every value the app writes (user roles, visit and pass statuses, alert statuses). A mismatch stops the start with a message that lists what to change. A mismatch in `0001` is found inside its transaction, so nothing of Vista's is created. `SCHEMA_CHECK=0` skips the check.
- **Guards for shared tables.** `0008` makes "one Admin per property" a database rule and refuses to run if a property already has two `admin` rows. `0009` adds `users.password_hash` and refuses to run if that column already holds hashes Vista did not write. If your platform's `users` table has a password column of its own, do not share it: rename Vista's column in `0009` and in the code, or keep staff accounts in a separate table. `0010` adds `users.vista_token_version`.
- **Several instances.** A transaction-level advisory lock serialises migrations and the lockdown, so two instances starting together are safe, also through a transaction pooler.
- **Not handled:** the app assumes the `public` schema and a PostgreSQL where `gen_random_uuid()` exists (13+). `0001` also runs `CREATE EXTENSION IF NOT EXISTS pgcrypto`, which needs a role allowed to do that if it is not installed yet.

The checks above were tested against simulated shared databases (same table names, other shapes). They have not been run against the real platform schema or a real Supabase project.

## Compared with the brief (Vista-VMS-Village-System.docx, version 2)

Checked by reading the code and the existing tests, not by walking every screen again. Matches the brief: the process flow A to G (setup, form, neutral reply and red flag, approval by email link or in the app, gate check with vehicle photo and logged override, passes per person in a group, house scan, 3-hour Missing, exit, HOA queue with *reject with a reason*, walk-in, wrong destination, close with a reason code); the six user types and what each can do; the Admin menu (Dashboard, Visits, Households, Village map and wayfinding, Gates and passes, Guards and HOA office, Restricted areas, Alerts, Messages, Reports, Audit log, Settings); a `property_id` on every village table; the defaults of the *Open decisions*; Super Admin sign-ins to a property audited.

Differences you should know about:

- **Overstay and "vehicle has not left" are not detected automatically.** A guard or Admin closes the visit with the reason *Vehicle not left*, *Overstay* or *Pass not returned*, which raises the alert and notification. The brief gives no time limit for an overstay, so none was invented. Decision needed: how long after the visit's end (or the gate notice) counts as an overstay.
- **The map editor does not draw blocks.** An imported map (image or PDF) is stored in the database, lots and gates are added and placed as pins on it, each lot is linked to a household and shows the people listed, and blocks are marked from the lot codes. Drawing the map itself, and drawing or editing a block's shape, are not built, although the page text says "import or draw".
- **Foundation tables are still stand-ins** for the platform's (`0001_foundation.sql`), and the village tables follow the new extend-not-recreate rule above. The Shared Platform Guide and the platform's migration 0003 were not available, so the real names are unchecked.
- Not part of this group's work, so not here: the items under *Provided next by the core team* (email invitation templates beyond what is described above, the Needs attention queue, and so on).

## Try the flow

1. **Visitor** (no account): Register now with name, phone, house `B1-L4`, ID or photo, purpose, date and time. The reply is the same for any house or name.
2. **Staff**: in demo mode **Sign in** as **Household account holder**, household *Maria Reyes (B1-L4)*, and approve the request. (With `SEED_PASSWORD`, sign in with the seeded email and that password.)
3. **Visitor**, Retrieve your QR pass: name and phone, now shows the QR.
4. **Security guard**: Gate, Check in: tick ID. For a car, take the entry photo (on a phone this opens the camera), then answer *matches* or *does not match* for plate, color and type (a mismatch needs an override with a reason). Issue passes. You can also use **Scan QR** to jump straight to a visitor.
5. **Household**, At the house: Scan at house, or scan a pass from another household to see the wrong-destination flag.
6. **Security guard**, Exit: scan each person out by typing or scanning the **pass number** (or tap their name), compare the car with the entry photo, tick Vehicle left, Mark left. Passes become available again.
7. **Admin**: every page of the Admin menu, plus Alerts, **Advance clock 3 hours** (calls the real Missing job, demo mode only), and the Audit log.

Demo accounts and households are in `backend/app/seed.py`. Unmatched requests land in the **HOA office** queue.

## Rules enforced by the API (not just the UI)

| Rule from the brief | Where |
|---|---|
| Neutral reply, never reveals who lives where | `POST /api/visits` returns the same body for match and no match |
| Public visitor request needs name, phone (7+ digits), house, ID or photo (JPEG, 1.5 MB), purpose (200 characters max), date and time | `POST /api/visits`. Walk-ins (`POST /api/walkins`) need only name and house |
| Unverified household cannot approve | `POST /api/visits/{ref}/decision` returns 403 |
| Not for me goes to the HOA queue | `POST /api/visits/{ref}/not-for-me` |
| Red flag needs an extra verification tick | `POST /api/visits/{ref}/check-in` |
| Vehicle check: a real entry photo (JPEG, max 1.5 MB), mismatch override with reason, logged | same endpoint, rows in `village_vehicle_checks` and `village_entry_photos` |
| Visitor's ID photo is shown to guard and admin only and deleted after the retention days | `GET /api/visits/{ref}/id-photo`, migration `0005`, `core.purge_photos` |
| Entry photos are personal data: only guard and admin can view them, deleted after the retention days | `GET /api/visits/{ref}/entry-photo`, `core.purge_photos` (background loop) |
| Household form: owner, block and lot (like `B1-L4`) or a house number, a valid email and phone, at least one person, and the account holder listed as an adult. Plain messages, nothing saved when it fails | `PUT /api/me/household` |
| A verified household that changes its lot must be verified again | same endpoint (status goes back to Awaiting HOA) |
| HOA verifies only a complete household, and only once. The HOA sees the people, email and phone first | `POST /api/households/{hid}/verify`, Verify review dialog |
| Removing a person from the form never fails because they host a visit | migration `0004`, `ON DELETE SET NULL` |
| One pass per person, passes from inventory | check-in, `badges` + `village_visit_people` |
| Walk-in: no pass until the household approves | status `walkin_pending` blocks check-in |
| Resident scan marks Arrived; another household's pass is a wrong destination | `POST /api/passes/{code}/arrived` |
| Missing after the configured hours with no house scan | `core.mark_missing`, background loop every minute |
| Exit: scan each person (by pass number or name), vehicle left, passes return. Closing with *Pass not returned* marks only the passes not scanned out as Lost | `exit-scan`, `left`, `close` |
| Primary adult sees other adults' visitors only for minors (Settings can change it) | `snapshot.build_state` |
| HOA "Today's visits": scheduled for today (or requested today with no date) or entered today | `today` flag in `snapshot.build_state` |
| Guard is notified when a resident scans a pass at the house, and sees Missing notices | guard `msgs` in `snapshot.build_state`, Guard **Notices** page |
| Directions only after check-in, never restricted areas | `POST /api/visits/lookup` |
| A deactivated account, a changed password or a replaced Admin ends its sessions at once | `core.ctx` checks `users.active`, role and `vista_token_version` on every request |
| Property isolation | every query filters `property_id`; the token, not a header, decides the village; tested with a second property |
| Roles | `core.need(...)`; a household gets only its own data in `/api/state` |

## Tests

```bash
cd backend && python -m pytest -q                 # 97 tests, creates and drops a vista_test database
TEST_APP_DSN='postgresql://u:p@host:6543/vista_test?pgbouncer=true' python -m pytest -q   # same suite through a pooler
```

The 97: 44 flow (`test_flow.py`), 25 hosting and platform (`test_hosting.py`), 16 password, deactivation and token tests (`test_auth_lifecycle.py`), 12 migration tests (`test_migrations.py`: a simulated shared database, incompatible tables, the platform's own village tables, v13 upgrade, two instances starting together). They need a PostgreSQL role that can create databases and roles (`anon` / `authenticated` are created if missing).

UI end-to-end tests (they drive the real React screens against the real API and database; use a fresh database for each run):

```bash
# demo mode: fresh seeded database, no access code
cd backend && AUTO_SEED=1 uvicorn app.main:app --port 8000
cd frontend && npm install && npm test

# published mode: the API and `npm test` need the same variables
export STAFF_ACCESS_CODE=letmein-staff-code SECRET_KEY=a-long-random-secret-key SUPER_ADMIN_CODE=owner-code-9876 \
       SEED_PASSWORD=seed-password-123 FRONTEND_URL=http://localhost:5173
cd backend && AUTO_SEED=1 uvicorn app.main:app --port 8000
cd frontend && npm test
```

Staff sign-in is limited to `LOGIN_RATE_LIMIT_PER_MIN` a minute per address; raise it (and `RATE_LIMIT_PER_MIN`) only for automated UI runs. `E2E_API` changes the API address.

## Test results for this version

Run for real on PostgreSQL 16:

| | Result |
|---|---|
| Backend tests | **97 passed**, 0 failed |
| Frontend production build (`npm run build`) | passes |
| UI end-to-end, demo mode | 35 passed, **2 failed**, 12 skipped (the skipped ones need published mode) |
| UI end-to-end, published mode | 42 passed, **4 failed**, 3 skipped (plus `scan.test.jsx` fails at set-up) |

**Remaining UI failures.** They are the same tests, in the same places, on the original v14 code before any of this version's changes (re-checked in the same session, three runs of the updated code and one of the original: identical lists), so they are not caused by it. Their causes were not investigated beyond the messages. One caution: an earlier demo-mode run of the same code gave 36 passed and 1 failed (only the map test), so this result is not stable between runs; the reason was not found.

- `e2e.test.jsx`, *admin: reports show real numbers and the map editor lets you pick a lot to place*: the label *Place on the map* is not found (fails in demo and published mode).
- `e2e.test.jsx`, *HOA corrects the unmatched request and resends it*: the text *Ghost* is not found (published mode, and in the later demo-mode runs).
- `forms.test.jsx`, two *Guard gate and exit* tests, and the `scan.test.jsx` set-up: the API answers *Not allowed for your role* in published mode. These tests seem to prepare data with role headers, which published mode ignores; they pass in demo mode.

The UI changes of this version (the password dialog taking the new token, signing out when the server ends a session) are checked by the production build only: no UI test covers them.

**Not run:** an actual Supabase project, an actual Render or Vercel deploy, `docker-compose.yml`, EmailJS, a real browser, the camera path of the QR scanner (only the decoder, the typed code and everything after a scan are tested), the real platform schema.

## What is not done yet (read before shipping)

- **Admin password recovery** (see *Accounts, passwords and sessions*). Changing a password needs the current one, also after a fresh Admin link.
- **The shared staff code** is one code for everybody and signs in as any role, including Admin. It stops strangers; it does not tell staff apart. Move everyone to personal accounts and set `STAFF_CODE_LOGIN=0`. In demo mode there is no authentication at all.
- **A shared platform database** is only checked against simulated schemas, see *Migrations*. Align table, role and status names with the real ones (the Shared Platform Guide and the platform's migration 0003 were not available). If the platform owns the foundation tables, a mismatch stops the start with a list; the shared `users.password_hash` column is a known risk.
- **Entry photos** are stored in PostgreSQL (`village_entry_photos`, shrunk to a JPEG of at most 1280 px by the app) and purged by the background job after the retention days. That is fine for a village's volume. For object storage later, only `check-in`, `entry-photo` and `purge_photos` change.
- **EmailJS:** `notify()` stores every message and calls EmailJS only if `EMAILJS_*` is set. The request the API sends to EmailJS is covered by a test with a mocked EmailJS; it was not run against a real EmailJS account.
- **QR and scanning:** pass badges are matched by their printed number (typed or read by a keyboard-style barcode scanner); the app does not print badge QR codes. The camera needs https or localhost.
- **Village map:** pins on an imported image, text directions, no route graph, no drawing of the map or of blocks (see *Compared with the brief*).
- **Not done:** pagination of large lists on the server, and rate limiting beyond the simple per-IP and per-account limiters.

## Update notes (backend hardening)

- **Password hashing no longer stops the API.** scrypt runs on a worker thread, so a sign-in or password change does not hold up the gate or anyone else (health-check latency during 12 simultaneous sign-ins: max 242 ms before, 64 ms after).
- **Request size limit.** A body over `MAX_BODY_BYTES` (default 3 MB, enough for a 1.5 MB photo as base64) is refused with 413 before it is read, whether or not the sender declares a length. The village map import has its own `MAX_MAP_BODY_BYTES` (default 12 MB, for the 8 MB file).
- **Free-text limits** with plain messages: person visited 120 characters, vehicle type 60, vehicle color 40, plate number 20.
- Tests: `cd backend && python -m pytest -q` (101 tests). The migration tests need a PostgreSQL reachable by host and port (`TEST_ADMIN_DSN=postgresql://user:pw@host:5432/postgres`), not a unix-socket-only DSN.

## Run it on a laptop (testing)

`START-HERE.md` has the steps (Docker Desktop + Node.js, then `start-local.bat` or `./start-local.sh`), the demo accounts and the common problems. `CHECKLIST.md` lists what to try for each role and what is still unverified. `docker-compose.local.yml` switches on every sign-in method with public test passwords: never use it for a real village.

With pgAdmin: `START-WITH-PGADMIN.md` (your own PostgreSQL via `start-nodocker.bat`/`.sh`, or pgAdmin on the Docker database at localhost:5433) and `pgadmin-queries.sql` (read-only queries).

Database to import into PostgreSQL: `database/vista_database.sql` (all tables plus the Greenfield demo village; `SELECT public.vista_remove_demo();` removes the demo for real use). Steps in `database/README.md`. Before you publish: `BAGO-I-PUBLISH.md`.
