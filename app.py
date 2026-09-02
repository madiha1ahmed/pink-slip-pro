import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from forms import HealthDataForm
from flask_migrate import Migrate
from flask import jsonify
from flask_mail import Mail, Message
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from datetime import datetime, timedelta, date
from openai import OpenAI
from flask import Markup
import re
import markdown2
import csv
import json
from io import StringIO
import requests
# SMS provider SDK (Plivo) is imported lazily inside send_sms_message so the app
# still runs if you choose the ClickSend HTTP option and never install plivo.



PRINCIPAL_EMAIL = os.getenv("PRINCIPAL_EMAIL")       # e.g. principal@school.org
PRINCIPAL_WHATSAPP = os.getenv("PRINCIPAL_WHATSAPP") # e.g. 14165550123 (no +)
#WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
#WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

SECRETARY_EMAIL   = os.getenv("SECRETARY_EMAIL")
SENDER_BCC_EMAIL  = os.getenv("SENDER_BCC_EMAIL") or os.getenv("MAIL_USERNAME")
VICE_PRINCIPAL_EMAIL = os.getenv("VICE_PRINCIPAL_EMAIL", "malasam@almahdilearninginstitute.ca")

# Secret token that protects the daily-tasks endpoint (set this in .env and in your cron job)
TASK_KEY = os.getenv("TASK_KEY", "change-me")

# Student-of-the-Month reminder schedule (days of the month).
# 23rd: heads-up to ALL teachers · 25th: "due today" to those who haven't submitted
# 26th: "past due" · 27th: "past due" + CC the vice-principal
SOM_REMIND_ALL_DAY      = int(os.getenv("SOM_REMIND_ALL_DAY", 23))
SOM_DUE_TODAY_DAY       = int(os.getenv("SOM_DUE_TODAY_DAY", 25))
SOM_PAST_DUE_DAY        = int(os.getenv("SOM_PAST_DUE_DAY", 26))
SOM_PAST_DUE_VP_DAY     = int(os.getenv("SOM_PAST_DUE_VP_DAY", 27))


account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token=os.getenv("TWILIO_AUTH_TOKEN")

# --- SMS configuration (Twilio-free) ---
# SMS_PROVIDER: "clicksend" (HTTP only, no extra install) or "plivo" (pip install plivo)
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "clicksend").lower()
SMS_FROM     = os.getenv("SMS_FROM")   # your sender number/ID, e.g. +12495551234

# ClickSend
CLICKSEND_USERNAME = os.getenv("CLICKSEND_USERNAME")
CLICKSEND_API_KEY  = os.getenv("CLICKSEND_API_KEY")

# Plivo
PLIVO_AUTH_ID    = os.getenv("PLIVO_AUTH_ID")
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN")


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


MONTHS = [
    'September', 'October', 'November', 'December',
    'January', 'February', 'March', 'April', 'May', 'June'
]
YEARS = [2025, 2026]

app = Flask(__name__)

# DB config (replace your current line)
db_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "sqlite:///slip_data.db"

# SQLAlchemy needs 'postgresql://' not 'postgres://'
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_secret_key')

# (Removed a duplicate line here that overrode the database with POSTGRES_URL/sqlite.
#  db_url above already handles DATABASE_URL, POSTGRES_URL, and the sqlite fallback.)

@app.before_first_request
def create_tables():
    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("Database URL not configured")
    db.create_all()


# Email configuration
# Email configuration for Gmail
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')  # from .env — never hard-code
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')  # Gmail App Password, from .env

# How parents are notified for a slip: "email" or "email_sms"
NOTIFY_CHANNEL   = os.getenv('NOTIFY_CHANNEL', 'email')

app.config['ENV'] = 'production'
app.config['DEBUG'] = False
app.config['SESSION_COOKIE_SECURE'] = True
app.config['REMEMBER_COOKIE_SECURE'] = True


mail = Mail(app)

# NOTE: Teachers are now stored in the database (see Teacher model below) and
# register themselves via /register. The old hard-coded 'teachers' dict was removed.
# get_teachers() rebuilds the same {email: {...}} shape the rest of the app expects.

#bcrypt = Bcrypt(app)

db = SQLAlchemy(app)
#db1 = SQLAlchemy(app)
migrate = Migrate(app, db)


class Teacher(db.Model):
    """A registered teacher. Replaces the old hard-coded `teachers` dict."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(30), nullable=True)   # +E.164 mobile for staff SMS
    # Stored as JSON text so it works on both SQLite and Postgres:
    homeroom_grades_json = db.Column(db.Text, default="[]")   # e.g. "[5]" or "[4,5]"
    grades_json = db.Column(db.Text, default="{}")            # e.g. "{\"5\": [\"Math\"]}"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_info(self):
        """Return the same dict shape the rest of the app expects."""
        try:
            homeroom = json.loads(self.homeroom_grades_json or "[]")
        except Exception:
            homeroom = []
        try:
            raw_grades = json.loads(self.grades_json or "{}")
        except Exception:
            raw_grades = {}
        # Grades are categorical (JK, SK, 1..8) — keep everything as strings so
        # they compare cleanly against Student.grade (also a string column).
        homeroom = [str(g) for g in homeroom]
        grades = {str(k): v for k, v in raw_grades.items()}
        return {
            "password": self.password_hash,
            "name": self.name,
            "phone": self.phone,
            "homeroom_grade": homeroom,
            "grades": grades,
        }


def get_teachers():
    """Rebuild the {email: {...}} mapping from the database on demand."""
    return {t.email: t.to_info() for t in Teacher.query.all()}

class HealthData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    slip_type = db.Column(db.String, nullable=False)
    student_name = db.Column(db.String, nullable=False)
    grade_of_student = db.Column(db.String(10), nullable=False)
    subject_of_student = db.Column(db.String, nullable=False)
    homework_desc = db.Column(db.String, nullable=False)
    teacher_email = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Add this field
    # For Yellow Slips: the new date the student must show the homework by.
    reschedule_date = db.Column(db.Date, nullable=True)
    # Set True once the teacher has been reminded on the reschedule date (prevents duplicate reminders).
    reschedule_notified = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<HealthData {self.id}>'

    
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.String(10), nullable=False)          # "JK","SK","1"..."8"
    parent_email_mom = db.Column(db.String(150), nullable=True)
    parent_email_dad = db.Column(db.String(150), nullable=True)
    parent_whatsapp_dad = db.Column(db.String(30), nullable=True)   # father's mobile
    parent_whatsapp_mom = db.Column(db.String(30), nullable=True)   # mother's mobile
    student_email = db.Column(db.String(150), nullable=True)

    @property
    def parent_emails(self):
        """All parent emails on file (0, 1, or 2)."""
        return [e.strip() for e in [self.parent_email_mom, self.parent_email_dad]
                if e and str(e).strip()]

    @property
    def parent_phones(self):
        """All parent mobiles on file, normalized to +E.164 (0, 1, or 2)."""
        nums = []
        for raw in [self.parent_whatsapp_mom, self.parent_whatsapp_dad]:
            n = normalize_na_phone(raw)
            if n and n not in nums:
                nums.append(n)
        return nums

    @property
    def parent_whatsapp(self):
        """Backward-compatible single number: first available parent mobile."""
        phones = self.parent_phones
        return phones[0] if phones else None

    @property
    def has_any_contact(self):
        return bool(self.parent_emails or self.parent_phones)

    def __repr__(self):
        return f"<Student {self.name} (Grade {self.grade})>"


    

    
class ArchiveData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    slip_type = db.Column(db.String, nullable=False)
    student_name = db.Column(db.String, nullable=False)
    grade_of_student = db.Column(db.String(10), nullable=False)
    subject_of_student = db.Column(db.String, nullable=False)
    homework_desc = db.Column(db.String, nullable=False)
    teacher_email = db.Column(db.String, nullable=False)  # Required for filtering

class StudentEvaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_email = db.Column(db.String, nullable=False)
    student_name = db.Column(db.String, nullable=False)
    grade = db.Column(db.String(10), nullable=False)
    month = db.Column(db.String, nullable=False)  # e.g., "September"
    year = db.Column(db.Integer, nullable=False)  # e.g., 2025

    responsibility = db.Column(db.Integer)
    self_regulation = db.Column(db.Integer)
    organization = db.Column(db.Integer)
    collaboration_initiative = db.Column(db.Integer)
    independent_work = db.Column(db.Integer)
    remarks = db.Column(db.String)
    average_score = db.Column(db.Float)
    is_submitted = db.Column(db.Boolean, default=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


    def __repr__(self):
        return f'<ArchiveData {self.id}>'


class Notification(db.Model):
    """In-app notifications shown via the bell icon on the dashboard."""
    id = db.Column(db.Integer, primary_key=True)
    teacher_email = db.Column(db.String, nullable=False, index=True)
    message = db.Column(db.String, nullable=False)
    category = db.Column(db.String, default="info")   # info | yellow_due | som_reminder
    link = db.Column(db.String, nullable=True)         # optional URL to jump to
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AttendanceSlip(db.Model):
    """A late arrival or absence recorded by a homeroom teacher."""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    slip_type = db.Column(db.String, nullable=False)     # "Late" | "Absent"
    student_name = db.Column(db.String, nullable=False, index=True)
    grade = db.Column(db.String(10), nullable=False)
    note = db.Column(db.String, nullable=True)           # optional reason
    recorded_by = db.Column(db.String, nullable=False)   # teacher email
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def add_notification(teacher_email, message, category="info", link=None):
    """Create an in-app notification (deduped against an identical unread one)."""
    if not teacher_email:
        return
    existing = Notification.query.filter_by(
        teacher_email=teacher_email, message=message, is_read=False
    ).first()
    if existing:
        return
    db.session.add(Notification(
        teacher_email=teacher_email, message=message, category=category, link=link
    ))
    db.session.commit()


def check_three_pink_slips(student_name):
    try:
        slips = HealthData.query.filter_by(student_name=student_name, slip_type="Pink Slip").order_by(HealthData.date).all()
        student = Student.query.filter_by(name=student_name).first()

        if not student:
            print(f"⚠️ No student record found for {student_name}")
            return

        # We now send to whoever is reachable. Only skip entirely if there is
        # NO email and NO phone anywhere on file for this student.
        if not student.has_any_contact:
            print(f"⚠️ No contact info (email or phone) on file for {student_name} — notification skipped.")
            return

        parent_email_mom = student.parent_email_mom
        parent_email_dad = student.parent_email_dad
        print(f"📧 Preparing notification for {student_name} — Total Pink Slips: {len(slips)} "
              f"(emails: {len(student.parent_emails)}, phones: {len(student.parent_phones)})")

        if len(slips) == 1:
            send_email_to_parent(student_name, parent_email_mom, parent_email_dad, [slips[0]])
        elif len(slips) == 2:
            send_email_to_parent(student_name, parent_email_mom, parent_email_dad, [slips[1]])
        elif len(slips) == 3:
            send_email_to_parent(student_name, parent_email_mom, parent_email_dad, slips, is_final=True)
            for slip in slips:
                archive_entry(slip.id)
    except Exception as e:
        print(f"❌ Error in check_three_pink_slips: {e}")


def _normalize_e164(number):
    """Return a clean +E.164 number (strips quotes/spaces and any leftover prefix)."""
    if not number:
        return None
    n = str(number).replace("whatsapp:", "").strip().strip('"').strip("'").strip()
    return n or None


def normalize_na_phone(raw):
    """Turn messy North-American numbers into +E.164.

    Handles blanks/NaN and formats like '(416)839-9850', '647 708 4808',
    '4168399850', '+1 416 839 9850', '1-416-839-9850'.  Returns None if there
    aren't enough digits to be a real number.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    if s.startswith("+"):
        digits = "".join(ch for ch in s if ch.isdigit())
        return "+" + digits if len(digits) >= 10 else None
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    if len(digits) >= 11:          # already has a country code
        return "+" + digits
    return None                    # too short to be valid


