from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, PasswordField, EmailField, DateField, FileField, BooleanField, DecimalField
from wtforms.validators import DataRequired, Email, Length, Optional, EqualTo, ValidationError, NumberRange
from models import User

class LoginForm(FlaskForm):
    email = EmailField('Email Address', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')

class SignupForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email Address', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    password = PasswordField('Password', validators=[
        DataRequired(), 
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    law_firm_name = StringField('Law Firm Name', validators=[DataRequired(), Length(min=2, max=200)])
    law_firm_description = TextAreaField('Law Firm Description', validators=[Optional(), Length(max=500)])

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data.lower()).first()
        if user:
            raise ValidationError('An account with this email already exists.')

class ProfileForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email Address', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    bio = TextAreaField('Bio/About', validators=[Optional(), Length(max=500)])

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[
        DataRequired(), 
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('new_password', message='Passwords must match')
    ])

class ClientForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email Address', validators=[Optional(), Email()])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    company_name = StringField('Company Name', validators=[Optional(), Length(max=200)])
    company_description = TextAreaField('Company Description', validators=[Optional(), Length(max=500)])
    industry = StringField('Industry', validators=[Optional(), Length(max=100)])
    website_url = StringField('Website URL', validators=[Optional(), Length(max=255)])
    password = PasswordField('Password', validators=[Optional(), Length(min=8)])

class TeamMemberForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email Address', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    bio = TextAreaField('Bio/About', validators=[Optional(), Length(max=500)])
    specialization = StringField('Specialization', validators=[Optional(), Length(max=200)])
    years_experience = StringField('Years of Experience', validators=[Optional()])
    education = TextAreaField('Education', validators=[Optional(), Length(max=500)])
    certifications = TextAreaField('Certifications', validators=[Optional(), Length(max=500)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])

class AdminUserForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired(), Length(min=2, max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(min=2, max=50)])
    email = EmailField('Email Address', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    role = SelectField('Role', choices=[
        ('client', 'Client'),
        ('team_member', 'Team Member'),
        ('admin', 'Administrator')
    ], validators=[DataRequired()])
    is_active = BooleanField('Active Account', default=True)
    password = PasswordField('Password', validators=[Optional(), Length(min=8)])

class ProjectForm(FlaskForm):
    name = StringField('Project Name', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=1000)])
    status = SelectField('Status', choices=[
        ('active', 'Active'),
        ('on_hold', 'On Hold'),
        ('completed', 'Completed')
    ], default='active')
    priority = SelectField('Priority', choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High')
    ], default='medium')
    deadline = DateField('Deadline', validators=[Optional()])
    budget = DecimalField('Budget', validators=[Optional(), NumberRange(min=0)])

class LawFirmForm(FlaskForm):
    name = StringField('Firm Name', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=1000)])
    address = TextAreaField('Address', validators=[Optional(), Length(max=500)])
    phone = StringField('Phone', validators=[Optional(), Length(max=20)])
    email = EmailField('Email', validators=[Optional(), Email()])
    website = StringField('Website', validators=[Optional(), Length(max=200)])

class ClientNoteForm(FlaskForm):
    note = TextAreaField('Note', validators=[DataRequired(), Length(max=2000)])

class LawFirmEditForm(FlaskForm):
    name = StringField('Firm Name', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=1000)])
    phone = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    email = EmailField('Email Address', validators=[Optional(), Email()])
    address = TextAreaField('Address', validators=[Optional(), Length(max=500)])
    website = StringField('Website', validators=[Optional(), Length(max=200)])
    practice_areas = TextAreaField('Practice Areas (one per line)', validators=[Optional()])