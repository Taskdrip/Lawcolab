import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from models import User, LawFirm, ROLE_ADMIN, ROLE_TEAM_MEMBER, ROLE_CLIENT
from forms import LoginForm, SignupForm, ProfileForm, ChangePasswordForm
from app import db, csrf
from utils.security import (
    limiter, record_failed_login, record_successful_login,
    is_account_locked, get_lockout_remaining
)
import uuid

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/superadmin-access', methods=['GET', 'POST'])
@csrf.exempt
@limiter.limit("5 per minute; 20 per hour")
def superadmin_access():
    """Super admin login — rate-limited, brute-force protected."""
    if current_user.is_authenticated:
        if current_user.is_super_admin():
            return redirect(url_for('superadmin.dashboard'))
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        ip = request.remote_addr

        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('auth/superadmin_login.html')

        user = User.query.filter_by(email=email).first()

        # Unified response to prevent user enumeration
        if not user or not user.password_hash:
            logger.warning("Super admin login failed (no user): %s from %s", email, ip)
            flash('Invalid credentials.', 'error')
            return render_template('auth/superadmin_login.html')

        if is_account_locked(user):
            mins = get_lockout_remaining(user)
            logger.warning("Locked account login attempt: %s from %s", email, ip)
            flash(
                f'Account temporarily locked due to multiple failed attempts. '
                f'Try again in {mins} minute(s).', 'error'
            )
            return render_template('auth/superadmin_login.html')

        if not user.check_password(password):
            record_failed_login(user, db)
            logger.warning("Super admin login failed (bad password): %s from %s", email, ip)
            attempts_left = max(0, 10 - (user.failed_login_attempts or 0))
            flash(
                f'Invalid credentials. {attempts_left} attempt(s) remaining before lockout.',
                'error'
            )
            return render_template('auth/superadmin_login.html')

        if not user.is_super_admin():
            logger.warning("Non-super-admin tried superadmin login: %s", email)
            flash('Access denied. Super Admin privileges required.', 'error')
            return render_template('auth/superadmin_login.html')

        if not user.active:
            flash('This account has been deactivated. Contact support.', 'error')
            return render_template('auth/superadmin_login.html')

        # Successful login
        record_successful_login(user, db, ip_address=ip)
        login_user(user, remember=True)
        session['logged_in'] = True
        session.permanent = True
        logger.info("Super admin login: %s from %s", email, ip)
        flash('Super Admin login successful!', 'success')
        return redirect(url_for('superadmin.dashboard'))

    return render_template('auth/superadmin_login.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
@csrf.exempt
@limiter.limit("10 per minute; 50 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    ip = request.remote_addr

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        remember_me = bool(request.form.get('remember_me'))

        if not email or not password:
            flash('Please enter both email and password.', 'error')
            return render_template('auth/login.html', form=form)

        user = User.query.filter_by(email=email).first()

        if not user or not user.password_hash:
            flash('Invalid email or password.', 'error')
            return render_template('auth/login.html', form=form)

        if is_account_locked(user):
            mins = get_lockout_remaining(user)
            flash(
                f'Account temporarily locked. Try again in {mins} minute(s).', 'error'
            )
            return render_template('auth/login.html', form=form)

        if not user.check_password(password):
            record_failed_login(user, db)
            flash('Invalid email or password.', 'error')
            return render_template('auth/login.html', form=form)

        if not user.active:
            flash('Your account has been deactivated. Please contact support.', 'error')
            return render_template('auth/login.html', form=form)

        # Successful login
        record_successful_login(user, db, ip_address=ip)
        login_user(user, remember=remember_me)
        logger.info("User login: %s from %s", email, ip)

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

    return render_template('auth/login.html', form=form)


@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = SignupForm()
    if form.validate_on_submit():
        from datetime import datetime, timedelta

        new_firm = LawFirm()
        new_firm.name = form.law_firm_name.data
        new_firm.description = (
            form.law_firm_description.data
            or f"Legal practice managed by {form.first_name.data} {form.last_name.data}"
        )
        new_firm.email = form.email.data.lower() if form.email.data else None
        new_firm.admin_access_granted = True
        new_firm.admin_access_expires = datetime.now() + timedelta(days=3)
        new_firm.subscription_period = '3days'

        user = User()
        user.id = str(uuid.uuid4())
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        if form.email.data:
            user.email = form.email.data.lower()
        user.phone = form.phone.data
        user.role = 'admin'
        user.set_password(form.password.data)
        user.active = True

        try:
            db.session.add(new_firm)
            db.session.flush()
            user.law_firm_id = new_firm.id
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Registration successful! Welcome to your 3-day free trial of LawColab.', 'success')
            return redirect(url_for('registration_success'))
        except Exception:
            db.session.rollback()
            logger.exception("Signup error")
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
        if form.email.data:
            current_user.email = form.email.data.lower()
        current_user.phone = form.phone.data
        current_user.bio = form.bio.data

        try:
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        except Exception:
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
            except Exception:
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
        current_user.address_line_1 = form.address_line_1.data
        current_user.address_line_2 = form.address_line_2.data
        current_user.city = form.city.data
        current_user.state_province = form.state_province.data
        current_user.postal_code = form.postal_code.data
        current_user.country = form.country.data

        db.session.commit()
        flash('Address updated successfully!', 'success')
        return redirect(url_for('auth.profile'))

    if request.method == 'GET':
        form.address_line_1.data = current_user.address_line_1
        form.address_line_2.data = current_user.address_line_2
        form.city.data = current_user.city
        form.state_province.data = current_user.state_province
        form.postal_code.data = current_user.postal_code
        form.country.data = current_user.country

    return render_template('auth/edit_address.html', form=form)