def _send_sms_clicksend(to_number, message_body):
    """Send SMS via ClickSend — HTTP only, no SDK to install (uses `requests`)."""
    if not CLICKSEND_USERNAME or not CLICKSEND_API_KEY:
        print("❌ ClickSend credentials missing. SMS not sent.")
        return
    payload = {"messages": [{
        "source": "python",
        "body": message_body,
        "to": to_number,
        **({"from": SMS_FROM} if SMS_FROM else {}),
    }]}
    try:
        r = requests.post(
            "https://rest.clicksend.com/v3/sms/send",
            auth=(CLICKSEND_USERNAME, CLICKSEND_API_KEY),
            json=payload,
            timeout=15,
        )
        if r.status_code == 200:
            print(f"📤 SMS (ClickSend) sent to {to_number}")
        else:
            print(f"❌ ClickSend error {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"❌ Error sending SMS via ClickSend: {e}")


def _send_sms_plivo(to_number, message_body):
    """Send SMS via Plivo — requires `pip install plivo` and a Plivo number in SMS_FROM."""
    if not PLIVO_AUTH_ID or not PLIVO_AUTH_TOKEN or not SMS_FROM:
        print("❌ Plivo credentials or SMS_FROM missing. SMS not sent.")
        return
    try:
        import plivo  # lazy import so the app runs without plivo installed
        client = plivo.RestClient(PLIVO_AUTH_ID, PLIVO_AUTH_TOKEN)
        resp = client.messages.create(
            src=SMS_FROM,        # your Plivo number, e.g. +12495551234
            dst=to_number,       # +E.164
            text=message_body,
        )
        print(f"📤 SMS (Plivo) sent to {to_number} | {getattr(resp, 'message_uuid', '')}")
    except Exception as e:
        print(f"❌ Error sending SMS via Plivo: {e}")


def send_sms_message(to_number, message_body):
    """Send a plain-text SMS using whichever provider SMS_PROVIDER selects.

    SMS_PROVIDER = "clicksend" (default, HTTP only) or "plivo".
    Neither is Twilio.
    """
    to_number = _normalize_e164(to_number)
    if not to_number:
        print("⚠️ No mobile number provided; SMS skipped.")
        return
    if SMS_PROVIDER == "plivo":
        _send_sms_plivo(to_number, message_body)
    else:
        _send_sms_clicksend(to_number, message_body)


def notify_parent_channels(to_number, message_body):
    """Send the parent notification over the channels NOTIFY_CHANNEL enables.

    NOTIFY_CHANNEL values:
        "email"     -> SMS off (email is sent separately)
        "email_sms" -> also send SMS
    """
    if (NOTIFY_CHANNEL or "email").lower() == "email_sms":
        send_sms_message(to_number, message_body)


def send_attendance_notification(student, slip_type, on_date, note=None):
    """Email (+ SMS per NOTIFY_CHANNEL) the parents about a late/absent slip."""
    label = "late arrival" if slip_type == "Late" else "absence"
    subject = f"Attendance notice — {student.name} ({slip_type})"
    body = (
        f"Assalamu alaikum,\n\n"
        f"This is a notification from Al-Mahdi Learning Institute regarding {student.name} "
        f"(Grade {student.grade}).\n\n"
        f"A {label} was recorded on {on_date.strftime('%B %d, %Y')}."
        + (f"\nNote: {note}" if note else "")
        + "\n\nIf you believe this is in error, please contact the school office.\n\n"
        f"Jazakumullahu khair,\nAl-Mahdi Learning Institute"
    )
    recipients = student.parent_emails
    phones = student.parent_phones
    if not recipients and not phones:
        print(f"⚠️ No contact info for {student.name}; attendance notice not sent.")
        return
    if recipients:
        send_email(subject, recipients, body, cc=None)
    sms_text = (f"Al-Mahdi: {student.name} was marked {slip_type.lower()} on "
                f"{on_date.strftime('%b %d, %Y')}." + (f" Note: {note}" if note else ""))
    for ph in phones:
        notify_parent_channels(ph, sms_text)


def send_email(subject, recipients, body, cc=None):
    """Generic email sender (used for teacher/staff notifications)."""
    if isinstance(recipients, str):
        recipients = [recipients]
    recipients = [r for r in (recipients or []) if r]
    if not recipients:
        print(f"⚠️ send_email: no recipients for '{subject}'")
        return
    try:
        msg = Message(subject=subject, recipients=recipients,
                      cc=[c for c in (cc or []) if c] or None,
                      sender=app.config.get('MAIL_USERNAME'))
        msg.body = body
        mail.send(msg)
        print(f"📧 Email sent: '{subject}' -> {recipients}")
    except Exception as e:
        print(f"❌ Error sending email '{subject}': {e}")


def notify_teacher(teacher_email, subject, body, category="info", link=None, cc=None, sms=True):
    """One call to reach a teacher: in-app bell + email + (optionally) SMS."""
    add_notification(teacher_email, subject, category=category, link=link)
    send_email(subject, teacher_email, body, cc=cc)
    if sms:
        teacher = Teacher.query.filter_by(email=teacher_email).first()
        # We only have teacher mobiles if you later add a phone field; SMS to staff
        # is skipped gracefully until then. Parent SMS is unaffected.
        phone = getattr(teacher, "phone", None) if teacher else None
        if phone:
            send_sms_message(phone, f"{subject}\n\n{body}")


# =====================================================================
#  DAILY TASKS  — run once a day (via /tasks/daily hit by a cron job,
#  and opportunistically when a teacher opens the dashboard).
# =====================================================================
_last_daily_run = {"date": None}

def _yellow_slips_due_today():
    """Remind the assigning teacher that a rescheduled (yellow-slip) homework is due today."""
    today = date.today()
    due = HealthData.query.filter(
        HealthData.slip_type == "Yellow Slip",
        HealthData.reschedule_date == today,
        (HealthData.reschedule_notified == False) | (HealthData.reschedule_notified.is_(None))
    ).all()
    for slip in due:
        subject = f"📌 Homework due today: {slip.student_name}"
        body = (
            f"Assalamu alaikum,\n\n"
            f"This is a reminder that {slip.student_name} (Grade {slip.grade_of_student}) "
            f"was given a yellow slip for {slip.subject_of_student} homework "
            f"(\"{slip.homework_desc}\") and rescheduled to show it today "
            f"({today.strftime('%B %d, %Y')}).\n\n"
            f"Please check whether the homework has been shown. If not, you can convert "
            f"the yellow slip to a pink slip from your dashboard.\n\n— PinkSlip Pro"
        )
        notify_teacher(slip.teacher_email, subject, body, category="yellow_due",
                       link="/dashboard", sms=True)
        slip.reschedule_notified = True
    if due:
        db.session.commit()
    return len(due)


def _som_teachers_not_submitted(month, year):
    """Teachers who have NOT submitted any Student-of-the-Month evaluation for month/year."""
    submitted = {
        row.teacher_email for row in StudentEvaluation.query
        .filter_by(month=month, year=year, is_submitted=True).all()
    }
    return [t for t in Teacher.query.all() if t.email not in submitted]


def _reminded_today(email, message):
    """True if this exact reminder was already sent to this teacher today (dedupe emails)."""
    start = datetime.combine(date.today(), datetime.min.time())
    return Notification.query.filter(
        Notification.teacher_email == email,
        Notification.message == message,
        Notification.created_at >= start
    ).first() is not None


def _current_som_period():
    """The month/year the reminders refer to (the current calendar month)."""
    today = date.today()
    return today.strftime("%B"), today.year


def _student_of_month_reminders():
    """Send the scheduled Student-of-the-Month reminders based on today's day number."""
    today = date.today()
    day = today.day
    month, year = _current_som_period()
    sent = 0

    if day == SOM_REMIND_ALL_DAY:
        subject = "📝 Student of the Month forms open"
        body = (f"Assalamu alaikum,\n\nA reminder that the Student of the Month evaluation "
                f"for {month} {year} is now open. Please complete it by the "
                f"{SOM_DUE_TODAY_DAY}th.\n\nJazakumullahu khair.\n— PinkSlip Pro")
        for t in Teacher.query.all():
            if _reminded_today(t.email, subject): continue
            notify_teacher(t.email, subject, body, category="som_reminder", link="/student-of-the-month")
            sent += 1

    elif day == SOM_DUE_TODAY_DAY:
        subject = "⏰ Student of the Month forms are due today"
        body = (f"Assalamu alaikum,\n\nThe Student of the Month evaluation for {month} {year} "
                f"is due today. Our records show you haven't submitted yet — please complete it.\n\n— PinkSlip Pro")
        for t in _som_teachers_not_submitted(month, year):
            if _reminded_today(t.email, subject): continue
            notify_teacher(t.email, subject, body, category="som_reminder", link="/student-of-the-month")
            sent += 1

    elif day == SOM_PAST_DUE_DAY:
        subject = "⚠️ Student of the Month forms are past due"
        body = (f"Assalamu alaikum,\n\nThe Student of the Month evaluation for {month} {year} "
                f"was due yesterday and is now past due. Please complete it as soon as possible.\n\n— PinkSlip Pro")
        for t in _som_teachers_not_submitted(month, year):
            if _reminded_today(t.email, subject): continue
            notify_teacher(t.email, subject, body, category="som_reminder", link="/student-of-the-month")
            sent += 1

    elif day == SOM_PAST_DUE_VP_DAY:
        subject = "🔴 Student of the Month forms still outstanding"
        body = (f"Assalamu alaikum,\n\nThe Student of the Month evaluation for {month} {year} "
                f"is still outstanding. The vice-principal has been copied on this reminder. "
                f"Please complete it today.\n\n— PinkSlip Pro")
        for t in _som_teachers_not_submitted(month, year):
            if _reminded_today(t.email, subject): continue
            notify_teacher(t.email, subject, body, category="som_reminder",
                           link="/student-of-the-month", cc=[VICE_PRINCIPAL_EMAIL])
            sent += 1

    return sent


def run_daily_tasks(force=False):
    """Run all scheduled daily jobs. Safe to call on every page load:
    - yellow-slip reminders are deduped per slip (reschedule_notified)
    - Student-of-the-Month reminders are deduped per teacher per day
    The `force` flag is kept for the cron endpoint but no longer gates anything,
    since each task is individually idempotent.
    """
    result = {
        "yellow_due_notified": _yellow_slips_due_today(),
        "som_reminders_sent": _student_of_month_reminders(),
        "date": date.today().isoformat(),
    }
    if result["yellow_due_notified"] or result["som_reminders_sent"]:
        print(f"🗓️  Daily tasks ran: {result}")
    return result



def send_email_to_parent(student_name, parent_email_mom, parent_email_dad, slips, is_final=False):
    try:
        slip_details = ""
        cc_set = set()

        student = Student.query.filter_by(name=student_name).first()
        for i, slip in enumerate(slips, start=1):
            slip_details += f"{i}️⃣ **Subject:** {slip.subject_of_student}\n"
            slip_details += f"   📅 Date: {slip.date.strftime('%Y-%m-%d')}\n"
            slip_details += f"   📖 Homework Details: {slip.homework_desc}\n\n"
            if slip.teacher_email:
                cc_set.add(slip.teacher_email)
            if student and student.student_email:
                cc_set.add(student.student_email)

        parent_whatsapp = getattr(student, "parent_whatsapp", None)
        student_grade   = getattr(student, "grade", None)

        # Include homeroom teacher only on 3rd slip
        if is_final and student_grade is not None:
            for email, info in get_teachers().items():
                homeroom_grades = info.get("homeroom_grade")
                if isinstance(homeroom_grades, (int, str)):
                    homeroom_grades = [homeroom_grades]
                if isinstance(homeroom_grades, list) and str(student_grade) in [str(g) for g in homeroom_grades]:
                    cc_set.add(email)
                    break

        # Add secretary only on 3rd slip
        cc_recipients = [e for e in cc_set if e]
        if is_final and SECRETARY_EMAIL:
            cc_recipients.append(SECRETARY_EMAIL)

        # Always BCC sender
        bcc_recipients = [SENDER_BCC_EMAIL] if SENDER_BCC_EMAIL else []

        recipients = [e for e in [parent_email_mom, parent_email_dad] if e]
        phones = student.parent_phones if student else []
        if not recipients and not phones:
            print(f"⚠️ No contact info (email or phone) for {student_name}; nothing sent.")
            return

        # Subjects and body
        if is_final:
            email_subject = f"URGENT: 3 Missed Homework Assignments for {student_name}"
            email_body = f"""
Assalamualaikum dear parent of {student_name},

We pray that you are well.

We wanted to bring to your attention that {student_name} has missed three homework assignments recently. Completing homework is essential for reinforcing the concepts taught in class and ensuring academic progress.

Below are the details of the missed assignments:

{slip_details}
📌 ACTION REQUIRED:  
Please take some time to discuss the importance of completing and submitting homework on time with {student_name}. If there are any challenges or reasons for the missed assignments, kindly let us know so we can work together to support {student_name} in staying on track.

We appreciate your cooperation and support in ensuring {student_name} succeeds in their academic journey.

Jazakumullahu Khair,  
Al-Mahdi Learning Institute - PinkSlip Pro
"""
        else:
            email_subject = f"Pink Slip Notification for {student_name}"
            email_body = f"""
Assalamualaikum dear parent of {student_name},

We pray that you are well.

This is to inform you that {student_name} has received a Pink Slip for missing a homework assignment. Kindly find the details below:

{slip_details}
We encourage you to discuss the importance of completing homework on time with {student_name} so that they can stay on track with their learning.

If you have any questions or concerns, feel free to reach out.

Jazakumullahu Khair,  
Al-Mahdi Learning Institute - PinkSlip Pro
"""

        if recipients:
            try:
                message = Message(
                    subject=email_subject,
                    sender=app.config['MAIL_USERNAME'],
                    recipients=recipients,         # mom/dad as available
                    cc=cc_recipients,              # + secretary only on 3rd
                    bcc=bcc_recipients,            # ← BCC sender on all
                    body=email_body
                )
                mail.send(message)
                print(f"📧 Sent email to {', '.join(recipients)} | CC: {', '.join(cc_recipients) if cc_recipients else '(none)'} | BCC: {', '.join(bcc_recipients) if bcc_recipients else '(none)'}")
            except Exception as e:
                print(f"Error sending email: {e}")
        else:
            print(f"ℹ️ No parent email for {student_name}; sending SMS only.")

        # Text every parent mobile we have (father and/or mother)
        if phones:
            text_body = re.sub(r"\*\*(.*?)\*\*", r"\1", email_body).strip()
            for ph in phones:
                notify_parent_channels(ph, text_body)
        else:
            print(f"ℹ️ No mobile number for {student_name}; SMS skipped.")

    except Exception as e:
        print(f"Error in send_email_to_parent: {e}")


    






# Decorator to restrict access to logged-in users
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'teacher_email' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function



def archive_expired_pink_slips():
    #expiration_time = datetime.utcnow() - timedelta(minutes=5)  # ⏱️ 5 minutes ago
    expiration_time = datetime.utcnow() - timedelta(days=60)
    # Find slips that are Pink Slip, older than 5 min
    expired_slips = HealthData.query.filter(
        HealthData.slip_type == "Pink Slip",
        HealthData.created_at <= expiration_time
    ).all()

    for slip in expired_slips:
        print(f"📦 Auto-archiving slip for {slip.student_name} at {slip.date}")

        archived_entry = ArchiveData(
            date=slip.date,
            slip_type=slip.slip_type,
            student_name=slip.student_name,
            grade_of_student=slip.grade_of_student,
            subject_of_student=slip.subject_of_student,
            homework_desc=slip.homework_desc,
            teacher_email=slip.teacher_email  # make sure ArchiveData has this!
        )
        db.session.add(archived_entry)
        db.session.delete(slip)
    
    db.session.commit()



@app.route('/test_email')
def test_email():
    try:
        message = Message(
            subject="Test Email from PinkSlip Pro",
            sender=app.config['MAIL_USERNAME'],
            recipients=['madiha8ahmed@gmail.com'],  # Replace with a test email
            body="This is a test email from PinkSlip Pro!"
        )
        mail.send(message)
        return "Test email sent successfully!"
    except Exception as e:
        return f"Error sending test email: {e}"




@app.before_first_request
def create_tables():
    db.create_all()
    
@app.route('/')
def index():
    # Unified hub for the whole management system.
    stats = {}
    if 'teacher_email' in session:
        te = session['teacher_email']
        try:
            stats['pink'] = HealthData.query.filter_by(teacher_email=te, slip_type="Pink Slip").count()
            stats['yellow'] = HealthData.query.filter_by(teacher_email=te, slip_type="Yellow Slip").count()
        except Exception:
            stats = {}
        # opportunistic daily run so time-based reminders still fire without a cron
        try:
            run_daily_tasks()
        except Exception as e:
            print(f"daily task (opportunistic) error: {e}")
    return render_template('home.html', stats=stats)


@app.route('/tasks/daily')
def tasks_daily():
    """Hit this once a day from a cron job: /tasks/daily?key=YOUR_TASK_KEY"""
    if request.args.get('key') != TASK_KEY:
        return {"error": "unauthorized"}, 403
    return run_daily_tasks(force=True)


@app.route('/notifications')
@login_required
def notifications():
    te = session.get('teacher_email')
    items = Notification.query.filter_by(teacher_email=te).order_by(Notification.created_at.desc()).limit(100).all()
    return render_template('notifications.html', items=items)


@app.route('/notifications/read/<int:note_id>', methods=['POST'])
@login_required
def mark_notification_read(note_id):
    te = session.get('teacher_email')
    note = Notification.query.filter_by(id=note_id, teacher_email=te).first()
    if note:
        note.is_read = True
        db.session.commit()
    return redirect(request.referrer or url_for('notifications'))


@app.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_read():
    te = session.get('teacher_email')
    Notification.query.filter_by(teacher_email=te, is_read=False).update({"is_read": True})
    db.session.commit()
    return redirect(request.referrer or url_for('notifications'))


@app.context_processor
def inject_notifications():
    """Make the bell's unread count + recent items available to every template."""
    if 'teacher_email' not in session:
        return {}
    te = session['teacher_email']
    try:
        unread = Notification.query.filter_by(teacher_email=te, is_read=False).count()
        recent = Notification.query.filter_by(teacher_email=te).order_by(Notification.created_at.desc()).limit(6).all()
    except Exception:
        unread, recent = 0, []
    return {"nav_unread": unread, "nav_recent": recent}


@app.route('/student-of-the-month')
@login_required
def student_of_the_month():
    return render_template('som.html')


# =====================================================================
#  ATTENDANCE MODULE  (late / absent) — recorded by homeroom teachers
# =====================================================================
def _homeroom_grades_for(teacher_email):
    info = get_teachers().get(teacher_email, {})
    hg = info.get("homeroom_grade", [])
    if isinstance(hg, int):
        hg = [hg]
    return [str(g) for g in (hg or [])]


@app.route('/attendance', methods=['GET', 'POST'])
@login_required
def attendance():
    teacher_email = session.get('teacher_email')
    homeroom_grades = _homeroom_grades_for(teacher_email)

    if not homeroom_grades:
        return render_template('attendance.html', no_homeroom=True,
                               students=[], today=date.today().isoformat(),
                               selected_date=date.today().isoformat())

    selected_date_str = request.form.get('date') or request.args.get('date') or date.today().isoformat()
    try:
        selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()
    except ValueError:
        selected_date = date.today()

    students = Student.query.filter(Student.grade.in_(homeroom_grades)).order_by(Student.name).all()

    if request.method == 'POST':
        recorded, notified = 0, 0
        for s in students:
            status = request.form.get(f"status_{s.id}")   # present | late | absent
            note = (request.form.get(f"note_{s.id}") or "").strip() or None
            if status not in ("late", "absent"):
                continue
            slip_type = "Late" if status == "late" else "Absent"
            # avoid duplicates for the same student + date + type
            exists = AttendanceSlip.query.filter_by(
                student_name=s.name, date=selected_date, slip_type=slip_type
            ).first()
            if exists:
                continue
            db.session.add(AttendanceSlip(
                date=selected_date, slip_type=slip_type, student_name=s.name,
                grade=s.grade, note=note, recorded_by=teacher_email
            ))
            recorded += 1
            try:
                send_attendance_notification(s, slip_type, selected_date, note)
                notified += 1
            except Exception as e:
                print(f"attendance notify error for {s.name}: {e}")
        db.session.commit()
        if recorded:
            flash(f"Attendance saved for {selected_date.strftime('%B %d, %Y')} — {recorded} slip(s), parents notified.", "success")
        else:
            flash("No late/absent students marked — nothing to record.", "info")
        return redirect(url_for('attendance', date=selected_date.isoformat()))

    # existing records for that date (to prefill)
    existing = {}
    for rec in AttendanceSlip.query.filter_by(date=selected_date).all():
        existing[rec.student_name] = rec.slip_type

    return render_template('attendance.html', no_homeroom=False, students=students,
                           existing=existing, homeroom_grades=homeroom_grades,
                           selected_date=selected_date.isoformat(), today=date.today().isoformat())


@app.route('/attendance/log')
@login_required
def attendance_log():
    teacher_email = session.get('teacher_email')
    homeroom_grades = _homeroom_grades_for(teacher_email)
    q = AttendanceSlip.query
    if homeroom_grades:
        q = q.filter(AttendanceSlip.grade.in_(homeroom_grades))
    else:
        q = q.filter_by(recorded_by=teacher_email)
    slips = q.order_by(AttendanceSlip.date.desc(), AttendanceSlip.student_name).limit(300).all()
    return render_template('attendance_log.html', slips=slips)


@app.route('/attendance/insights')
@login_required
def attendance_insights():
    teacher_email = session.get('teacher_email')
    homeroom_grades = _homeroom_grades_for(teacher_email)
    q = AttendanceSlip.query
    if homeroom_grades:
        q = q.filter(AttendanceSlip.grade.in_(homeroom_grades))
    else:
        q = q.filter_by(recorded_by=teacher_email)
    slips = q.all()

    counts_by_type = {"Late": 0, "Absent": 0}
    per_student = {}       # {name: {"Late": n, "Absent": m}}
    over_time = {}         # {"YYYY-MM": {"Late": n, "Absent": m}}
    for s in slips:
        counts_by_type[s.slip_type] = counts_by_type.get(s.slip_type, 0) + 1
        per_student.setdefault(s.student_name, {"Late": 0, "Absent": 0})
        per_student[s.student_name][s.slip_type] += 1
        key = s.date.strftime("%Y-%m")
        over_time.setdefault(key, {"Late": 0, "Absent": 0})
        over_time[key][s.slip_type] += 1
    over_time = dict(sorted(over_time.items()))

    return render_template('attendance_insights.html',
                           teacher_name=teacher_email.split('@')[0].replace('.', ' ').title(),
                           counts_by_type=counts_by_type, per_student=per_student,
                           over_time=over_time, total=len(slips),
                           students_flagged=len(per_student))



@app.route('/form', methods=['GET', 'POST'])
@login_required
def form():
    form = HealthDataForm()
    teacher_email = session.get('teacher_email')

    if teacher_email not in get_teachers():
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))

    # Get teacher's assigned grades & subjects
    teacher_info = get_teachers().get(teacher_email, {})
    allowed_grades = list(teacher_info.get("grades", {}).keys())  # Ensure grades are a list
    grade_subject_mapping = teacher_info.get("grades", {}) if teacher_info.get("grades") else {}

    print(f"🔍 DEBUG: Allowed Grades: {allowed_grades}")  # Debugging print
    print(f"🔍 DEBUG: Grade-Subject Mapping: {grade_subject_mapping}")  # Debugging print

    # Fetch students in allowed grades (Student.grade is an integer column,
    # so only pass numeric grades to the query — JK/SK etc. are skipped safely)
    grade_strs = [str(g) for g in allowed_grades]
    students_in_allowed_grades = Student.query.filter(Student.grade.in_(grade_strs)).all()
    student_choices = [(student.name, student.name) for student in students_in_allowed_grades]

    # Prepare valid subjects (for all grades)
    valid_subjects = set()
    for subjects in grade_subject_mapping.values():
        valid_subjects.update(subjects)

    # Update form choices dynamically
    form.grade_of_student.choices = [("", "Select Grade")] + [(str(grade), str(grade)) for grade in allowed_grades]
    form.student_name.choices = [("", "Select Student")] + student_choices
    form.subject_of_student.choices = [("", "Select Subject")] + [(subject, subject) for subject in valid_subjects]  # Dynamic subjects

    if form.validate_on_submit():
        print("✅ Form submission received!")  # Debugging print

        # Optional reschedule date (only meaningful for yellow slips)
        reschedule = None
        rd_raw = request.form.get('reschedule_date')
        if form.slip_type.data == "Yellow Slip" and rd_raw:
            try:
                reschedule = datetime.strptime(rd_raw, "%Y-%m-%d").date()
            except ValueError:
                reschedule = None

        new_data = HealthData(
            date=form.date.data,
            slip_type=form.slip_type.data,
            student_name=form.student_name.data,
            grade_of_student=str(form.grade_of_student.data),
            subject_of_student=form.subject_of_student.data,
            homework_desc=form.homework_desc.data,
            teacher_email=teacher_email,
            reschedule_date=reschedule,
        )
        db.session.add(new_data)
        db.session.commit()
        print("✅ Data saved to database!")  # Debugging print

        if new_data.slip_type == "Pink Slip":
            print("📧 Sending email to parent...")  # Debugging print
            check_three_pink_slips(new_data.student_name)
            print("✅ Email process triggered!")  # Debugging print

        if reschedule:
            flash(f"Yellow slip assigned to {new_data.student_name}. You'll be reminded on {reschedule.strftime('%B %d, %Y')}.", "success")
        else:
            flash(f"Slip assigned to {new_data.student_name}.", "success")
        return redirect(url_for('dashboard'))

    # Print validation errors
    print("❌ Form validation failed! Errors:")
    for field, errors in form.errors.items():
        print(f"❌ {field}: {', '.join(errors)}")

    return render_template('form.html', form=form, grade_subject_mapping=grade_subject_mapping)




