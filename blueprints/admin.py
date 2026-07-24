from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from app import db
from models import User, Project, LawFirm, DashboardSlider, Invoice, DirectMessage, CalendarEvent, ROLE_ADMIN, ROLE_TEAM_MEMBER, ROLE_CLIENT
from utils.decorators import require_super_admin
from utils.decorators import require_admin
from utils.trial_access import require_active_subscription, trial_warning_context, get_trial_notification
from forms import ClientForm, TeamMemberForm
import uuid
import os
from datetime import date, timedelta
from werkzeug.utils import secure_filename

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard')
@require_admin
@require_active_subscription
def admin_dashboard():
    """Admin dashboard showing law firm statistics"""
    # Ensure admin has a law firm
    if not current_user.law_firm_id:
        current_user.create_law_firm_if_admin()

    law_firm_id = current_user.law_firm_id

    # Get law firm statistics
    total_clients = User.query.filter_by(law_firm_id=law_firm_id, role=ROLE_CLIENT).count()
    total_team_members = User.query.filter_by(law_firm_id=law_firm_id, role=ROLE_TEAM_MEMBER).count()
    total_projects = Project.query.filter_by(law_firm_id=law_firm_id).count()

    # Recent activity
    recent_clients = User.query.filter_by(law_firm_id=law_firm_id, role=ROLE_CLIENT).order_by(User.created_at.desc()).limit(5).all()
    recent_projects = Project.query.filter_by(law_firm_id=law_firm_id).order_by(Project.created_at.desc()).limit(5).all()

    # ── Smart Notifications ──────────────────────────────────────────────────
    today = date.today()
    soon = today + timedelta(days=7)
    smart_notifications = []

    # 1. Projects with deadlines in the next 7 days
    due_projects = Project.query.filter(
        Project.law_firm_id == law_firm_id,
        Project.deadline != None,
        Project.deadline >= today,
        Project.deadline <= soon,
        Project.status == 'active'
    ).order_by(Project.deadline).limit(5).all()
    for p in due_projects:
        days_left = (p.deadline - today).days
        label = "Due today!" if days_left == 0 else f"Due in {days_left} day{'s' if days_left != 1 else ''}"
        smart_notifications.append({
            'type': 'deadline',
            'icon': 'fas fa-calendar-exclamation',
            'color': 'danger' if days_left <= 1 else 'warning',
            'title': f'Project deadline: {p.title}',
            'detail': label,
            'link': url_for('projects.project_detail', project_id=p.id),
        })

    # 2. Overdue invoices
    overdue_invoices = Invoice.query.filter(
        Invoice.law_firm_id == law_firm_id,
        Invoice.status.in_(['sent', 'overdue']),
        Invoice.due_date < today
    ).order_by(Invoice.due_date).limit(5).all()
    for inv in overdue_invoices:
        days_late = (today - inv.due_date).days
        smart_notifications.append({
            'type': 'invoice',
            'icon': 'fas fa-file-invoice-dollar',
            'color': 'danger',
            'title': f'Invoice #{inv.invoice_number} overdue',
            'detail': f'{days_late} day{"s" if days_late != 1 else ""} past due — ${inv.total_amount:,.2f}',
            'link': url_for('invoices.view_invoice', id=inv.id),
        })

    # 3. Invoices due within 7 days (not yet overdue)
    upcoming_invoices = Invoice.query.filter(
        Invoice.law_firm_id == law_firm_id,
        Invoice.status.in_(['sent', 'draft']),
        Invoice.due_date >= today,
        Invoice.due_date <= soon
    ).order_by(Invoice.due_date).limit(3).all()
    for inv in upcoming_invoices:
        days_left = (inv.due_date - today).days
        smart_notifications.append({
            'type': 'invoice_upcoming',
            'icon': 'fas fa-file-invoice',
            'color': 'warning',
            'title': f'Invoice #{inv.invoice_number} due soon',
            'detail': f'Due in {days_left} day{"s" if days_left != 1 else ""} — ${inv.total_amount:,.2f}',
            'link': url_for('invoices.view_invoice', id=inv.id),
        })

    # 4. Unread direct messages
    unread_count = DirectMessage.query.filter_by(
        receiver_id=current_user.id,
        is_read=False
    ).count()
    if unread_count:
        smart_notifications.append({
            'type': 'message',
            'icon': 'fas fa-envelope',
            'color': 'info',
            'title': f'{unread_count} unread message{"s" if unread_count != 1 else ""}',
            'detail': 'You have unread messages waiting',
            'link': url_for('chat.chat_home'),
        })

    # 5. Upcoming calendar events (next 3 days)
    very_soon = today + timedelta(days=3)
    try:
        from datetime import datetime as dt
        upcoming_events = CalendarEvent.query.filter(
            CalendarEvent.law_firm_id == law_firm_id,
            CalendarEvent.start_datetime >= dt.combine(today, dt.min.time()),
            CalendarEvent.start_datetime <= dt.combine(very_soon, dt.max.time())
        ).order_by(CalendarEvent.start_datetime).limit(4).all()
        for ev in upcoming_events:
            ev_date = ev.start_datetime.date()
            days_left = (ev_date - today).days
            smart_notifications.append({
                'type': 'event',
                'icon': 'fas fa-calendar-check',
                'color': 'primary',
                'title': ev.title,
                'detail': 'Today' if days_left == 0 else f'In {days_left} day{"s" if days_left != 1 else ""}',
                'link': url_for('calendar.index'),
            })
    except Exception:
        pass
    # ────────────────────────────────────────────────────────────────────────

    # Add trial context and notifications
    context = trial_warning_context()
    trial_notification = get_trial_notification()

    return render_template('admin/dashboard.html',
                         total_clients=total_clients,
                         total_team_members=total_team_members,
                         total_projects=total_projects,
                         recent_clients=recent_clients,
                         recent_projects=recent_projects,
                         trial_notification=trial_notification,
                         smart_notifications=smart_notifications,
                         **context)

