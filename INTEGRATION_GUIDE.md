# PinkSlip Pro — Upgrade Guide

A gift for Al-Mahdi Learning Institute. This package adds three things to your existing app:

1. **A branded, redesigned frontend** (the "paper slip" identity).
2. **Teacher self-registration** — no more hard-coded teacher list.
3. **SMS / WhatsApp notifications** to parents, alongside email.

Nothing about your slip logic, archiving, insights, evaluations, or AI reports changed.

---

## 0. Before anything: rotate your secrets ⚠️

Your old `.env` (and a few source files) contained **live** credentials. Anyone with the
zip can use them. Regenerate all of these, then put the new values in a fresh `.env`:

- OpenAI API key
- Twilio Account SID + Auth Token
- Gmail App Password
- Flask `SECRET_KEY`
- Postgres database password (in `DATABASE_URL`)

The new code reads every secret from environment variables — see `.env.example`.
Also delete `whatsapp_test.py` (it has hard-coded credentials and is no longer used).

---

## 1. What to drop in

Copy these over your existing project (back up first). **Important:** copy the *whole*
`templates/` folder from this package — it contains all your original pages plus the new
ones. (Last time only the redesigned templates were included, which is why `archive.html`
went missing and the page 500'd.)

```
app.py                         ← replaces yours
requirements.txt               ← replaces yours (Twilio removed)
static/css/almahdi.css         ← new design system
templates/                     ← COMPLETE folder — all pages, redesigned + originals
seed_teachers.py               ← new (one-time)
.env.example                   ← reference for your .env
```

The `templates/` folder now includes every page: base, index, login, register, dashboard,
form, and archive are redesigned; insights, evaluate, evaluate_students, view_evaluations,
generate_report, and ai_report are your originals (they inherit the new look automatically
because they extend `base.html`).

`static/images/al-mahdi-logo.jpeg` is already in your project and is used in the header.

## 2. Create the Teacher table

The app creates the new `Teacher` table automatically on first run (`db.create_all()`).
On a fresh Postgres you can also use your existing Flask-Migrate setup:

```bash
flask db migrate -m "add Teacher table"
flask db upgrade
```

## 3. Get your current teachers in (one-time)

So existing staff aren't locked out:

```bash
python seed_teachers.py
```

Everyone gets the temporary password `12AlMahdi!` — ask them to re-register or change it.
(Or skip this entirely and have all teachers self-register at `/register`.)

## 4. Run it

```bash
pip install -r requirements.txt
flask run          # or: gunicorn app:app
```

Visit `/register` to make an account, then `/login`.

---

## Notifications: SMS, no Twilio

You asked for **SMS only, without Twilio**. Done — Twilio is fully removed from the code
and dependencies. Set `NOTIFY_CHANNEL='email_sms'` to turn SMS on (or `'email'` for email only).

Pick a provider with `SMS_PROVIDER`:

- **`clicksend`** (default) — the easiest option. It's a plain HTTPS request, so there's
  **nothing extra to install** (it uses `requests`, which you already have). Sign up at
  clicksend.com, grab your username + API key, put them in `.env`, done.
- **`plivo`** — a clean, Twilio-style API with a Python SDK and good Canada pricing. If you
  choose this, also run `pip install plivo` (uncomment it in `requirements.txt`) and set
  `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, and `SMS_FROM` (your Plivo number).

The parent's mobile number is read from the existing `parent_whatsapp` field on each Student
(despite the name, it now just holds the mobile number for SMS). Store it in +E.164 form,
e.g. `+19055551234`.

**One honest heads-up about Canadian SMS.** Sending app-to-person texts to Canadian mobiles
requires carrier-level sender registration (A2P / 10DLC for local numbers, or a verified
toll-free number). That's a *carrier* rule — it applies no matter which provider you use, so
switching away from Twilio doesn't remove it. ClickSend and Plivo both walk you through it;
budget a few days for approval before go-live. For quick testing you can usually send to your
own verified number right away.

### A note on why Twilio was swapped out
For the record, Twilio is a US company (HQ San Francisco, NYSE: TWLO) with engineering offices
mainly in India and Europe — it isn't Israeli. But you wanted off it, so it's gone either way,
and the SMS code is now a single swappable function (`send_sms_message`) if you ever want a
different provider.

---

## Notes / things I flagged

- **Archive timing:** your workflow diagram says slips archive after *1 month*, but the code
  uses `timedelta(days=60)` (2 months) in `archive_expired_pink_slips()`. Change that one line
  if you want it to match the diagram.
- **Grades JK/SK:** registration now offers JK–8. Student records only store integer grades,
  so JK/SK subjects register fine but won't pull a student roster until you add JK/SK students.
- **Two `create_tables` functions** existed in the original file; I left them as-is (harmless,
  `create_all` is idempotent) to avoid touching unrelated code.
- I fixed a latent bug in `convert_yellow_to_pink` (a missing comma + a bad WhatsApp call that
  would have raised an error on the "under 3 slips" path).

Jazakumullahu khair — I hope the teachers love it. 💗
