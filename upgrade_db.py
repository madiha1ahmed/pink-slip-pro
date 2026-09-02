"""
One-time, NON-DESTRUCTIVE database upgrade for the Al-Mahdi Hub.

It adds any columns/tables that newer features need, WITHOUT deleting your data:
  • teacher.homeroom_grades, teacher.phone, teacher.grades_json, teacher.is_active, teacher.created_at
  • health_data.reschedule_date, health_data.reminder_sent
  • creates new tables: attendance_slip, e_certificate (via SQLAlchemy)

Run it once from the project folder:   python upgrade_db.py

Works for local SQLite. For Render Postgres, a fresh database is built automatically by the
app; if you ever need to alter an existing Postgres, use Flask-Migrate instead.
"""
import sqlite3, os
from app import app, db

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'slip_data.db')

# columns to ensure: table -> [(column, SQL type + default)]
WANT = {
    'teacher': [
        ('homeroom_grades', "VARCHAR(50) DEFAULT ''"),
        ('phone',           "VARCHAR(30) DEFAULT ''"),
        ('grades_json',     "TEXT DEFAULT '{}'"),
        ('is_active',       "BOOLEAN DEFAULT 1"),
        ('created_at',      "DATETIME"),
    ],
    'health_data': [
        ('reschedule_date', "DATE"),
        ('reminder_sent',   "BOOLEAN DEFAULT 0"),
    ],
}

def ensure_columns():
    if not os.path.exists(DB_PATH):
        print("No existing slip_data.db — nothing to alter; the app will create it fresh.")
        return
    con = sqlite3.connect(DB_PATH); cur = con.cursor()
    for table, cols in WANT.items():
        # skip if the table doesn't exist yet
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cur.fetchone():
            print(f"(table '{table}' doesn't exist yet — will be created by the app)")
            continue
        existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})")}
        for col, decl in cols:
            if col not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
                print(f"  + added {table}.{col}")
    con.commit(); con.close()

if __name__ == '__main__':
    print("Upgrading database…")
    ensure_columns()
    with app.app_context():
        db.create_all()   # creates any brand-new tables (attendance_slip, e_certificate)
    print("✅ Done. Your data is intact and the schema is up to date.")
