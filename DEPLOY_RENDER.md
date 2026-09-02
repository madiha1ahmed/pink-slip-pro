# Deploying PinkSlip Pro to Render — step by step

Time needed: ~30–40 minutes. You'll create a PostgreSQL database and a web service,
set your secrets, seed the teachers, and add a daily cron job.

---

## 0. Before you start — rotate your secrets (again, seriously)

The keys that were in your old `.env` are compromised (they were shared in zips). Regenerate:
- **Gmail App Password** (Google Account → Security → App passwords)
- **OpenAI API key**
- **ClickSend** username + API key (Dashboard → API credentials)
- You do **not** need Twilio anymore.

You'll paste the fresh values into Render, not into any file.

---

## 1. Put the code on GitHub

Render deploys from a Git repo. From your `completed` folder:

```bash
# make sure secrets are NOT committed
echo ".env" >> .gitignore
echo "slip_data.db" >> .gitignore
echo "venv/" >> .gitignore
echo "__pycache__/" >> .gitignore

git init
git add .
git commit -m "PinkSlip Pro — ready for Render"
```

Create a new empty repo on GitHub (e.g. `pinkslip-pro`), then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/pinkslip-pro.git
git branch -M main
git push -u origin main
```

**Double-check** on GitHub that `.env` and `slip_data.db` are NOT there.

---

## 2. Create the PostgreSQL database

1. Log in at **dashboard.render.com** → **New +** → **Postgres**.
2. Name: `pinkslip-db`. Region: **Ohio** (closest to Niagara Falls).
3. Plan: **Basic-256mb (~$6/mo)**. Create it.
4. When it's ready, open it and copy the **Internal Database URL**
   (starts with `postgresql://…`, host ends in `…-a`). You'll use this in step 3.
   *Internal* is correct because your web service runs inside Render's network.

---

## 3. Create the web service

1. **New +** → **Web Service** → connect your GitHub repo.
2. Settings:
   - **Region:** Ohio (same as the database — this matters).
   - **Runtime:** Python 3 (it reads `runtime.txt` → 3.9.18).
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 2`
   - **Plan:** **Starter ($7/mo)**.
3. Under **Environment**, add these variables (Add Environment Variable for each):

   | Key | Value |
   |-----|-------|
   | `DATABASE_URL` | *(paste the Internal Database URL from step 2)* |
   | `SECRET_KEY` | *(a long random string — Render can generate one)* |
   | `TASK_KEY` | *(another long random string; you'll reuse it in step 6)* |
   | `MAIL_USERNAME` | your Gmail address |
   | `MAIL_PASSWORD` | your Gmail **App Password** |
   | `NOTIFY_CHANNEL` | `email_sms` |
   | `SMS_PROVIDER` | `clicksend` |
   | `SMS_FROM` | your sender number, e.g. `+1XXXXXXXXXX` |
   | `CLICKSEND_USERNAME` | your ClickSend username |
   | `CLICKSEND_API_KEY` | your ClickSend API key |
   | `OPENAI_API_KEY` | your new OpenAI key |
   | `PRINCIPAL_EMAIL` | principal@almahdilearninginstitute.ca |
   | `VICE_PRINCIPAL_EMAIL` | malasam@almahdilearninginstitute.ca |
   | `SECRETARY_EMAIL` | secretary@almahdilearninginstitute.ca |

4. Click **Create Web Service**. Render builds and starts it. First build takes a few minutes.

When it goes live, the app auto-creates all the database tables on the first request
(`create_all()` runs against your fresh Postgres). Visit the URL — the home page should load.

> **Tip:** watch the **Logs** tab during the first deploy. "Running on … / Booting worker"
> means gunicorn started. A crash usually means a missing env var — the log names which one.

---

## 4. Seed the teachers (one time)

So staff aren't locked out on day one:

1. Open your web service → **Shell** tab.
2. Run:
   ```bash
   python seed_teachers.py
   ```
   This loads your original staff into the new database. (Or skip it and have everyone
   self-register at `/register`.)

Then have each teacher log in and confirm their profile, and add their **mobile number**
(re-register, or we can add an "edit profile" screen later) so SMS reminders reach them.

---

## 5. Point your school domain (optional, later)

If you want `slips.almahdilearninginstitute.ca` instead of the `onrender.com` URL:
Web service → **Settings** → **Custom Domains** → add it, then create the CNAME record
Render shows you at your domain registrar. Render handles the HTTPS certificate automatically.

---

## 6. Set up the daily reminders (cron)

The yellow-slip "due today" and Student-of-the-Month reminders need a nudge once a day.
Pick **one** option:

**Option A — free external cron (simplest):**
1. Go to **cron-job.org**, make a free account.
2. Create a job that runs **daily at 7:00 AM (America/Toronto)** and calls:
   ```
   https://YOUR-APP.onrender.com/tasks/daily?key=YOUR_TASK_KEY
   ```
   (use the exact `TASK_KEY` you set in step 3).

**Option B — Render Cron Job:**
Render → **New +** → **Cron Job**, schedule `0 12 * * *` (12:00 UTC ≈ 7–8 AM Toronto),
command:
```bash
curl -s "https://YOUR-APP.onrender.com/tasks/daily?key=YOUR_TASK_KEY"
```
(Render Cron Jobs are billed separately by runtime; Option A is free and fine for this.)

To verify it works, paste the URL in your browser once — you should get a small JSON
summary like `{"yellow_due_notified": 0, "som_reminders_sent": 0, ...}`.

---

## 7. Future updates (this ends the "wipe the database" pain)

- **New code / bug fixes:** just `git push`. Render auto-deploys.
- **New tables** (e.g. the upcoming certificates table): handled automatically —
  `create_all()` adds missing tables on deploy, no data loss.
- **New columns on existing tables** (the thing that kept biting you locally): these need a
  migration, NOT a wipe. In the certificate batch I'll wire up Flask-Migrate so it's a one-time:
  ```bash
  # in the Render Shell, only when a column is added:
  flask db upgrade
  ```
  which alters the table in place and keeps every row. I'll give you the exact commands then.

**Never run `reset_db.py all` or delete data on the production database** — that's only for
your local SQLite testing.

---

## Quick troubleshooting

- **502 / app won't boot:** check Logs. Almost always a missing/misspelled env var, or the
  start command. It must be `gunicorn app:app …` (the file is `app.py`, the Flask object is `app`).
- **"could not translate host name …-a":** you used the database's *external* URL from your
  laptop, or the web service and DB are in different regions. Use the **Internal** URL and keep
  both in Ohio.
- **Emails not sending:** Gmail needs an **App Password** (not your login password), and
  `MAIL_USERNAME` must be the same Gmail address.
- **SMS not sending:** confirm ClickSend credentials and that Canadian sender registration is
  approved; test to your own number first.
- **Slow first load after idle:** the Starter plan may sleep when idle and take ~30s to wake.
  The daily cron ping also keeps it warm around that time.
