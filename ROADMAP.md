# PinkSlip Pro → Al-Mahdi School Management System — Roadmap

You asked for five big things. To protect the app the staff already love (and that the
principal is about to pay to host), I'm building this in **tested increments** rather than one
giant untested drop. Here's exactly where things stand.

---

## ✅ DELIVERED & TESTED in this batch

### 1. Unified home page (`/`)
A branded hub for the whole system with real Al-Mahdi information (Niagara Falls, JK–8,
Tarbiyah curriculum, est. 2019) and cards for each section: **PinkSlip Pro** (live),
**Attendance** (coming), **Student of the Month** (live), **e-Certificates** (coming).

### 2. Yellow-slip reschedule + due-date reminders
- The assign-slip form now shows a **"Rescheduled due date"** field when you pick *Yellow Slip*.
- On that date, the assigning teacher gets a reminder — **on the dashboard (bell), by email, and by SMS** —
  saying the student's homework is due today and to check it.
- No duplicate reminders (each slip is only reminded once).

### 3. Notification bell + notifications page
- A 🔔 bell in the top bar shows an unread count and a dropdown of recent alerts.
- A full `/notifications` page lists everything with mark-as-read.

### 4. Automated Student-of-the-Month reminders
Runs on a schedule (configurable in `.env`):
- **23rd** – heads-up to **all** teachers that forms are open.
- **25th** – "due today" to teachers who **haven't submitted**.
- **26th** – "past due" to those still outstanding.
- **27th** – final notice, **CC the vice-principal** (`malasam@almahdilearninginstitute.ca`).
Each reminder is email + SMS + dashboard bell.

### 5. "Student of the Month" section
Evaluations moved out of PinkSlip Pro into their own section at `/student-of-the-month`
(links to fill-in and view-evaluations).

---

## ⚙️ How the daily jobs run (important for deployment)

Time-based jobs (yellow-slip due dates, SoM reminders) need something to "wake up" once a day.
Two layers are built in:

1. **Opportunistic** — whenever a teacher opens the home page, the day's jobs run once (guarded
   so they only fire a single time per day). This means it works even with zero extra setup.
2. **Reliable (recommended for production)** — a cron job hits a protected URL once a day:
   ```
   GET https://your-app.onrender.com/tasks/daily?key=YOUR_TASK_KEY
   ```
   On Render: add a **Cron Job** service (or use a free external pinger like cron-job.org) set to
   run daily at ~7:00 AM, pointing at that URL. Set `TASK_KEY` in `.env` to a long random string
   and use the same value in the cron URL.

---

## 🔜 NEXT — designed, not yet built

### A. Attendance (Late slips + Absent slips) — ✅ NOW BUILT
- New `AttendanceSlip` model (Late / Absent).
- Homeroom teachers record daily attendance from a class roster at `/attendance`
  (Present / Late / Absent per student, optional note, date picker).
- Parents are notified by email + SMS on any late/absent slip.
- Insights at `/attendance/insights` mirror PinkSlip Pro (stat tiles, late-vs-absent
  doughnut, monthly trend, per-student stacked bars) and a full log at `/attendance/log`.

### B. e-Certificates — still needs your blank PDF
Auto-generated PDF awards, four types, each **dated**:
1. Perfect attendance (month)
2. No pink slips (month)
3. Not late for 10 days in a row
4. Not absent for 10 days in a row
- Emailed as PDF to the **student and parents**.
- A `Certificate` table records every award so you can count how many each student collects
  (for the future "10 certificates → reward" idea).

**I need one thing from you to build this:** the **blank certificate PDF** (ideally one design;
I can recolor/label the four types from it, or you can send four). Tell me roughly where the
student's **name** and the **date** should sit, and I'll auto-fill them onto your template.
Certificate generation depends on the Attendance module (A) for the late/absent streaks, so the
natural order is: **A → B**.

---

## 🚀 Deployment (Render) — for the end, as you said
- Web service: **Starter $7/mo**; PostgreSQL: **$6/mo** — good choices for this size.
- We'll set all secrets as Render **Environment Variables** (never in code), point
  `DATABASE_URL` at the Render Postgres **internal** URL, add the daily **Cron Job**, and
  run `seed_teachers.py` once. I'll give you a step-by-step when we get there.

---

### Suggested order from here
1. **e-Certificates** (once you send the blank PDF) — builds on the attendance streaks now available.
2. **Deploy to Render** with cron + seeded teachers.

Tell me which you'd like next, and send the certificate PDF whenever it's handy.

---

## ⚠️ After installing this batch: rebuild your local database

This batch adds columns (`teacher.phone`) and a new table (`attendance_slip`), plus the earlier
`reschedule_*` columns. Because `db.create_all()` won't alter existing tables, rebuild your
**local test** database once:

```
rm slip_data.db      # (or: python reset_db.py all)
flask run            # recreates all tables fresh
python populate_students.py
python populate_subjects.py
```

Then register again (you'll now be asked for a mobile number). On **production** you'll use
`flask db migrate` + `flask db upgrade` instead — never wipe live data. I'll set that up at deploy.
