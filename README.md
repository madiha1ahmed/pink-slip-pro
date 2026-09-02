# Al-Mahdi Hub — full update (fixes + Certificates module)

## ⚠️ First, the three errors in your log — and the fixes

1. **`/static/css/style.css` 404 (why the page looked unstyled).**
   The stylesheet wasn't in your `static/css/` folder, so no CSS loaded at all — that raw-HTML
   look is the 404, not the design. **Fix:** this package includes `static/css/style.css`; make
   sure it lands at `completed/static/css/style.css`.

2. **`TemplateNotFound: pinkslip_home.html`.**
   Not all new templates were copied in. **Fix:** this package's `templates/` has every template.

3. **`no such column: teacher.homeroom_grades`.**
   Your local database has the old schema. `db.create_all()` never alters existing tables.
   **Fix:** run the included, non-destructive upgrade once:
   ```
   python upgrade_db.py
   ```
   It adds the missing columns and creates the new tables without touching your data.

## How to apply
Extract this folder **into** your `8-3-project-deployment/completed/` folder, overwriting the
same-named files. Do NOT delete your data files (slip_data.db, xlsx, migrations). Then:
```
python upgrade_db.py        # one-time schema top-up
flask run
```
Hard-refresh the browser (Cmd/Ctrl+Shift+R) so the new CSS loads.

## NEW — Certificates module (achievements students collect)
Four dated e-certificates, emailed as PDFs to the student + parents, and tracked so you can see
who's collecting them (leaderboard at `/certificates`):

| Type | Rule |
|------|------|
| Perfect Attendance | No **Absent** slips in a calendar month |
| No Pink Slips | No **Pink** slips in a calendar month (checks live + archived) |
| Punctuality Star | No **Late** slip across the last 10 school days (Mon–Fri) |
| Attendance Star | No **Absent** slip across the last 10 school days |

- **Your blank PDFs:** drop four files into `static/certificates/` named
  `perfect_attendance.pdf`, `no_pink_slips.pdf`, `no_late_streak.pdf`, `no_absent_streak.pdf`.
  The app stamps the student **name** (centered) and **date** onto page 1. If a file is missing,
  it generates a clean certificate from scratch (see `previews/sample-certificate.png`), so it
  never breaks. Fine-tune text position with the `CERT_LAYOUT` env var (see certificates/README.txt).
- **When they're issued:** monthly certs are evaluated on the 1st (for the month just ended);
  streak certs are checked daily. Both run inside `/tasks/run-daily`. You can also click
  **Run check now** on the Certificates page any time. Issuing is idempotent (no duplicates).
- **Data saved:** every certificate is a row in `e_certificate` (student, type, period, date),
  ready for a future "10 certificates → gift coupon" rule.

## Daily scheduler (unchanged endpoint, now also does certificates)
`GET /tasks/run-daily?token=CRON_TOKEN` → yellow-slip reminders + SOTM form reminders + certificates.
Point one daily job at it (Render Cron $1/mo, or free GitHub Actions / UptimeRobot).

## Dependencies
Add to requirements.txt (see requirements-additions.txt): `psycopg2-binary`, `pypdf`.
(`reportlab` is already present.)

## Suite name
`SUITE_NAME` env var (default "Al-Mahdi Hub") renames the whole product in one place.

## Verified by
Python compile, Jinja parse of all 23 templates, url_for resolution, unit tests of the eligibility
+ school-day-window logic, and an actual generated sample certificate PDF. Email/Twilio/Postgres
aren't exercised in the build sandbox, so run `upgrade_db.py` and a quick local smoke test before deploy.

## Definitions to confirm with the principal
- "Perfect Attendance" = zero absences that month (lateness handled by the separate Punctuality Star).
- "10 school days" = 10 consecutive weekdays (Mon–Fri); holidays aren't excluded yet — tell me your
  school calendar and I can skip PA days.
- Streak certs are awarded at most once per 10-school-day window so students keep collecting them.
