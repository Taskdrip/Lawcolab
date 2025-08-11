from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from models import User, ROLE_ADMIN, ROLE_TEAM_MEMBER, ROLE_CLIENT
from forms import LoginForm, SignupForm, ProfileForm, ChangePasswordForm
from app import db
import uuid

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        if email:
            user = User.query.filter_by(email=email.lower()).first()
            if user and user.password_hash and user.check_password(form.password.data):
                if not user.is_active():
                    flash('Your account has been deactivated. Please contact support.', 'error')
                    return render_template('auth/login.html', form=form)
                
                login_user(user, remember=form.remember_me.data)
                
                # Redirect to intended page or dashboard
                next_page = request.args.get('next')
                if not next_page or urlparse(next_page).netloc != '':
                    if user.is_admin():
                        next_page = url_for('admin.admin_dashboard')
                    elif user.is_team_member():
                        next_page = url_for('dashboard.team_member_dashboard')
                    else:
                        next_page = url_for('dashboard.client_dashboard')
                return redirect(next_page)
            else:
                flash('Invalid email or password', 'error')
        else:
            flash('Please enter a valid email address', 'error')
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = SignupForm()
    if form.validate_on_submit():
        user = User()
        user.id = str(uuid.uuid4())
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        email = form.email.data
        if email:
            user.email = email.lower()
        user.phone = form.phone.data
        user.role = form.role.data
        user.set_password(form.password.data)
        user.active = True
        
        try:
            db.session.add(user)
            db.session.commit()
            
            flash('Registration successful! Please log in to your account.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('Registration failed. Please try again.', 'error')
    
    return render_template('auth/signup.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    
    if form.validate_on_submit():
        # Check if email is being changed and if it's already taken
        if form.email.data.lower() != current_user.email:
            existing_user = User.query.filter_by(email=form.email.data.lower()).first()
            if existing_user:
                flash('Email address is already in use.', 'error')
                return render_template('auth/profile.html', form=form)
        
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        current_user.email = form.email.data.lower()
        current_user.phone = form.phone.data
        current_user.bio = form.bio.data
        
        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('auth.profile'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to update profile. Please try again.', 'error')
    
    return render_template('auth/profile.html', form=form)

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('Current password is incorrect.', 'error')
            return render_template('auth/change_password.html', form=form)
        
        current_user.set_password(form.new_password.data)
        
        try:
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('auth.profile'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to change password. Please try again.', 'error')
    
    return render_template('auth/change_password.html', form=form)