@app.route('/dashboard')
@login_required

def dashboard():
    teacher_email = session.get('teacher_email')
    # Fire time-based reminders (yellow-slip due dates etc.) when a teacher lands here.
    try:
        run_daily_tasks()
    except Exception as e:
        print(f"daily task (dashboard) error: {e}")
    teacher_info = get_teachers().get(teacher_email, {})
    homeroom_grades = teacher_info.get("homeroom_grade")  # Can be int or list
    if isinstance(homeroom_grades, (int, str)):
        homeroom_grades = [homeroom_grades]  # normalize to list

    archive_expired_pink_slips()


    # Query 1: All slips for homeroom students
    homeroom_slips = []
    if homeroom_grades:
        grade_strs = [str(g) for g in homeroom_grades]
        students = Student.query.filter(Student.grade.in_(grade_strs)).all()
        student_names = [s.name for s in students]
        homeroom_slips = HealthData.query.filter(HealthData.student_name.in_(student_names)).all()

    # Query 2: All slips submitted by the current teacher
    teacher_slips = HealthData.query.filter_by(teacher_email=teacher_email).all()

    # Combine both slip lists without duplicates (based on HealthData.id)
    combined_slips_dict = {slip.id: slip for slip in homeroom_slips + teacher_slips}
    all_data = list(combined_slips_dict.values())

    # Prepare dashboard data
    dates = [data.date.strftime("%Y-%m-%d") for data in all_data]
    slip_type_data = [data.slip_type for data in all_data]
    student_name_data = [data.student_name for data in all_data]
    grade_of_student_data = [data.grade_of_student for data in all_data]
    subject_of_student_data = [data.subject_of_student for data in all_data]
    homework_desc_data = [data.homework_desc for data in all_data]
    ids = [data.id for data in all_data]
    teacher_name = teacher_info.get("name", "")
    return render_template(
        'dashboard.html',
        dates=dates,
        slip_type_data=slip_type_data,
        student_name_data=student_name_data,
        grade_of_student_data=grade_of_student_data,
        subject_of_student_data=subject_of_student_data,
        homework_desc_data=homework_desc_data,
        ids=ids,
        teacher_name = teacher_name,
        homeroom_grades=homeroom_grades
    )






