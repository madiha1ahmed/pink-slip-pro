"""
One-time migration: load the original hard-coded staff roster into the
Teacher table so existing teachers can log in immediately.

Run once, after deploying the new app.py:

    python seed_teachers.py

Existing accounts (matched by email) are skipped, so it's safe to re-run.
After this, new teachers use the /register page and you never touch code again.

NOTE: every seeded teacher gets the same temporary password below. Ask each
teacher to log in and (ideally) re-register or change it. Better still: skip
this script entirely and have everyone self-register from scratch.
"""
import json
from werkzeug.security import generate_password_hash
from app import app, db, Teacher

TEMP_PASSWORD = "12AlMahdi!"   # change this before running if you like

# (email, name, homeroom_grades, {grade: [subjects]})
ROSTER = [
    ("mahmed@almahdilearninginstitute.ca", "Madiha Mariam Ahmed", [6],
     {4: ["Math"], 5: ["Math"], 6: ["Math"]}),
    ("fjaffal@almahdilearninginstitute.ca", "Fatme Jaffal", [4, 5],
     {2: ["Arabic", "Quran"], 3: ["Arabic", "Quran"], 6: ["Arabic", "Art"],
      7: ["Arabic", "Art"], 8: ["Arabic", "Art"]}),
    ("hassaad@almahdilearninginstitute.ca", "Hala Assaad", [],
     {2: ["English"], 3: ["English"]}),
    ("faborida@almahdilearninginstitute.ca", "Fatima Abourida", [4, 5],
     {4: ["English", "Gym"], 5: ["Gym"], 6: ["Gym"], 7: ["Gym"], 8: ["Gym"]}),
    ("fabbas@almahdilearninginstitute.ca", "Faiza Abbas", [2, 3],
     {2: ["Math", "Science", "Social", "Islamic Studies", "Gym"],
      3: ["Math", "Science", "Social", "Islamic Studies", "Gym"],
      7: ["Math"], 8: ["Math"]}),
    ("sselman@almahdilearninginstitute.ca", "Sarah Selman", [4, 5],
     {4: ["English", "Islamic Studies", "French", "Social"],
      5: ["French", "Islamic Studies", "Social"],
      6: ["French"], 7: ["French"], 8: ["French"]}),
    ("sshoaib@almahdilearninginstitute.ca", "Sarah Shoaib", ["JK"],
     {1: ["English"]}),
]

with app.app_context():
    db.create_all()
    added = 0
    for email, name, homeroom, grades in ROSTER:
        if Teacher.query.filter_by(email=email).first():
            print(f"↷ skip (already exists): {email}")
            continue
        db.session.add(Teacher(
            name=name,
            email=email,
            password_hash=generate_password_hash(TEMP_PASSWORD),
            homeroom_grades_json=json.dumps(homeroom),
            grades_json=json.dumps({str(g): s for g, s in grades.items()}),
        ))
        added += 1
        print(f"✓ added: {name} <{email}>")
    db.session.commit()
    print(f"\nDone. {added} teacher(s) added. Temporary password for all: {TEMP_PASSWORD}")
