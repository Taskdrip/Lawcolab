from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from models import User, LawFirm, ROLE_ADMIN, ROLE_TEAM_MEMBER, ROLE_CLIENT
from forms import LoginForm, SignupForm, ProfileForm, ChangePasswordForm
from app import db, csrf
import uuid

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/superadmin-access', methods=['GET', 'POST'])
@csrf.exempt
def superadmin_access():
    """Direct super admin login without CSRF"""
    if current_user.is_authenticated:
        return redirect(url_for('superadmin.dashboard') if current_user.is_super_admin() else url_for('index'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if email and password:
            user = User.query.filter_by(email=email.lower()).first()
            if user and user.password_hash and user.check_password(password):
                print(f"DEBUG: User found: {user.email}, Role: {user.role}")
                if user.is_super_admin():
                    login_user(user, remember=True)
                    print(f"DEBUG: Super admin logged in successfully: {user.email}")
                    flash('Super Admin login successful!', 'success')
                    return redirect(url_for('superadmin.dashboard'))
                else:
                    print(f"DEBUG: User {user.email} is not super admin. Role: {user.role}")
                    flash('Access denied. Super Admin privileges required.', 'error')
            else:
                flash('Invalid credentials', 'error')
        else:
            flash('Please enter both email and password', 'error')
    
    return render_template('auth/superadmin_login.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
@csrf.exempt
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    
    # Handle form submission
    if request.method == 'POST':
        # Manual form processing to bypass CSRF issues
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        remember_me = bool(request.form.get('remember_me'))
        
        if email and password:
            user = User.query.filter_by(email=email.lower()).first()
            if user and user.password_hash and user.check_password(password):
                if not user.active:
                    flash('Your account has been deactivated. Please contact support.', 'error')
                    return render_template('auth/login.html', form=form)
                
                login_user(user, remember=remember_me)
                
                # Redirect to intended page or dashboard
                next_page = request.args.get('next')
                if not next_page or urlparse(next_page).netloc != '':
                    if user.is_super_admin():
                        next_page = url_for('superadmin.dashboard')
                    elif user.is_admin():
                        next_page = url_for('admin.admin_dashboard')
                    elif user.is_team_member():
                        next_page = url_for('index')
                    else:
                        next_page = url_for('index')
                return redirect(next_page)
            else:
                flash('Invalid email or password', 'error')
        else:
            flash('Please enter both email and password', 'error')
    
    return render_template('auth/login.html', form=form)

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = SignupForm()
    if form.validate_on_submit():
        # Create new law firm first
        new_firm = LawFirm()
        new_firm.name = form.law_firm_name.data
        new_firm.description = form.law_firm_description.data or f"Legal practice managed by {form.first_name.data} {form.last_name.data}"
        new_firm.email = form.email.data.lower() if form.email.data else None
        
        # Create user as law firm admin
        user = User()
        user.id = str(uuid.uuid4())
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        email = form.email.data
        if email:
            user.email = email.lower()
        user.phone = form.phone.data
        user.role = 'admin'  # All signups are law firm admins
        user.set_password(form.password.data)
        user.active = True
        
        try:
            db.session.add(new_firm)
            db.session.flush()  # Get the law firm ID
            
            # Associate user with their new law firm
            user.law_firm_id = new_firm.id
            db.session.add(user)
            db.session.commit()
            
            # Login the user immediately after successful registration
            login_user(user)
            flash('Registration successful! Welcome to LawColab.', 'success')
            return redirect(url_for('registration_success'))
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
        current_user.first_name = form.first_name.data
        current_user.last_name = form.last_name.data
        email = form.email.data
        if email:
            current_user.email = email.lower()
        current_user.phone = form.phone.data
        current_user.bio = form.bio.data
        
        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Failed to update profile. Please try again.', 'error')
    
    return render_template('auth/profile.html', form=form)

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        if current_user.check_password(form.current_password.data):
            current_user.set_password(form.new_password.data)
            try:
                db.session.commit()
                flash('Password changed successfully!', 'success')
                return redirect(url_for('auth.profile'))
            except Exception as e:
                db.session.rollback()
                flash('Failed to change password. Please try again.', 'error')
        else:
            flash('Current password is incorrect.', 'error')
    
    return render_template('auth/change_password.html', form=form)

@auth_bp.route('/edit_address', methods=['GET', 'POST'])
@login_required
def edit_address():
    from forms import AddressForm
    
    form = AddressForm()
    
    if form.validate_on_submit():
        # Update user address fields
        current_user.address_line_1 = form.address_line_1.data
        current_user.address_line_2 = form.address_line_2.data
        current_user.city = form.city.data
        current_user.state_province = form.state_province.data
        current_user.postal_code = form.postal_code.data
        current_user.country = form.country.data
        
        db.session.commit()
        flash('Address updated successfully!', 'success')
        return redirect(url_for('auth.profile'))
    
    # Pre-populate form with existing address data
    if request.method == 'GET':
        form.address_line_1.data = current_user.address_line_1
        form.address_line_2.data = current_user.address_line_2
        form.city.data = current_user.city
        form.state_province.data = current_user.state_province
        form.postal_code.data = current_user.postal_code
        form.country.data = current_user.country
    
    return render_template('auth/edit_address.html', form=form)