@admin_bp.route('/add-client', methods=['GET', 'POST'])
@require_admin
def add_client():
    """Admin can add new clients to their law firm"""
    form = ClientForm()
    
    if form.validate_on_submit():
        # Create new client user
        client = User()
        client.id = str(uuid.uuid4())
        client.first_name = form.first_name.data
        client.last_name = form.last_name.data
        client.email = form.email.data.lower() if form.email.data else None
        client.phone = form.phone.data
        client.company_name = form.company_name.data
        client.company_description = form.company_description.data
        client.industry = form.industry.data
        client.website_url = form.website_url.data
        client.role = ROLE_CLIENT
        client.law_firm_id = current_user.law_firm_id  # Associate with admin's law firm
        client.active = True
        
        # Set a default password (clients should change this)
        if form.password.data:
            client.set_password(form.password.data)
        else:
            client.set_password('ClientPassword123!')  # Default password
        
        try:
            db.session.add(client)
            db.session.commit()
            flash(f'Client {client.full_name} has been added to your law firm successfully!', 'success')
            return redirect(url_for('clients.list_clients'))
        except Exception as e:
            db.session.rollback()
            flash('Error adding client. Please try again.', 'error')
    
    return render_template('admin/add_client.html', form=form)

@admin_bp.route('/add-team-member', methods=['GET', 'POST'])
@require_admin  
def add_team_member():
    """Admin can add new team members to their law firm"""
    # Ensure admin has a law firm
    if not current_user.law_firm_id:
        current_user.create_law_firm_if_admin()
        db.session.commit()
    
    form = TeamMemberForm()
    
    if form.validate_on_submit():
        # Create new team member user
        team_member = User()
        team_member.id = str(uuid.uuid4())
        team_member.first_name = form.first_name.data
        team_member.last_name = form.last_name.data
        team_member.email = form.email.data.lower() if form.email.data else None
        team_member.phone = form.phone.data
        team_member.bio = form.bio.data
        team_member.specialization = form.specialization.data
        # Convert years_experience to int if provided
        if form.years_experience.data and form.years_experience.data.strip():
            try:
                team_member.years_experience = int(form.years_experience.data)
            except ValueError:
                team_member.years_experience = None
        else:
            team_member.years_experience = None
        team_member.education = form.education.data
        team_member.certifications = form.certifications.data
        team_member.role = ROLE_TEAM_MEMBER
        team_member.law_firm_id = current_user.law_firm_id  # Associate with admin's law firm
        team_member.active = True
        
        # Set password
        team_member.set_password(form.password.data)
        
        try:
            db.session.add(team_member)
            db.session.commit()
            flash(f'Team member {team_member.full_name} has been added to your law firm successfully!', 'success')
            return redirect(url_for('team.list_team'))
        except Exception as e:
            db.session.rollback()
            print(f"Error adding team member: {str(e)}")  # Debug logging
            flash(f'Error adding team member: {str(e)}', 'error')
    
    return render_template('admin/add_team_member.html', form=form)

