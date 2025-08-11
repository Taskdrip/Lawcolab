from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from functools import wraps
from forms import AdminUserForm, LawFirmForm
from app import db
from models import LawFirm, User, Project, ROLE_ADMIN, ROLE_TEAM_MEMBER, ROLE_CLIENT
import uuid

def require_admin(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin():
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/dashboard')
@require_admin
def admin_dashboard():
    """Admin dashboard with comprehensive overview"""
    # Get statistics
    total_users = User.query.count()
    total_clients = User.query.filter_by(role=ROLE_CLIENT).count()
    total_team_members = User.query.filter_by(role=ROLE_TEAM_MEMBER).count()
    total_admins = User.query.filter_by(role=ROLE_ADMIN).count()
    total_projects = Project.query.count()
    active_projects = Project.query.filter_by(status='active').count()
    
    # Get recent users
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    # Get firm info
    firm = LawFirm.query.first()
    
    stats = {
        'total_users': total_users,
        'total_clients': total_clients,
        'total_team_members': total_team_members,
        'total_admins': total_admins,
        'total_projects': total_projects,
        'active_projects': active_projects
    }
    
    return render_template('admin/dashboard.html', stats=stats, recent_users=recent_users, firm=firm)

@admin_bp.route('/firm-profile', methods=['GET', 'POST'])
@require_admin
def firm_profile():
    """Manage law firm profile"""
    firm = LawFirm.query.first()
    form = LawFirmForm(obj=firm) if firm else LawFirmForm()
    
    if form.validate_on_submit():
        if not firm:
            firm = LawFirm()
            db.session.add(firm)
        
        form.populate_obj(firm)
        
        try:
            db.session.commit()
            flash('Firm profile updated successfully!', 'success')
            return redirect(url_for('admin.firm_profile'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to update firm profile. Please try again.', 'error')
    
    return render_template('admin/firm_profile.html', form=form, firm=firm)

@admin_bp.route('/users')
@require_admin
def list_users():
    """List all users with management options"""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)

@admin_bp.route('/users/add', methods=['GET', 'POST'])
@require_admin
def add_user():
    """Add new team member"""
    form = AdminUserForm()
    
    if form.validate_on_submit():
        # Check if email already exists
        existing_user = User.query.filter_by(email=form.email.data.lower()).first()
        if existing_user:
            flash('A user with this email already exists.', 'error')
            return render_template('admin/add_user.html', form=form)
        
        user = User()
        user.id = str(uuid.uuid4())
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.email = form.email.data.lower()
        user.phone = form.phone.data
        user.role = form.role.data
        user.bio = form.bio.data
        user.set_password(form.password.data)
        user.active = True
        
        try:
            db.session.add(user)
            db.session.commit()
            
            flash(f'User {user.full_name} added successfully!', 'success')
            return redirect(url_for('admin.list_users'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to add user. Please try again.', 'error')
    
    return render_template('admin/add_user.html', form=form)

@admin_bp.route('/users/<user_id>/edit', methods=['GET', 'POST'])
@require_admin
def edit_user(user_id):
    """Edit user details"""
    user = User.query.get_or_404(user_id)
    form = AdminUserForm(obj=user)
    
    if form.validate_on_submit():
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.email = form.email.data.lower()
        user.phone = form.phone.data
        user.role = form.role.data
        user.bio = form.bio.data
        
        if form.password.data:
            user.set_password(form.password.data)
        
        try:
            db.session.commit()
            flash(f'User {user.full_name} updated successfully!', 'success')
            return redirect(url_for('admin.list_users'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to update user. Please try again.', 'error')
    
    return render_template('admin/edit_user.html', form=form, user=user)

@admin_bp.route('/users/<user_id>/toggle-status', methods=['POST'])
@require_admin
def toggle_user_status(user_id):
    """Toggle user active status"""
    user = User.query.get_or_404(user_id)
    
    # Prevent admin from deactivating themselves
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('admin.list_users'))
    
    user.active = not user.active
    status = 'activated' if user.active else 'deactivated'
    
    try:
        db.session.commit()
        flash(f'User {user.full_name} {status} successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to update user status. Please try again.', 'error')
    
    return redirect(url_for('admin.list_users'))

@admin_bp.route('/projects')
@require_admin
def list_projects():
    """List all projects for assignment management"""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template('admin/projects.html', projects=projects)

@admin_bp.route('/projects/<project_id>/assign', methods=['GET', 'POST'])
@require_admin
def assign_project(project_id):
    """Assign team members to project"""
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'POST':
        user_ids = request.form.getlist('user_ids')
        
        # Clear existing assignments
        from models import ProjectAssignment
        ProjectAssignment.query.filter_by(project_id=project_id).delete()
        
        # Add new assignments
        for user_id in user_ids:
            user = User.query.get(user_id)
            if user and (user.is_team_member() or user.is_admin()):
                assignment = ProjectAssignment()
                assignment.project_id = project_id
                assignment.user_id = user_id
                assignment.assigned_at = db.func.now()
                db.session.add(assignment)
        
        try:
            db.session.commit()
            flash(f'Team members assigned to {project.name} successfully!', 'success')
            return redirect(url_for('admin.list_projects'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to assign team members. Please try again.', 'error')
    
    # Get available team members
    team_members = User.query.filter(User.role.in_([ROLE_TEAM_MEMBER, ROLE_ADMIN])).all()
    
    # Get current assignments
    from models import ProjectAssignment
    current_assignments = ProjectAssignment.query.filter_by(project_id=project_id).all()
    assigned_user_ids = [a.user_id for a in current_assignments]
    
    return render_template('admin/assign_project.html', 
                         project=project, 
                         team_members=team_members,
                         assigned_user_ids=assigned_user_ids)

@admin_bp.route('/team-management')
@require_admin
def team_management():
    """Team management overview"""
    return redirect(url_for('admin.list_users'))
    
    if form.validate_on_submit():
        # Check if email is being changed and if it's already taken
        if form.email.data.lower() != user.email:
            existing_user = User.query.filter_by(email=form.email.data.lower()).first()
            if existing_user:
                flash('A user with this email already exists.', 'error')
                return render_template('admin/edit_user.html', form=form, user=user)
        
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.email = form.email.data.lower()
        user.phone = form.phone.data
        user.role = form.role.data
        user.is_active = form.is_active.data
        
        if form.password.data:
            user.set_password(form.password.data)
        
        try:
            db.session.commit()
            flash(f'User {user.full_name} updated successfully!', 'success')
            return redirect(url_for('admin.manage_users'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to update user. Please try again.', 'error')
    
    return render_template('admin/edit_user.html', form=form, user=user)

@admin_bp.route('/users/<user_id>/toggle-status', methods=['POST'])
@require_admin
def toggle_user_status(user_id):
    """Toggle user active status"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('admin.manage_users'))
    
    user.is_active = not user.is_active
    status = 'activated' if user.is_active else 'deactivated'
    
    try:
        db.session.commit()
        flash(f'User {user.full_name} has been {status}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to update user status.', 'error')
    
    return redirect(url_for('admin.manage_users'))