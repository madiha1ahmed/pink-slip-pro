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
from datetime import datetime, timedelta
from openai import OpenAI
from flask import Markup
import re
import markdown2
from twilio.rest import Client

account_sid = 'ACf71e43846bbe8466b3730273568fc5fd'
auth_token='692cb59e658e3599e2015a1c31a1538d'


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


MONTHS = [
    'September', 'October', 'November', 'December',
    'January', 'February', 'March', 'April', 'May', 'June'
]
YEARS = [2025, 2026]

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('POSTGRES_URL', 'sqlite:///slip_data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email configuration
# Email configuration for Gmail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'madiha1ahmed@gmail.com'  # Replace with your Gmail address
app.config['MAIL_PASSWORD'] = 'ktqr vukf tsay cqzw'  # Replace with the App Password

mail = Mail(app)

teachers = {
    "mahmed@almahdilearninginstitute.ca": {
        "password": generate_password_hash("12AlMahdi!"),  # Secure password hashing
        "homeroom_grade": [5],
        "name": "Madiha Mariam Ahmed",
        "grades": {
            4: ["Math"],  # Teaches only Math in Grade 4
            5: ["Math", "Science", "Social", "Art", "Gym"],  # Teaches multiple subjects in Grade 5
            6: ["Art", "Gym"]  # Teaches only Art & Gym in Grade 6
        }
    },
    "fabbas@almahdilearninginstitute.ca": {
        "password": generate_password_hash("12AlMahdi!"),
        "homeroom_grade": [3],
        "name": "Faiza Abbas, Al-Mahdi's Math genius and Clean freak!!",
        "grades": {
            3: ["Math", "Science", "Social", "Art", "Gym"],
            7: ["Math"],
            8: ["Math"]
        }
    },
    "zjaffery@almahdilearninginstitute.ca": {
        "password": generate_password_hash("12AlMahdi!"),
        "homeroom_grade": [7,8],
        "name": "Zahra Jaffery, Al-Mahdi's favorite English instructor!",
        "grades": {
            5: ["English", "Islamic Studies"],
            6: ["English", "Islamic Studies"],
            7: ["English"],
            8: ["English"]
        }
    },
    "sghabriss@almahdilearninginstitute.ca": {
        "password": generate_password_hash("12AlMahdi!"),
        "name": "Soukyana Ghabriss, Al-Mahdi's all-rounder and best staff member of the year!",
        "homeroom_grade": [None],
        "grades": {
            4: ["French"],
            5: ["French"],
            6: ["French"],
            7: ["French"],
            8: ["French"]
        }
    }
}



#bcrypt = Bcrypt(app)

db = SQLAlchemy(app)
#db1 = SQLAlchemy(app)
migrate = Migrate(app, db)

class HealthData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    slip_type = db.Column(db.String, nullable=False)
    student_name = db.Column(db.String, nullable=False)
    grade_of_student = db.Column(db.Integer, nullable=False)
    subject_of_student = db.Column(db.String, nullable=False)
    homework_desc = db.Column(db.String, nullable=False)
    teacher_email = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Add this field

    def __repr__(self):
        return f'<HealthData {self.id}>'

    
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    grade = db.Column(db.Integer, nullable=False)
    parent_email = db.Column(db.String(150), nullable=False)  # Add this column
    parent_whatsapp = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f"<Student {self.name} (Grade {self.grade})>"


    

    
class ArchiveData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    slip_type = db.Column(db.String, nullable=False)
    student_name = db.Column(db.String, nullable=False)
    grade_of_student = db.Column(db.Integer, nullable=False)
    subject_of_student = db.Column(db.String, nullable=False)
    homework_desc = db.Column(db.String, nullable=False)
    teacher_email = db.Column(db.String, nullable=False)  # Required for filtering

class StudentEvaluation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_email = db.Column(db.String, nullable=False)
    student_name = db.Column(db.String, nullable=False)
    grade = db.Column(db.Integer, nullable=False)
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


def check_three_pink_slips(student_name):
    try:
        slips = HealthData.query.filter_by(student_name=student_name, slip_type="Pink Slip").order_by(HealthData.date).all()
        student = Student.query.filter_by(name=student_name).first()

        if not student or not student.parent_email:
            print(f"⚠️ Parent email not found for {student_name}")  # Debugging print
            return
        
        if not student or not student.parent_whatsapp:
            print(f"⚠️ Parent WhatsApp not found for {student_name}")  # Debugging print
            return
        
        parent_email = student.parent_email
        parent_whatsapp = student.parent_whatsapp.strip('"').strip("'").strip()
        print(f"📧 Preparing email for {student_name} - Total Pink Slips: {len(slips)}")
        print(f"📧 Preparing whatsapp for {student_name} - Total Pink Slips: {len(slips)}")  # Debugging print

        if len(slips) == 1:
            print(f"📤 Sending first pink slip email to {parent_email}")  # Debugging print
            send_email_to_parent(student_name, parent_email, [slips[0]])
            
        elif len(slips) == 2:
            print(f"📤 Sending second pink slip email to {parent_email}")  # Debugging print
            send_email_to_parent(student_name, parent_email, [slips[1]])
            
        elif len(slips) == 3:
            print(f"⚠️ Third pink slip detected! Sending urgent email to {parent_email}")  # Debugging print
            send_email_to_parent(student_name, parent_email, slips, is_final=True)
            
            for slip in slips:
                archive_entry(slip.id)
    except Exception as e:
        print(f"❌ Error in check_three_pink_slips: {e}")


def send_whatsapp_message(to_number, message_body):
    """
    Sends a plain text WhatsApp message using Twilio.

    Args:
        to_number (str): WhatsApp number in E.164 format, e.g., +14165551234
        message_body (str): Message content (plain text)

    Environment Variables Required:
        - TWILIO_ACCOUNT_SID
        - TWILIO_AUTH_TOKEN
        - TWILIO_WHATSAPP_FROM (e.g., whatsapp:+14155238886 for sandbox)
    """
    try:
        
        

        if not account_sid or not auth_token:
            print("❌ TWILIO credentials missing. WhatsApp not sent.")
            return
        
        

        client = Client(account_sid, auth_token)
        msg = client.messages.create(
            from_='whatsapp:+14155238886',
            to=f"whatsapp:{to_number}",
            body=message_body
        )
        print(f"📤 WhatsApp sent to {to_number} | SID: {msg.sid}")

    except Exception as e:
        print(f"❌ Error sending WhatsApp: {e}")


def send_email_to_parent(student_name, parent_email, slips, is_final=False):
    """
    Sends the existing email to the parent and mirrors the same text to WhatsApp.
    Requires:
      - Student.parent_whatsapp populated (E.164 format, e.g., +14165551234)
      - TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN env vars (preferred)
      - TWILIO_WHATSAPP_FROM env var set to your WA sender
        (e.g., 'whatsapp:+14155238886' for Twilio sandbox)
    """
    try:
        # Build slip details and CC list (same as before)
        slip_details = ""
        cc_set = set()

        for i, slip in enumerate(slips, start=1):
            slip_details += f"{i}️⃣ **Subject:** {slip.subject_of_student}\n"
            slip_details += f"   📅 Date: {slip.date.strftime('%Y-%m-%d')}\n"
            slip_details += f"   📖 Homework Details: {slip.homework_desc}\n\n"
            if slip.teacher_email:
                cc_set.add(slip.teacher_email)

        # Look up student once (grade + whatsapp)
        student = Student.query.filter_by(name=student_name).first()
        parent_whatsapp = None
        student_grade = None
        if student:
            parent_whatsapp = getattr(student, "parent_whatsapp", None)
            student_grade = student.grade

        # Include homeroom teacher on final (3rd pink) email
        if is_final and student_grade is not None:
            for email, info in teachers.items():
                homeroom_grades = info.get("homeroom_grade")
                if isinstance(homeroom_grades, int):
                    homeroom_grades = [homeroom_grades]
                if isinstance(homeroom_grades, list) and student_grade in homeroom_grades:
                    cc_set.add(email)
                    break  # assume one homeroom teacher per grade

        # Email subject/body (unchanged)
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

        # Send the email
        try:
            message = Message(
                subject=email_subject,
                sender=app.config['MAIL_USERNAME'],
                recipients=[parent_email],
                cc=[e for e in cc_set if e],
                body=email_body
            )
            mail.send(message)
            print(f"📧 Sent email to {parent_email} | CC: {', '.join(cc_set) if cc_set else '(none)'}")
        except Exception as e:
            print(f"Error sending email: {e}")

        # Replace WhatsApp part with:
        if parent_whatsapp:
            whatsapp_body = re.sub(r"\*\*(.*?)\*\*", r"\1", email_body).strip()
            print(f"📤 Sending first pink slip WhatsApp to {parent_whatsapp}")
            #parent_whatsapp = "+1"+"parent_whatsapp"
            send_whatsapp_message(parent_whatsapp, whatsapp_body)
        else:
            print(f"⚠️ No WhatsApp number found for {student_name}")

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
    return render_template('index.html')

@app.route('/form', methods=['GET', 'POST'])
@login_required
def form():
    form = HealthDataForm()
    teacher_email = session.get('teacher_email')

    if teacher_email not in teachers:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))

    # Get teacher's assigned grades & subjects
    teacher_info = teachers.get(teacher_email, {})
    allowed_grades = list(teacher_info.get("grades", {}).keys())  # Ensure grades are a list
    grade_subject_mapping = teacher_info.get("grades", {}) if teacher_info.get("grades") else {}

    print(f"🔍 DEBUG: Allowed Grades: {allowed_grades}")  # Debugging print
    print(f"🔍 DEBUG: Grade-Subject Mapping: {grade_subject_mapping}")  # Debugging print

    # Fetch students in allowed grades
    students_in_allowed_grades = Student.query.filter(Student.grade.in_(allowed_grades)).all()
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

        new_data = HealthData(
            date=form.date.data,
            slip_type=form.slip_type.data,
            student_name=form.student_name.data,
            grade_of_student=int(form.grade_of_student.data),
            subject_of_student=form.subject_of_student.data,
            homework_desc=form.homework_desc.data,
            teacher_email=teacher_email
        )
        db.session.add(new_data)
        db.session.commit()
        print("✅ Data saved to database!")  # Debugging print

        if new_data.slip_type == "Pink Slip":
            print("📧 Sending email to parent...")  # Debugging print
            check_three_pink_slips(new_data.student_name)
            print("✅ Email process triggered!")  # Debugging print

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
    teacher_info = teachers.get(teacher_email, {})
    homeroom_grades = teacher_info.get("homeroom_grade")  # Can be int or list
    if isinstance(homeroom_grades, int):
        homeroom_grades = [homeroom_grades]  # normalize to list

    archive_expired_pink_slips()


    # Query 1: All slips for homeroom students
    homeroom_slips = []
    if homeroom_grades:
        students = Student.query.filter(Student.grade.in_(homeroom_grades)).all()
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
    teacher_info = teachers.get(teacher_email, {})
    homeroom_grades = teacher_info.get("homeroom_grade")
    teacher_name = teacher_info.get("name", "")
    if isinstance(homeroom_grades, int):
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
    students = Student.query.filter_by(grade=int(grade)).all()
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
            email = request.form['email']
            password = request.form['password']

            if email in teachers:
                hashed_password = teachers[email]["password"]  # Get the stored hashed password

                if check_password_hash(hashed_password, password):
                    session['teacher_email'] = email  # Store email in session
                    flash('Login successful!', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Invalid email or password.', 'danger')
            else:
                flash('Invalid email or password.', 'danger')

        return render_template('login.html')

    except Exception as e:
        print(f"Error in /login route: {e}")  # Print error to terminal
        flash("An unexpected error occurred. Please try again.", "danger")
        return redirect(url_for('login'))


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
        if student and student.parent_email and student.parent_whatsapp:
            # Count the number of Pink Slips **AFTER** the conversion
            pink_slips = HealthData.query.filter_by(student_name=entry.student_name, slip_type="Pink Slip").count()

            if pink_slips < 3:
                # If it's NOT the third pink slip, send a normal email
                send_email_to_parent(entry.student_name, student.parent_email, [entry])
                send_whatsapp_message(student.parent_whatsapp, [entry])
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
    teacher_info = teachers.get(teacher_email, {})
    homeroom_grades = teacher_info.get("homeroom_grade", [])
    subjects_by_grade = teacher_info.get("grades", {})

    if isinstance(homeroom_grades, int):
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

    if homeroom_grades:
        homeroom_students = Student.query.filter(Student.grade.in_(homeroom_grades)).all()
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
        slips_per_grade_subject=slips_per_grade_subject
    )


