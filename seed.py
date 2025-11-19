from app_old import db
from app_old import HealthData
from datetime import datetime, timedelta
import random

# Clear the database
db.drop_all()
db.create_all()

# Generate dummy data for the past 3 months
start_date = datetime.now() - timedelta(days=90)
slip_type_options = ["Pink Slip", "Yellow Slip"]
student_name_options = ["Fatima Al-Kheichen", "Manessa Farhat", "Maryam Farhat", "Ali Al-Kheichen", "Mohammad Farhat", "Murtaza Naqvi"]  # Example activities
subject_of_student_options = ['Math', 'Science', 'Social', 'Art', 'Gym', 'Quran', 'Islamic Studies', 'Coding']
homework_desc_options = ['MEP Math Page 24', 'Unit 1 Self-check', 'Unit 3 Something to do', 'Unit 9 Uluru Paininting']

for i in range(90):
    date = start_date + timedelta(days=i)
    slip_type = random.choice(slip_type_options)
    student_name = random.choice(student_name_options)  # Exercise in minutes
    grade_of_student = random.randint(1, 8)  # Meditation in minutes
    subject_of_student = random.choice(subject_of_student_options)
    homework_desc = random.choice(homework_desc_options)
    data = HealthData(date=date, slip_type=slip_type, student_name=student_name, grade_of_student=grade_of_student, subject_of_student=subject_of_student, homework_desc=homework_desc)
    db.session.add(data)

db.session.commit()
print("Database seeded with dummy data.")