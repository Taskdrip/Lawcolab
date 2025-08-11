from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, FileField, HiddenField
from wtforms.validators import DataRequired, Email, Optional, Length
from flask_wtf.file import FileAllowed

class LawFirmProfileForm(FlaskForm):
    name = StringField('Firm Name', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description')
    logo_url = StringField('Logo URL', validators=[Optional(), Length(max=500)])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    email = StringField('Email', validators=[Optional(), Email(), Length(max=120)])
    address = TextAreaField('Address')
    website = StringField('Website', validators=[Optional(), Length(max=200)])
    practice_areas = TextAreaField('Practice Areas (one per line)')

class ProjectForm(FlaskForm):
    title = StringField('Project Title', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description')
    status = SelectField('Status', choices=[
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold')
    ], default='active')
    priority = SelectField('Priority', choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High')
    ], default='medium')
    deadline = DateField('Deadline', validators=[Optional()])

class UserRoleForm(FlaskForm):
    role = SelectField('Role', choices=[
        ('admin', 'Admin'),
        ('team_member', 'Team Member'),
        ('client', 'Client')
    ])

class UserProfileForm(FlaskForm):
    first_name = StringField('First Name', validators=[Optional(), Length(max=100)])
    last_name = StringField('Last Name', validators=[Optional(), Length(max=100)])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    bio = TextAreaField('Bio')

class ClientNoteForm(FlaskForm):
    note = TextAreaField('Note', validators=[DataRequired()])

class FileUploadForm(FlaskForm):
    file = FileField('File', validators=[
        DataRequired(),
        FileAllowed(['pdf', 'doc', 'docx', 'txt', 'jpg', 'jpeg', 'png'], 'Invalid file type')
    ])
    project_id = HiddenField()
