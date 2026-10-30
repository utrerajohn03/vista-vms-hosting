# Hosting guide: Supabase (database) + Render (API) + Vercel (website)

Lahat ay may free plan. Gawin ayon sa pagkakasunod.

## Laman ng folder
```
render.yaml   -> Render Blueprint (API)
backend/      -> FastAPI (Render)
frontend/     -> React website (Vercel), may vercel.json na
database/     -> SQL (kusa nang tumatakbo, AUTO_MIGRATE=1)
```

## 1. GitHub
Gumawa ng bagong repository sa github.com. I-upload ang **LAMAN** ng folder na ito (hindi ang zip, at hindi ang folder mismo), para nasa **pinakaugat (root) ng repo** ang `render.yaml`, `backend/` at `frontend/`. Kailangang nasa root ang `render.yaml` para mabasa ng Render. Huwag mag-upload ng `.env` o API keys.

## 2. Supabase (database)
1. supabase.com > gumawa ng New project. Tandaan ang database password.
2. Sa project mo, pindutin ang **Connect** button sa itaas ng page.
3. Piliin ang **Session pooler**. Kopyahin ang connection string (ganito ang itsura: `postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-<region>.pooler.supabase.com:5432/postgres`).
4. Palitan ang `[YOUR-PASSWORD]` ng password mo (walang bracket). Kung may espesyal na character ang password (`@`, `/`, `#`, `:`), i-URL-encode ito, o mas madali, mag-reset ng password na letters at numbers lang.
5. Ito ang `DATABASE_URL`. Bakit Session pooler: IPv4-compatible ito at para sa persistent na server tulad ng API na ito. Ang Direct connection ay IPv6 lang bilang default.
6. Walang kailangang i-run na SQL: gagawa ang API ng tables pagka-start (`AUTO_MIGRATE=1`).

## 3. EmailJS (email ng QR, approval link at invitation) - gawin bago mag-Render
EmailJS ang email tool ng sistema ayon sa brief. HTTPS API ito, kaya gumagana sa Render free plan (na humaharang sa SMTP).
1. Mag-sign up sa emailjs.com.
2. **Email Services** > **Add New Service** > piliin ang provider (hal. Gmail) at i-connect ang email na gagamiting sender. Kopyahin ang **Service ID**.
3. **Email Templates** > **Create New Template**. Sa template settings:
   - **To Email**: `{{to_email}}`
   - **Subject**: `{{subject}}`
   - **Content** (halimbawa):
     ```
     {{message}}

     <img src="{{qr_url}}" alt="QR code" width="240" height="240">
     {{qr_code}}
     ```
   Isang template lang ang gamit ng app para sa lahat ng email. Sa mga email na walang QR (invitation, approval link), walang laman ang `{{qr_url}}`, kaya maaaring may walang-laman na larawan sa ibaba ng email. Hindi nito sinisira ang email; nasa `{{message}}` ang buong teksto at mga link.
   Kopyahin ang **Template ID**.
4. **Account** > **General**: kopyahin ang **Public Key**.
5. **Account** > **Security**: i-on ang **Allow EmailJS API for non-browser applications**, at kopyahin ang **Private Key** (Access Token).
6. Ihanda ang apat na value: `EMAILJS_SERVICE_ID`, `EMAILJS_TEMPLATE_ID`, `EMAILJS_PUBLIC_KEY`, `EMAILJS_PRIVATE_KEY`. Ilalagay ang mga ito sa Render sa susunod na step.
7. Itago ang Private Key at huwag i-commit.

## 4. Render (API)
1. render.com > **New** > **Blueprint** > ikonekta ang GitHub at piliin ang repo. Babasahin nito ang `render.yaml`.
2. Hihingin ang mga value na ito (yung may `sync: false`):
   | Name | Ilalagay |
   |---|---|
   | `DATABASE_URL` | Session pooler string mula Supabase |
   | `STAFF_ACCESS_CODE` | code na itatype ng staff sa sign in |
   | `SUPER_ADMIN_CODE` | sarili mong code bilang platform owner |
   | `EMAILJS_SERVICE_ID` | Service ID mula EmailJS |
   | `EMAILJS_TEMPLATE_ID` | Template ID mula EmailJS |
   | `EMAILJS_PUBLIC_KEY` | Public Key mula EmailJS |
   | `EMAILJS_PRIVATE_KEY` | Private Key mula EmailJS |
   | `CORS_ORIGINS` | `*` muna |
   | `FRONTEND_URL` | pansamantalang `https://temp.example` (papalitan sa step 6) |
3. Pindutin ang Apply/Deploy at hintayin na matapos ang deploy.
4. Kopyahin ang URL ng service (`https://<pangalan>.onrender.com`). Buksan ang `https://<pangalan>.onrender.com/api/health`. Dapat may ok na sagot.

## 5. Vercel (website)
1. vercel.com > **Add New...** > **Project**.
2. Sa **Import Git Repository**, pindutin ang **Import** sa tabi ng repo mo.
3. Sa **Root Directory**, pindutin ang **Edit** at piliin ang `frontend`.
4. Framework Preset: Vite (kusang nade-detect). Build command at output directory: iwanan sa default (`npm run build`, `dist`).
5. Sa **Environment Variables** ilagay ang `VITE_API_URL` = Render URL mo, walang `/` sa dulo.
6. **Deploy**. Kopyahin ang Vercel URL.
7. Tandaan: ang `VITE_` na variables ay isinasama sa website **sa oras ng build**. Kapag binago mo ang `VITE_API_URL` pagkatapos, kailangan mong mag-**Redeploy** para tumalab.

## 6. Balik sa Render (huling ayos)
Render > iyong service > **Environment**. I-update at i-save (magre-redeploy ito):
- `CORS_ORIGINS` = Vercel URL (hal. `https://vista-vms.vercel.app`)
- `FRONTEND_URL` = Vercel URL

Ang `PUBLIC_API_URL` (para lumabas ang QR picture sa loob ng email, sa `{{qr_url}}` ng template) ay kinukuha na ng app nang kusa mula sa Render (`RENDER_EXTERNAL_URL`), kaya hindi mo na ito kailangang ilagay.

## 7. Subukan
1. Buksan ang Vercel URL at mag-sign in gamit ang code.
2. Gumawa ng household (may email), mag-submit ng visit bilang visitor (may email), at i-approve bilang household.
3. Dapat may dumating na email na may QR sa dalawa. Kung wala, tingnan ang **Render > Logs**: `EMAIL NOT SENT to ... (dahilan)`.

## Mga paalala
- **Free Render ay natutulog** pagkatapos ng 15 minutong walang request (docs ng Render), at mabagal ang unang bukas. May 750 free instance hours bawat buwan: sapat para sa isang service na laging gising, pero kapag naubos, sinususpinde ang service hanggang sa susunod na buwan. Maaari ring i-restart ng Render ang free service anumang oras. Para laging gising, gumamit ng uptime pinger sa `/api/health` o mag-upgrade sa paid.
- Hindi ginagamit ang Render Postgres dito (Supabase ang database), kaya hindi ka maaapektuhan ng 30-araw na pag-expire ng free Render database.
- Kung mali ang `CORS_ORIGINS`, "Failed to fetch" ang lalabas sa website. Dapat eksakto ang Vercel URL (https, walang `/` sa dulo).
- Huwag i-commit ang secrets (`.env`, API keys).
- Ang `SECRET_KEY` at `CRON_KEY` ay ginagawa ng Render. Huwag palitan pagkatapos, para hindi mag-expire ang mga link.
