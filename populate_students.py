import pandas as pd
from app import db, Student  # Import db and Student model from your app

# Path to your Excel file
file_path = "students.xlsx"

# Read the Excel file into a pandas DataFrame
df = pd.read_excel(file_path)

# Iterate through the rows and add each student to the database
for _, row in df.iterrows():
    student = Student(
        name=row["Name"],  # Replace with the column name in your Excel file
        grade=row["Grade"],
        parent_email_mom=row['Parent Email Mom'],
        parent_email_dad=row['Parent Email Dad'],
        parent_whatsapp = row['Parent WhatsApp'],
        student_email = row["Student Email"]  # Replace with the column name in your Excel file
    )
    db.session.add(student)

# Commit the changes to save them in the database
db.session.commit()

print("Student database has been populated successfully!")