@admin_bp.route('/manage-projects')
@require_admin
def manage_projects():
    """Admin project management page"""
    projects = Project.query.filter_by(law_firm_id=current_user.law_firm_id).order_by(Project.created_at.desc()).all()
    return render_template('admin/manage_projects.html', projects=projects)

@admin_bp.route('/manage-users')
@require_admin
def manage_users():
    """Admin user management page with beautiful interface"""
    # Get all users in the admin's law firm
    users = User.query.filter_by(law_firm_id=current_user.law_firm_id).order_by(User.created_at.desc()).all()
    
    # Get statistics
    total_users = len(users)
    active_users = len([u for u in users if u.active])
    inactive_users = total_users - active_users
    
    # Separate by role
    admins = [u for u in users if u.role == ROLE_ADMIN]
    team_members = [u for u in users if u.role == ROLE_TEAM_MEMBER]
    clients = [u for u in users if u.role == ROLE_CLIENT]
    
    return render_template('admin/manage_users.html', 
                         users=users,
                         total_users=total_users,
                         active_users=active_users,
                         inactive_users=inactive_users,
                         admins=admins,
                         team_members=team_members,
                         clients=clients)

@admin_bp.route('/delete-user/<user_id>', methods=['POST'])
@require_admin
def delete_user(user_id):
    """Delete a user from the database"""
    user = User.query.get_or_404(user_id)
    
    # Security check: ensure user belongs to admin's law firm
    if user.law_firm_id != current_user.law_firm_id:
        flash('You can only delete users from your own law firm.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    # Prevent admin from deleting themselves
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    try:
        # Store name for confirmation message
        user_name = user.full_name
        
        # Delete user
        db.session.delete(user)
        db.session.commit()
        
        flash(f'User {user_name} has been permanently deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to delete user. Please try again.', 'error')
    
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/toggle-user-status/<user_id>', methods=['POST'])
@require_admin
def toggle_user_status(user_id):
    """Toggle user active/inactive status"""
    user = User.query.get_or_404(user_id)
    
    # Security check: ensure user belongs to admin's law firm
    if user.law_firm_id != current_user.law_firm_id:
        flash('You can only manage users from your own law firm.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    # Prevent admin from deactivating themselves
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    try:
        user.active = not user.active
        status = 'activated' if user.active else 'deactivated'
        db.session.commit()
        
        flash(f'User {user.full_name} has been {status}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to update user status. Please try again.', 'error')
    
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/firm-profile', methods=['GET', 'POST'])
@require_admin
def firm_profile():
    """Admin can manage law firm profile"""
    firm = LawFirm.query.get(current_user.law_firm_id)
    
    if request.method == 'POST' and firm:
        firm.name = request.form.get('name')
        firm.description = request.form.get('description')
        firm.phone = request.form.get('phone')
        firm.email = request.form.get('email')
        firm.address = request.form.get('address')
        firm.website = request.form.get('website')
        firm.practice_areas = request.form.get('practice_areas')
        
        try:
            db.session.commit()
            flash('Law firm profile updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error updating profile. Please try again.', 'error')
    
    return render_template('admin/firm_profile.html', firm=firm)

@admin_bp.route('/banking-settings', methods=['GET', 'POST'])
@require_admin
def banking_settings():
    """Admin can manage banking details for receiving payments"""
    firm = LawFirm.query.get(current_user.law_firm_id)
    
    if request.method == 'POST' and firm:
        # Update banking details
        firm.bank_name = request.form.get('bank_name', '').strip()
        firm.account_holder_name = request.form.get('account_holder_name', '').strip()
        firm.account_number = request.form.get('account_number', '').strip()
        firm.routing_number = request.form.get('routing_number', '').strip()
        firm.swift_code = request.form.get('swift_code', '').strip()
        firm.tax_id = request.form.get('tax_id', '').strip()
        
        try:
            db.session.commit()
            flash('Banking details updated successfully! Your clients will now see these payment details on invoices.', 'success')
            return redirect(url_for('admin.banking_settings'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating banking details. Please try again.', 'error')
    
    return render_template('admin/banking_settings.html', firm=firm)


# ── Dashboard Slider Management ───────────────────────────────────────────────

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
SLIDER_UPLOAD_FOLDER = 'static/uploads/sliders'

def _allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def _seed_default_sliders(law_firm_id):
    """Create platform-default slider slides for a new law firm."""
    defaults = [
        dict(title="Manage Cases Effortlessly",
             subtitle="All your active matters in one place",
             description="Track deadlines, documents, and progress across every case with crystal-clear visibility.",
             cta_text="View Projects", cta_link="/projects/",
             bg_color="#0d1b4b", icon="fas fa-briefcase", sort_order=0),
        dict(title="Professional Invoicing",
             subtitle="Get paid faster with smart invoices",
             description="Generate beautiful PDF invoices, track payments, and send automated reminders to clients.",
             cta_text="Go to Invoices", cta_link="/invoices/",
             bg_color="#1a3a2a", icon="fas fa-file-invoice-dollar", sort_order=1),
        dict(title="Real-Time Team Chat",
             subtitle="Collaborate without leaving the platform",
             description="Message your team and clients instantly. Keep all legal communications secure and searchable.",
             cta_text="Open Chat", cta_link="/enhanced-chat/support",
             bg_color="#3a1a0d", icon="fas fa-comments", sort_order=2),
        dict(title="Court Dates & Deadlines",
             subtitle="Never miss a critical date again",
             description="Sync court hearings, client meetings and filing deadlines in one shared calendar.",
             cta_text="Open Calendar", cta_link="/calendar/",
             bg_color="#1a0d3a", icon="fas fa-calendar-check", sort_order=3),
        dict(title="Client Management Hub",
             subtitle="Every client relationship, perfectly organised",
             description="Store contact details, case history, notes and documents — all linked to each client profile.",
             cta_text="View Clients", cta_link="/clients/",
             bg_color="#3a0d1a", icon="fas fa-users", sort_order=4),
    ]
    for d in defaults:
        slide = DashboardSlider(law_firm_id=law_firm_id, **d)
        db.session.add(slide)
    db.session.commit()


@admin_bp.route('/sliders')
@require_super_admin
def manage_sliders():
    """List all dashboard slider slides for this law firm."""
    sliders = (DashboardSlider.query
               .filter_by(law_firm_id=current_user.law_firm_id)
               .order_by(DashboardSlider.sort_order)
               .all())
    if not sliders:
        _seed_default_sliders(current_user.law_firm_id)
        sliders = (DashboardSlider.query
                   .filter_by(law_firm_id=current_user.law_firm_id)
                   .order_by(DashboardSlider.sort_order)
                   .all())
    return render_template('admin/manage_sliders.html', sliders=sliders)


@admin_bp.route('/sliders/add', methods=['GET', 'POST'])
@require_super_admin
def add_slider():
    """Add a new dashboard slider slide."""
    if request.method == 'POST':
        slide = DashboardSlider()
        slide.law_firm_id = current_user.law_firm_id
        slide.title       = request.form.get('title', '').strip()
        slide.subtitle    = request.form.get('subtitle', '').strip()
        slide.description = request.form.get('description', '').strip()
        slide.cta_text    = request.form.get('cta_text', 'Learn More').strip()
        slide.cta_link    = request.form.get('cta_link', '#').strip()
        slide.bg_color    = request.form.get('bg_color', '#0d1b4b').strip()
        slide.icon        = request.form.get('icon', 'fas fa-star').strip()
        slide.sort_order  = int(request.form.get('sort_order', 0) or 0)
        slide.is_active   = 'is_active' in request.form

        # Handle background image upload
        file = request.files.get('bg_image')
        if file and file.filename and _allowed_image(file.filename):
            os.makedirs(SLIDER_UPLOAD_FOLDER, exist_ok=True)
            fname = secure_filename(f"{uuid.uuid4()}_{file.filename}")
            file.save(os.path.join(SLIDER_UPLOAD_FOLDER, fname))
            slide.bg_image = f"uploads/sliders/{fname}"

        if not slide.title:
            flash('Title is required.', 'error')
            return render_template('admin/slider_form.html', slide=None, action='add')

        db.session.add(slide)
        db.session.commit()
        flash('Slide added successfully!', 'success')
        return redirect(url_for('admin.manage_sliders'))

    return render_template('admin/slider_form.html', slide=None, action='add')


@admin_bp.route('/sliders/<int:slider_id>/edit', methods=['GET', 'POST'])
@require_super_admin
def edit_slider(slider_id):
    """Edit an existing dashboard slider slide."""
    slide = DashboardSlider.query.get_or_404(slider_id)
    if slide.law_firm_id != current_user.law_firm_id:
        flash('Access denied.', 'error')
        return redirect(url_for('admin.manage_sliders'))

    if request.method == 'POST':
        slide.title       = request.form.get('title', '').strip()
        slide.subtitle    = request.form.get('subtitle', '').strip()
        slide.description = request.form.get('description', '').strip()
        slide.cta_text    = request.form.get('cta_text', 'Learn More').strip()
        slide.cta_link    = request.form.get('cta_link', '#').strip()
        slide.bg_color    = request.form.get('bg_color', '#0d1b4b').strip()
        slide.icon        = request.form.get('icon', 'fas fa-star').strip()
        slide.sort_order  = int(request.form.get('sort_order', 0) or 0)
        slide.is_active   = 'is_active' in request.form

        file = request.files.get('bg_image')
        if file and file.filename and _allowed_image(file.filename):
            os.makedirs(SLIDER_UPLOAD_FOLDER, exist_ok=True)
            fname = secure_filename(f"{uuid.uuid4()}_{file.filename}")
            file.save(os.path.join(SLIDER_UPLOAD_FOLDER, fname))
            slide.bg_image = f"uploads/sliders/{fname}"

        if not slide.title:
            flash('Title is required.', 'error')
            return render_template('admin/slider_form.html', slide=slide, action='edit')

        db.session.commit()
        flash('Slide updated successfully!', 'success')
        return redirect(url_for('admin.manage_sliders'))

    return render_template('admin/slider_form.html', slide=slide, action='edit')


@admin_bp.route('/sliders/<int:slider_id>/delete', methods=['POST'])
@require_super_admin
def delete_slider(slider_id):
    """Delete a dashboard slider slide."""
    slide = DashboardSlider.query.get_or_404(slider_id)
    if slide.law_firm_id != current_user.law_firm_id:
        flash('Access denied.', 'error')
        return redirect(url_for('admin.manage_sliders'))
    db.session.delete(slide)
    db.session.commit()
    flash('Slide deleted.', 'success')
    return redirect(url_for('admin.manage_sliders'))


@admin_bp.route('/sliders/<int:slider_id>/toggle', methods=['POST'])
@require_super_admin
def toggle_slider(slider_id):
    """Toggle a slide's active/inactive status."""
    slide = DashboardSlider.query.get_or_404(slider_id)
    if slide.law_firm_id != current_user.law_firm_id:
        flash('Access denied.', 'error')
        return redirect(url_for('admin.manage_sliders'))
    slide.is_active = not slide.is_active
    db.session.commit()
    return redirect(url_for('admin.manage_sliders'))