@app.route('/view_students')
def view_students():
    students = Student.query.all()
    return "<br>".join([f"Name: {student.name}, Grade: {student.grade}" for student in students])

@app.route('/delete/<int:entry_id>', methods=['POST'])
def delete_entry(entry_id):
    # Retrieve the entry by ID
    entry = HealthData.query.get(entry_id)
    if entry:
        db.session.delete(entry)  # Delete the entry
        db.session.commit()  # Commit changes to the database
        return redirect(url_for('archive'))
    return "Entry not found", 404


@app.route('/archive/<int:entry_id>', methods=['POST'])
def archive_entry(entry_id):
    entry = HealthData.query.get(entry_id)
    if entry:
        archived_entry = ArchiveData(
                date=entry.date,
                slip_type=entry.slip_type,
                student_name=entry.student_name,
                grade_of_student=entry.grade_of_student,
                subject_of_student=entry.subject_of_student,
                homework_desc=entry.homework_desc,
                #teacher_email=entry.teacher_email,
                teacher_email=entry.teacher_email
  # ✅ Include this
            )

        db.session.add(archived_entry)
        db.session.delete(entry)  # Delete from main table
        db.session.commit()
        return redirect(url_for('dashboard'))
    return "Entry not found", 404


@app.route('/archive')
@login_required
def archive():
    teacher_email = session.get('teacher_email')
    teacher_info = get_teachers().get(teacher_email, {})
    homeroom_grades = teacher_info.get("homeroom_grade")
    teacher_name = teacher_info.get("name", "")
    if isinstance(homeroom_grades, (int, str)):
        homeroom_grades = [homeroom_grades]

    archive_expired_pink_slips()


    # Step 1: Get student names in homeroom grades
    homeroom_students = []
    if homeroom_grades:
        students = Student.query.filter(Student.grade.in_(homeroom_grades)).all()
        homeroom_students = [s.name for s in students]

    # Step 2: Get archived slips that either:
    # - belong to homeroom students (regardless of subject/teacher)
    # - were assigned by the current teacher (regardless of grade)
    homeroom_slips = ArchiveData.query.filter(ArchiveData.student_name.in_(homeroom_students)).all() if homeroom_students else []
    teacher_slips = ArchiveData.query.filter_by(teacher_email=teacher_email).all()

    # Step 3: Combine and deduplicate by ID
    combined = {entry.id: entry for entry in homeroom_slips + teacher_slips}
    filtered_archive = list(combined.values())

    return render_template('archive.html', archived_data=filtered_archive, homeroom_grades=homeroom_grades, teacher_name = teacher_name)






