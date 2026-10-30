# Email setup: QR code sa email (visitor AT household)

## Ano ang nagbago
Pag **na-approve** ng household ang isang visit, may mag-e-email na ngayon ng **totoong QR code (picture)**:

1. sa **visitor**, kung naglagay siya ng Email sa form (at naka-on ang *Settings > Notifications > Email QR codes to visitors*);
2. sa **household account holder** (yung email na nasa Households), para may kopya rin sila. Ito ay kahit walang email ang visitor.

Kasama sa email ang QR picture (sa SMTP: nakalagay sa mismong email at naka-attach din bilang `.png`; sa EmailJS: lumalabas via `{{qr_url}}` ng template) at ang text code `VISTA:...` kung sakaling hindi mag-load ang picture.

## Bakit dati walang na-send
Walang email na naka-set up. Sa laptop, walang nagbabasa ng email settings, kaya **walang naipapadala kahit approved na**. Ang approval lang ang nakikita sa Messages page. Ngayon, may SMTP na gumagana sa laptop (Gmail ang pinakamadali) at may babala sa log kapag walang email setup.

> **Sa hosting (Render), EmailJS ang gamitin, hindi Gmail/SMTP** (hinaharang ng Render free ang SMTP). Tingnan ang HOSTING.md step 3. Ang Gmail setup sa ibaba ay para sa laptop lang.

## Gmail setup (5 minuto, laptop)
1. Sa Google Account mo, i-on ang **2-Step Verification**.
2. Pumunta sa https://myaccount.google.com/apppasswords at gumawa ng **App Password** (16 letters). Hindi ito ang normal mong password.
3. Buksan ang `backend/.env` at ilagay:
   ```
   SMTP_USER=iyong.email@gmail.com
   SMTP_PASSWORD=abcd efgh ijkl mnop
   ```
4. I-restart ang API (isara ang "Vista API" window, patakbuhin ulit ang `start-nodocker.bat`).
5. I-test:
   ```
   cd backend
   .venv\Scripts\python mailtest.py iyong.email@gmail.com
   ```
   Kung **SENT** ang lumabas at may QR picture sa inbox (tingnan din ang Spam), gumagana na.

Pwede rin ang ibang provider (Outlook, atbp.): palitan ang `SMTP_HOST`, `SMTP_PORT` at `SMTP_SECURITY` (`starttls` para sa 587, `ssl` para sa 465).

## Sa Render (published): EmailJS
Sundin ang HOSTING.md step 3. Ilagay ang `EMAILJS_SERVICE_ID`, `EMAILJS_TEMPLATE_ID`, `EMAILJS_PUBLIC_KEY` at `EMAILJS_PRIVATE_KEY` bilang Environment variables sa Render. Sa template, gamitin ang `{{to_email}}`, `{{subject}}`, `{{message}}`, `{{qr_code}}` at `<img src="{{qr_url}}">`. Ang `PUBLIC_API_URL` ay kusang kinukuha mula sa Render. Ang EmailJS ang inuuna kapag naka-set; ang SMTP ay fallback para sa laptop.

## Kung wala pa rin
- Tingnan ang window ng API: `EMAIL NOT SENT to ...` ang lalabas kasama ang dahilan, o `Email ... NOT sent: no email is set up`.
- Sa Render: siguraduhing kumpleto ang apat na `EMAILJS_*` at naka-on ang **Allow EmailJS API for non-browser applications** sa EmailJS. Sa laptop: siguraduhing may laman ang `SMTP_USER` at `SMTP_PASSWORD` sa `backend/.env`.
- Ang visitor ay dapat naglagay ng Email sa form para makatanggap siya. Ang household ay laging may email (required sa household form).
