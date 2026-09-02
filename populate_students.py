"""
Populate the Student table from students.xlsx.

Handles the updated file layout:
  First Name | Family Name | Name | Grade | Parent Email Dad | Parent Email Mom
  | Student Email | Father WhatsApp | Mother WhatsApp

Missing values (blank cells / NaN) are stored as NULL — the app then notifies
whichever parent(s) it can reach and skips the rest gracefully.

Run once against a fresh database:
    python populate_students.py
"""
import math
import pandas as pd
from app import app, db, Student, normalize_na_phone

FILE = "students.xlsx"


def clean(val):
    """Return a trimmed string, or None for blanks / NaN."""
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def clean_grade(val):
    """Normalize grade to 'JK', 'SK', or '1'..'8' (a string)."""
    s = clean(val)
    if s is None:
        return None
    s = s.upper().replace("GRADE", "").strip()
    try:
        return str(int(float(s)))     # '5' or '5.0' -> '5'
    except (ValueError, TypeError):
        return s                      # 'JK' / 'SK'


def col(row, *names):
    """First matching column value (handles trailing spaces in headers)."""
    for n in names:
        for key in row.index:
            if key.strip().lower() == n.strip().lower():
                return row[key]
    return None


with app.app_context():
    df = pd.read_excel(FILE)
    added, skipped = 0, 0
    for _, row in df.iterrows():
        name = clean(col(row, "Name")) or " ".join(
            x for x in [clean(col(row, "First Name")), clean(col(row, "Family Name"))] if x
        )
        if not name:
            skipped += 1
            continue

        student = Student(
            name=name,
            grade=clean_grade(col(row, "Grade")) or "?",
            parent_email_dad=clean(col(row, "Parent Email Dad")),
            parent_email_mom=clean(col(row, "Parent Email Mom")),
            student_email=clean(col(row, "Student Email")),
            parent_whatsapp_dad=normalize_na_phone(col(row, "Father WhatsApp")),
            parent_whatsapp_mom=normalize_na_phone(col(row, "Mother WhatsApp")),
        )
        db.session.add(student)
        added += 1

    db.session.commit()

    no_contact = [s.name for s in Student.query.all() if not s.has_any_contact]
    print(f"Added {added} students ({skipped} rows skipped for missing name).")
    if no_contact:
        print(f"WARNING: {len(no_contact)} student(s) have NO parent email or phone on file:")
        for n in no_contact:
            print(f"    - {n}")
        print("   Notifications for these students will be skipped until contact info is added.")