@app.route('/get_students/<grade>', methods=['GET'])
def get_students(grade):
    # Query the database for students in the selected grade
    students = Student.query.filter_by(grade=str(grade)).all()
    student_names = [student.name for student in students]  # Extract names
    return jsonify({'students': student_names})

@app.route('/delete_archive_entry/<int:entry_id>', methods=['POST'])
def delete_archive_entry(entry_id):
    # Find the entry in the archive database
    entry = ArchiveData.query.get_or_404(entry_id)
    try:
        # Delete the entry
        db.session.delete(entry)
        db.session.commit()
        return redirect(url_for('archive'))  # Redirect to the archive page
    except Exception as e:
        return f"An error occurred while deleting the entry: {e}"

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            email = (request.form.get('email') or '').strip().lower()
            password = request.form.get('password') or ''

            teacher = Teacher.query.filter_by(email=email).first()
            if teacher and check_password_hash(teacher.password_hash, password):
                session['teacher_email'] = email  # Store email in session
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid email or password.', 'danger')

        return render_template('login.html')

    except Exception as e:
        print(f"Error in /login route: {e}")  # Print error to terminal
        flash("An unexpected error occurred. Please try again.", "danger")
        return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Teachers create their own account and declare what they teach."""
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        phone = _normalize_e164(request.form.get('phone'))
        password = request.form.get('password') or ''
        confirm = request.form.get('confirm') or ''

        # --- validation ---
        if not name or not email or not password:
            flash('Please fill in your name, email, and password.', 'danger')
            return redirect(url_for('register'))
        if password != confirm:
            flash('The two passwords do not match.', 'danger')
            return redirect(url_for('register'))
        if len(password) < 8:
            flash('Please choose a password with at least 8 characters.', 'danger')
            return redirect(url_for('register'))
        if Teacher.query.filter_by(email=email).first():
            flash('An account with that email already exists. Try logging in.', 'warning')
            return redirect(url_for('login'))

        # --- homeroom grades: checkboxes named "homeroom" ---
        homeroom = []
        for val in request.form.getlist('homeroom'):
            homeroom.append(int(val) if val.isdigit() else val)

        # --- grade -> subjects: checkboxes named "teach_<grade>" ---
        grades = {}
        possible_grades = ['JK', 'SK', 1, 2, 3, 4, 5, 6, 7, 8]
        for g in possible_grades:
            subjects = request.form.getlist(f'teach_{g}')
            if subjects:
                grades[str(g)] = subjects  # keys stored as strings in JSON

        if not grades:
            flash('Please select at least one subject you teach.', 'danger')
            return redirect(url_for('register'))

        teacher = Teacher(
            name=name,
            email=email,
            phone=phone,
            password_hash=generate_password_hash(password),
            homeroom_grades_json=json.dumps(homeroom),
            grades_json=json.dumps(grades),
        )
        db.session.add(teacher)
        db.session.commit()

        flash('Account created — welcome! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.pop('teacher_email', None)  # Remove teacher's email from session
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))  # Redirect to login page

@app.route('/convert_yellow_to_pink/<int:entry_id>', methods=['POST'])
@login_required
def convert_yellow_to_pink(entry_id):
    entry = HealthData.query.get(entry_id)

    if entry and entry.slip_type == "Yellow Slip":
        # Convert to Pink Slip
        entry.slip_type = "Pink Slip"
        db.session.commit()

        # Get student details
        student = Student.query.filter_by(name=entry.student_name).first()
        if student and student.has_any_contact:
            # Count the number of Pink Slips **AFTER** the conversion
            pink_slips = HealthData.query.filter_by(student_name=entry.student_name, slip_type="Pink Slip").count()

            if pink_slips < 3:
                # If it's NOT the third pink slip, send a normal notification.
                # send_email_to_parent() also fires SMS/WhatsApp internally,
                # so there's no separate messaging call needed here.
                send_email_to_parent(
                    entry.student_name,
                    student.parent_email_mom,
                    student.parent_email_dad,
                    [entry],
                )
            else:
                # If it's the third Pink Slip, let check_three_pink_slips() handle the email
                check_three_pink_slips(entry.student_name)
                flash(f"Yellow Slip for {entry.student_name} has been converted to a Pink Slip. Third slip action triggered.", "warning")
                return redirect(url_for('dashboard'))

        flash(f"Yellow Slip for {entry.student_name} has been converted to a Pink Slip.", "success")
    else:
        flash("Invalid action. Slip not found or is already pink.", "danger")

    return redirect(url_for('dashboard'))


@app.route('/insights')
@login_required
def insights():
    teacher_email = session.get('teacher_email')
    teacher_info = get_teachers().get(teacher_email, {})
    homeroom_grades = teacher_info.get("homeroom_grade", [])
    subjects_by_grade = teacher_info.get("grades", {})

    if isinstance(homeroom_grades, (int, str)):
        homeroom_grades = [homeroom_grades]
    elif not homeroom_grades:
        homeroom_grades = []

    # ✅ Data for subject teacher
    teacher_slips = HealthData.query.filter_by(teacher_email=teacher_email).all()

    slip_counts_by_type = {}
    slip_counts_by_student = {}
    slips_stacked_data = {}
    slip_type_details = {"Pink Slip": [], "Yellow Slip": []}

    # New: Grouped data by Grade-Subject
    slips_per_grade_subject = {}

    for slip in teacher_slips:
        # Count by type
        slip_counts_by_type[slip.slip_type] = slip_counts_by_type.get(slip.slip_type, 0) + 1

        # Count per student for stacked data
        if slip.student_name not in slips_stacked_data:
            slips_stacked_data[slip.student_name] = {"Pink Slip": 0, "Yellow Slip": 0}
        slips_stacked_data[slip.student_name][slip.slip_type] += 1

        # Overall count
        slip_counts_by_student[slip.student_name] = slip_counts_by_student.get(slip.student_name, 0) + 1

        # Tooltip info
        slip_type_details[slip.slip_type].append(f"{slip.student_name} - {slip.subject_of_student}")

        # 📊 Grouped by Grade-Subject (e.g., 'Grade 5 Math')
        label = f"Grade {slip.grade_of_student} {slip.subject_of_student}"
        if label not in slips_per_grade_subject:
            slips_per_grade_subject[label] = {}
        if slip.student_name not in slips_per_grade_subject[label]:
            slips_per_grade_subject[label][slip.student_name] = {"Pink Slip": 0, "Yellow Slip": 0}
        slips_per_grade_subject[label][slip.student_name][slip.slip_type] += 1

    # ✅ Data for homeroom teacher
    homeroom_students = []
    slips_by_subject = {}
    slips_by_student_homeroom = {}

    # 📈 Trend over time (by month) — for the line chart
    slips_over_time = {}          # {"2025-06": {"Pink Slip": n, "Yellow Slip": m}}
    for slip in teacher_slips:
        if not getattr(slip, "date", None):
            continue
        key = slip.date.strftime("%Y-%m")
        slips_over_time.setdefault(key, {"Pink Slip": 0, "Yellow Slip": 0})
        slips_over_time[key][slip.slip_type] = slips_over_time[key].get(slip.slip_type, 0) + 1
    slips_over_time = dict(sorted(slips_over_time.items()))

    if homeroom_grades:
        grade_strs = [str(g) for g in homeroom_grades]
        homeroom_students = Student.query.filter(Student.grade.in_(grade_strs)).all()
        homeroom_names = [s.name for s in homeroom_students]

        slips = HealthData.query.filter(HealthData.student_name.in_(homeroom_names)).all()

        for slip in slips:
            slips_by_subject[slip.subject_of_student] = slips_by_subject.get(slip.subject_of_student, 0) + 1
            slips_by_student_homeroom[slip.student_name] = slips_by_student_homeroom.get(slip.student_name, 0) + 1

    return render_template(
        'insights.html',
        teacher_name=teacher_email.split('@')[0].replace('.', ' ').title(),
        is_homeroom_teacher=bool(homeroom_grades),
        slip_counts_by_type=slip_counts_by_type,
        slip_counts_by_student=slip_counts_by_student,
        slips_by_subject=slips_by_subject,
        slips_by_student_homeroom=slips_by_student_homeroom,
        slips_stacked_data=slips_stacked_data,
        slip_type_details=slip_type_details,
        slips_per_grade_subject=slips_per_grade_subject,
        slips_over_time=slips_over_time
    )


@app.route('/evaluate_students', methods=['GET', 'POST'])
@login_required
def evaluate_students():
    teacher_email = session.get('teacher_email')
    teacher_info = get_teachers().get(teacher_email, {})
    all_grades = teacher_info.get("grades", {}).keys()

    # Fetch students that the teacher teaches
    students = Student.query.filter(Student.grade.in_(all_grades)).all()

    selected_month = request.args.get('month')
    selected_year = request.args.get('year', type=int)

    # Show form only if month and year are selected
    if selected_month and selected_year:
        # Load existing evaluations (partial or submitted)
        evaluations = {}
        for eval in StudentEvaluation.query.filter_by(
            teacher_email=teacher_email,
            month=selected_month,
            year=selected_year
        ).all():
            evaluations[(eval.student_name, eval.grade)] = {
                "responsibility": eval.responsibility,
                "self_regulation": eval.self_regulation,
                "organization": eval.organization,
                "collaboration_initiative": eval.collaboration_initiative,
                "independent_work": eval.independent_work,
                "remarks": eval.remarks,
                "average_score": eval.average_score
            }

    else:
        evaluations = {}

    return render_template(
        'evaluate_students.html',
        students=students,
        evaluations=evaluations,
        months=MONTHS,
        years=YEARS,
        selected_month=selected_month,
        selected_year=selected_year
    )

def generate_evaluations_csv(evals, month, year, teacher_email):
    sio = StringIO()
    w = csv.writer(sio)
    w.writerow([
        "Teacher Email","Month","Year","Student","Grade",
        "Responsibility","Self-Regulation","Organization","Collaboration/Initiative","Independent Work",
        "Average","Remarks"
    ])
    for e in evals:
        w.writerow([
            teacher_email, month, year, e.student_name, e.grade,
            e.responsibility, e.self_regulation, e.organization,
            e.collaboration_initiative, e.independent_work,
            e.average_score, (e.remarks or "")
        ])
    data = sio.getvalue().encode("utf-8-sig")
    filename = f"Evaluations_{month}_{year}_{teacher_email.split('@')[0]}.csv"
    return data, filename

def email_csv_to_principal(csv_bytes, filename, teacher_email, month, year):
    if not PRINCIPAL_EMAIL:
        print("PRINCIPAL_EMAIL is not set; skipping email.")
        return
    subject = f"Submitted Evaluations – {month} {year} – {teacher_email}"
    body = (
        f"Assalamualaikum,\n\n"
        f"Attached are the submitted evaluations for {month} {year} from {teacher_email}.\n\n"
        f"Jazakumullahu Khair,\nPinkSlip Pro"
    )
    msg = Message(
        subject=subject,
        sender=app.config['MAIL_USERNAME'],
        recipients=[PRINCIPAL_EMAIL],
        cc=[teacher_email],
        body=body
    )
    msg.attach(filename, "text/csv", csv_bytes)
    mail.send(msg)



@app.route('/save_evaluations', methods=['POST'])
@login_required
def save_evaluations():
    import math
    teacher_email = session.get('teacher_email')
    month = request.form.get('month')
    year = int(request.form.get('year'))
    action = request.form.get('action')  # "save" or "submit"

    def parse_int(name):
        raw = (request.form.get(name) or "").strip()
        return int(raw) if raw.isdigit() else None

    # iterate robustly: key format "student_{name}_{grade}"
    for key in request.form:
        if not key.startswith("student_"):
            continue
        parts = key.split("_")
        grade = parts[-1]
        student_name = "_".join(parts[1:-1])  # handles underscores in names

        responsibility = parse_int(f"responsibility_{student_name}_{grade}")
        self_regulation = parse_int(f"self_regulation_{student_name}_{grade}")
        organization = parse_int(f"organization_{student_name}_{grade}")
        collaboration = parse_int(f"collaboration_initiative_{student_name}_{grade}")
        independent_work = parse_int(f"independent_work_{student_name}_{grade}")
        remarks = request.form.get(f"remarks_{student_name}_{grade}", "") or None

        scores = [responsibility, self_regulation, organization, collaboration, independent_work]
        avg_score = round(sum(s for s in scores if s is not None) / 5, 2) if all(s is not None for s in scores) else None

        # on final submit, enforce completeness server-side too
        if action == "submit" and any(s is None for s in scores):
            flash(f"Please complete all ratings for {student_name} (Grade {grade}) before submitting.", "warning")
            return redirect(url_for('evaluate_students', month=month, year=year))

        record = StudentEvaluation.query.filter_by(
            teacher_email=teacher_email,
            student_name=student_name,
            grade=grade,
            month=month,
            year=year
        ).first()

        if not record:
            record = StudentEvaluation(
                teacher_email=teacher_email,
                student_name=student_name,
                grade=grade,
                month=month,
                year=year
            )
            db.session.add(record)

        record.responsibility = responsibility
        record.self_regulation = self_regulation
        record.organization = organization
        record.collaboration_initiative = collaboration
        record.independent_work = independent_work
        record.remarks = remarks
        record.average_score = avg_score
        record.is_submitted = (action == "submit")

    db.session.commit()

    if action == "save":
        flash("Evaluations saved successfully.", "success")
        return redirect(url_for('evaluate_students', month=month, year=year))

    # action == "submit": generate CSV, email, WhatsApp, then go to view
    submitted = StudentEvaluation.query.filter_by(
        teacher_email=teacher_email, month=month, year=year, is_submitted=True
    ).all()

    csv_bytes, filename = generate_evaluations_csv(submitted, month, year, teacher_email)
    email_csv_to_principal(csv_bytes, filename, teacher_email, month, year)

    flash("Evaluations submitted and emailed to the principal.", "success")
    return redirect(url_for('view_evaluations', month=month, year=year))



@app.route('/view_evaluations')
@login_required
def view_evaluations():
    teacher_email = session.get('teacher_email')
    selected_month = request.args.get('month')
    selected_year = request.args.get('year', type=int)

    evaluations = []
    if selected_month and selected_year:
        evaluations = StudentEvaluation.query.filter_by(
            teacher_email=teacher_email,
            month=selected_month,
            year=selected_year,
            is_submitted=True
        ).all()

    return render_template(
        'view_evaluations.html',
        evaluations=evaluations,
        months=MONTHS,
        years=YEARS,
        selected_month=selected_month,
        selected_year=selected_year
    )

def build_ai_prompt(data, month, year):
    prompt = f"""
