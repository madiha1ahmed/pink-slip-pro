from flask_wtf import FlaskForm
from wtforms import IntegerField, SubmitField, DateField, StringField, SelectField
from wtforms.validators import InputRequired, NumberRange, DataRequired
from wtforms.widgets import DateInput
from datetime import date

class HealthDataForm(FlaskForm):
    # render_kw type="date" makes the browser show a real calendar picker;
    # default=date.today pre-fills today so the teacher usually doesn't touch it.
    date = DateField('Date', format='%Y-%m-%d', validators=[DataRequired()],
                     default=date.today, render_kw={"type": "date"})
    slip_type = SelectField("Type of homework slip", 
                            choices=[("", 'Select type of homework slip')]+[(str(i), f"{i}") for i in ["Pink Slip", "Yellow Slip"]],
                            validators = [DataRequired()])




    student_name = StringField('Name of student', validators=[DataRequired()])
    #grade_of_student = IntegerField('Grade', validators=[InputRequired(), NumberRange(min=1)])
    grade_of_student = SelectField(
        'Grade',
        choices=[('', 'Select Grade')] + [(str(i), f"{i}") for i in ['JK','SK',1,2,3,4,5,6,7,8]],  # Add placeholder option
        validators=[DataRequired()]
    )
    subject_of_student = SelectField(
        'Subject',
        choices=[('', 'Select Subject')] + [(str(i), f"{i}") for i in ['Math', 'Science', 'English', 'Social', 'French', 'Arabic', 'Islamic Studies', 'Quran', 'Art', 'Gym']],  # Add placeholder option
        validators=[DataRequired()]
    )
    homework_desc = StringField('Missing Homework Description', validators=[DataRequired()])
    submit = SubmitField('Assign slip')
