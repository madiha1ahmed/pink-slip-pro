import pandas as pd
from app import db, Subject  # Import db and Student model from your app

# Path to your Excel file
file_path = "subjects.xlsx"

# Read the Excel file into a pandas DataFrame
df = pd.read_excel(file_path)

# Iterate through the rows and add each student to the database
for _, row in df.iterrows():
    subject = Subject(
        subject=row["Subject"],  # Replace with the column name in your Excel file
        #grade=row["Grade"]  # Replace with the column name in your Excel file
    )
    db.session.add(subject)

# Commit the changes to save them in the database
db.session.commit()

print("Subject database has been populated successfully!")