You are a school AI assistant helping the principal of an Islamic school evaluate students based on their performance data from respective teachers for {month} {year}.

Each row of input data contains:
- Student name
- Grade
- Responsibility (on a scale of 1–5)
- Self-Regulation (on a scale of 1–5)
- Organization (on a scale of 1–5)
- Collaboration/Initiative (on a scale of 1–5)
- Independent Work (on a scale of 1–5)
- Remarks (optional for teachers to fill in)
- Average score

Definitions of parameters:
Responsibility = Homework completion, returning signed papers, coming prepared, managing supplies, and fulfilling classroom duties.
Self-Regulation = Behavior in class, hallway, Salah hall, outside, and during dismissal.
Organization = Desk and surroundings neatness, managing supplies, papers in place.
Collaboration/Initiative = Working well with others, contributing to group tasks, helping/supporting, and showing respect.
Independent Work = Completing tasks on time, following instructions, avoiding distractions, time management, effort.

Tasks:
1. <strong>Students of the Month Recommendations 🏆</strong>  
   - Recommend only students who are truly deserving based on strong ratings and/or positive remarks.  
   - You may recommend fewer than five. Do not force a full list if others are not qualified.  
   - For each recommended student, explain why they stood out (referencing their strong parameters and remarks).  
   - Present in a <table> with columns: Student Name, Grade, Average Score, Strengths, Remarks.  

