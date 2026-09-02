"""
Reset helper for testing.

Usage:
    python reset_db.py teachers    # delete ALL teacher accounts only (keeps students, slips, evaluations)
    python reset_db.py all         # wipe EVERYTHING (drops and recreates all tables)

After running "teachers", every email is free again, so you can test /register
from scratch — including your own.
"""
import sys
from app import app, db, Teacher

def show_db():
    print(f"→ Database in use: {app.config.get('SQLALCHEMY_DATABASE_URI')}\n")

def reset_teachers():
    with app.app_context():
        count = Teacher.query.count()
        Teacher.query.delete()
        db.session.commit()
        print(f"✅ Deleted {count} teacher account(s). Students and slips are untouched.")
        print("   You can now register fresh at /register.")

def reset_all():
    with app.app_context():
        confirm = input("⚠️  This deletes ALL data (teachers, students, slips, evaluations). Type 'WIPE' to confirm: ")
        if confirm.strip() != "WIPE":
            print("Cancelled. Nothing was changed.")
            return
        db.drop_all()
        db.create_all()
        print("✅ Database wiped and recreated empty. Re-run populate scripts if you want sample data.")

if __name__ == "__main__":
    show_db()
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if mode == "teachers":
        reset_teachers()
    elif mode == "all":
        reset_all()
    else:
        print("Please say what to reset:")
        print("    python reset_db.py teachers   (recommended — clears teacher logins only)")
        print("    python reset_db.py all        (nuclear — wipes the whole database)")