@app.route('/evaluate_students', methods=['GET', 'POST'])
@login_required
def evaluate_students():
    teacher_email = session.get('teacher_email')
    teacher_info = teachers.get(teacher_email, {})
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

@app.route('/save_evaluations', methods=['POST'])
@login_required
def save_evaluations():
    teacher_email = session.get('teacher_email')
    month = request.form.get('month')
    year = int(request.form.get('year'))
    action = request.form.get('action')  # "save" or "submit"

    for key in request.form:
        if key.startswith("student_"):
            _, student_name, grade = key.split("_")
            grade = int(grade)

            responsibility = int(request.form.get(f"responsibility_{student_name}_{grade}", 0))
            self_regulation = int(request.form.get(f"self_regulation_{student_name}_{grade}", 0))
            organization = int(request.form.get(f"organization_{student_name}_{grade}", 0))
            collaboration = int(request.form.get(f"collaboration_initiative_{student_name}_{grade}", 0))
            independent_work = int(request.form.get(f"independent_work_{student_name}_{grade}", 0))
            remarks = request.form.get(f"remarks_{student_name}_{grade}", "")
            avg_score = round(sum([responsibility, self_regulation, organization, collaboration, independent_work]) / 5, 2)

            # Check if record exists
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

            # Update fields
            record.responsibility = responsibility
            record.self_regulation = self_regulation
            record.organization = organization
            record.collaboration_initiative = collaboration
            record.independent_work = independent_work
            record.remarks = remarks
            record.average_score = avg_score
            record.is_submitted = (action == "submit")

    db.session.commit()

    flash("Evaluations saved successfully." if action == "save" else "Evaluations submitted!", "success")
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