2. <strong>Students Needing Attention or Support 🔍</strong>  
   - Identify up to five students with the lowest averages or most concerning remarks.  
   - For each, explain the specific parameter(s) they struggle with.  
   - Provide personalized, practical interventions teachers, parents or the principal can use.  
   - Present in a <table> with columns: Student Name, Grade, Average Score, Weak Areas, Suggested Interventions.  

3. <strong>Overall Insights 📊</strong>  
   - Highlight strengths and common challenges across the class.  
   - Suggest actionable strategies the school can adopt to support both strong and weak students.  
   - Present as a short <ul> list.  

Formatting Rules:
- Respond in clean HTML fragments only.  
- No markdown, no backticks, no code fences, no ```html,<html>/<head>/<body> tags.  
- Use <strong> for section titles, <p> for explanations, <ul>/<li> for insights, and <table> for tabular data.  

Data:
"""

    for s in data:
        prompt += f"\n- {s['name']} (Grade {s['grade']}): Resp={s['responsibility']}, SelfReg={s['self_regulation']}, Org={s['organization']}, Collab={s['collaboration_initiative']}, IndWork={s['independent_work']}, Avg={s['average']}, Remarks={s['remarks']}"

    return prompt.strip()

@app.route('/generate_report', methods=['GET', 'POST'])
@login_required
def generate_report():
    teacher_email = session.get('teacher_email')

    # --- GET: show month/year picker ---
    if request.method == 'GET':
        return render_template('generate_report.html', months=MONTHS, years=YEARS)

    # --- POST: generate report ---
    month = request.form.get('month')
    year = request.form.get('year', type=int)

    if not month or not year:
        flash("Please select a month and year.", "warning")
        return redirect(url_for('generate_report'))

    evaluations = StudentEvaluation.query.filter_by(
        teacher_email=teacher_email,
        month=month,
        year=year,
        is_submitted=True
    ).all()

    if not evaluations:
        flash(f"No submitted evaluations for {month} {year}.", "warning")
        return redirect(url_for('generate_report'))

    # Build structured data for the prompt
    student_data = [{
        "name": e.student_name,
        "grade": e.grade,
        "responsibility": e.responsibility,
        "self_regulation": e.self_regulation,
        "organization": e.organization,
        "collaboration_initiative": e.collaboration_initiative,
        "independent_work": e.independent_work,
        "remarks": e.remarks or "",
        "average": e.average_score
    } for e in evaluations]

    prompt = build_ai_prompt(student_data, month, year)

    try:
        # OpenAI new SDK style; ensure you've set up `client = OpenAI(api_key=...)`
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You generate concise, objective student performance reports using clean HTML with real <strong> tags and real <table> markup (no asterisks, no ASCII tables)."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )
        report_text = resp.choices[0].message.content or ""

        # Convert any lingering markdown bold to HTML bold, then render tables via markdown2.
        # (If you change your prompt to “respond in pure HTML only”, you can skip markdown2.)
        report_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", report_text)

        # Give headings some emoji polish (optional)
        report_text = report_text.replace(
            "Top 5 Student of the Month Recommendations",
            "🏆 <strong>Top 5 Student of the Month Recommendations</strong>"
        ).replace(
            "Students Needing Support",
            "🔍 <strong>Students Needing Support</strong>"
        )

        # Convert markdown tables (if any) to real HTML tables
        html_report = markdown2.markdown(report_text, extras=["tables"])
        return render_template("ai_report.html", report=Markup(html_report), month=month, year=year)

    except Exception as e:
        print(f"OpenAI API error: {e}")
        flash("Error generating AI report.", "danger")
        return redirect(url_for('generate_report'))

        


    


from flask import make_response
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO

@app.route('/download_report/<month>/<int:year>')
@login_required
def download_report(month, year):
    teacher_email = session.get('teacher_email')

    evaluations = StudentEvaluation.query.filter_by(
        teacher_email=teacher_email,
        month=month,
        year=year,
        is_submitted=True
    ).all()

    if not evaluations:
        flash("No evaluations submitted for this month and year.", "warning")
        return redirect(url_for('generate_report'))

    # Prepare data for AI
    student_data = [
        {
            "name": e.student_name,
            "grade": e.grade,
            "responsibility": e.responsibility,
            "self_regulation": e.self_regulation,
            "organization": e.organization,
            "collaboration_initiative": e.collaboration_initiative,
            "independent_work": e.independent_work,
            "remarks": e.remarks or "",
            "average": e.average_score
        } for e in evaluations
    ]

    prompt = build_ai_prompt(student_data, month, year)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are an assistant that generates student performance reports."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.5
    )

    report = response.choices[0].message.content

    # Generate PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()
    story = [Paragraph(line, styles["Normal"]) for line in report.split('\n')]
    doc.build(story)

    pdf = buffer.getvalue()
    buffer.close()

    response = make_response(pdf)
    response.headers["Content-Disposition"] = f"attachment; filename=AI_Report_{month}_{year}.pdf"
    response.headers["Content-Type"] = "application/pdf"
    return response

import re
from markupsafe import Markup

def clean_ai_output_to_html(text):
    # 1. Remove markdown asterisks and replace bolds
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

    # 2. Convert markdown-style tables to real HTML tables
    def convert_table(md):
        lines = [line.strip() for line in md.strip().split("\n") if line.strip()]
        if not lines or len(lines) < 2: return md

        headers = [h.strip() for h in lines[0].split("|") if h.strip()]
        html = "<table class='table table-bordered table-sm'><thead><tr>" + \
               "".join(f"<th>{h}</th>" for h in headers) + "</tr></thead><tbody>"

        for line in lines[2:]:  # skip header + separator
            cells = [c.strip() for c in line.split("|") if c.strip()]
            html += "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

        html += "</tbody></table>"
        return html

    table_blocks = re.findall(r"((?:\|.*?\n)+)", text)
    for tb in table_blocks:
        html_table = convert_table(tb)
        text = text.replace(tb, html_table)

    # Final cleanup: newlines to <br>
    text = text.replace("\n\n", "<br><br>")
    return Markup(text)


if __name__ == '__main__':
    app.run(debug=True)