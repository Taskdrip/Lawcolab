from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from functools import wraps
from forms import AdminUserForm, LawFirmForm, ProjectForm
from app import db
from models import LawFirm, User, Project, ProjectAssignment, ROLE_ADMIN, ROLE_TEAM_MEMBER, ROLE_CLIENT
from werkzeug.utils import secure_filename
import uuid
import os

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
def manage_users():
    """List and manage all users"""
    users = User.query.all()
    return render_template('admin/manage_users.html', users=users)

@admin_bp.route('/users/add', methods=['GET', 'POST'])
@require_admin
def add_user():
    """Add new team member"""
    form = AdminUserForm()
    
    if form.validate_on_submit():
        # Check if email already exists
        email = form.email.data
        if email:
            existing_user = User.query.filter_by(email=email.lower()).first()
            if existing_user:
                flash('A user with this email already exists.', 'error')
                return render_template('admin/add_user.html', form=form)
        
        user = User()
        user.id = str(uuid.uuid4())
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        if email:
            user.email = email.lower()
        user.phone = form.phone.data
        user.role = form.role.data
        user.set_password(form.password.data)
        user.active = True
        
        try:
            db.session.add(user)
            db.session.commit()
            
            flash(f'User {user.full_name} added successfully!', 'success')
            return redirect(url_for('admin.manage_users'))
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
        email = form.email.data
        if email:
            user.email = email.lower()
        user.phone = form.phone.data
        user.role = form.role.data
        user.active = form.is_active.data
        
        if form.password.data:
            user.set_password(form.password.data)
        
        # Handle profile image upload
        if 'profile_image' in request.files:
            file = request.files['profile_image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{user_id}_{file.filename}")
                upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
                os.makedirs(upload_path, exist_ok=True)
                
                file_path = os.path.join(upload_path, filename)
                file.save(file_path)
                user.profile_image_url = f"/static/uploads/profiles/{filename}"
        
        try:
            db.session.commit()
            flash(f'User {user.full_name} updated successfully!', 'success')
            return redirect(url_for('admin.manage_users'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to update user. Please try again.', 'error')
    
    return render_template('admin/edit_user.html', form=form, user=user)

@admin_bp.route('/users/<user_id>/grant-admin')
@require_admin
def grant_admin(user_id):
    """Grant admin privileges to a user"""
    user = User.query.get_or_404(user_id)
    
    if user.role == ROLE_ADMIN:
        flash(f'{user.full_name} is already an admin.', 'info')
    else:
        user.role = ROLE_ADMIN
        try:
            db.session.commit()
            flash(f'Admin privileges granted to {user.full_name}!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Failed to grant admin privileges.', 'error')
    
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/users/<user_id>/toggle-status')
@require_admin
def toggle_user_status(user_id):
    """Toggle user active/inactive status"""
    user = User.query.get_or_404(user_id)
    
    user.active = not user.active
    status = "activated" if user.active else "deactivated"
    
    try:
        db.session.commit()
        flash(f'User {user.full_name} has been {status}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Failed to update user status.', 'error')
    
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/projects')
@require_admin
def manage_projects():
    """List and manage all projects"""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return render_template('admin/manage_projects.html', projects=projects)

@admin_bp.route('/projects/add', methods=['GET', 'POST'])
@require_admin
def add_project():
    """Add new project"""
    form = ProjectForm()
    
    # Get all clients and team members for assignment
    clients = User.query.filter_by(role=ROLE_CLIENT).all()
    team_members = User.query.filter(User.role.in_([ROLE_TEAM_MEMBER, ROLE_ADMIN])).all()
    
    if form.validate_on_submit():
        project = Project()
        project.created_by_id = current_user.id
        project.title = form.name.data
        project.description = form.description.data
        project.status = form.status.data
        project.priority = form.priority.data
        project.deadline = form.deadline.data
        # project.budget = form.budget.data  # TODO: Add budget field to Project model
        
        try:
            db.session.add(project)
            db.session.flush()  # Get the project ID
            
            # Assign selected users to project
            assigned_users = request.form.getlist('assigned_users')
            if assigned_users:
                for user_id in assigned_users:
                    assignment = ProjectAssignment()
                    assignment.project_id = project.id
                    assignment.user_id = user_id
                    db.session.add(assignment)
            
            db.session.commit()
            flash(f'Project "{project.title}" created successfully!', 'success')
            return redirect(url_for('admin.manage_projects'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to create project. Please try again.', 'error')
    
    return render_template('admin/add_project.html', form=form, clients=clients, team_members=team_members)

@admin_bp.route('/projects/<project_id>/assign', methods=['GET', 'POST'])
@require_admin
def assign_project_users(project_id):
    """Assign lawyers and clients to a project"""
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'POST':
        # Clear existing assignments
        ProjectAssignment.query.filter_by(project_id=project_id).delete()
        
        # Add new assignments
        assigned_users = request.form.getlist('assigned_users')
        for user_id in assigned_users:
            assignment = ProjectAssignment()
            assignment.project_id = project_id
            assignment.user_id = user_id
            db.session.add(assignment)
        
        try:
            db.session.commit()
            flash(f'Project assignments updated for "{project.title}"!', 'success')
            return redirect(url_for('admin.manage_projects'))
        except Exception as e:
            db.session.rollback()
            flash('Failed to update project assignments.', 'error')
    
    # Get all users for assignment
    all_users = User.query.filter_by(active=True).all()
    current_assignments = [a.user_id for a in project.assignments]
    
    return render_template('admin/assign_project.html', 
                         project=project, 
                         all_users=all_users, 
                         current_assignments=current_assignments)

@admin_bp.route('/upload-profile-image', methods=['POST'])
@require_admin
def upload_profile_image():
    """Handle profile image upload for users"""
    user_id = request.form.get('user_id')
    user = User.query.get_or_404(user_id)
    
    if 'profile_image' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('admin.edit_user', user_id=user_id))
    
    file = request.files['profile_image']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('admin.edit_user', user_id=user_id))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{user_id}_{file.filename}")
        upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
        os.makedirs(upload_path, exist_ok=True)
        
        file_path = os.path.join(upload_path, filename)
        file.save(file_path)
        
        # Update user profile image URL
        user.profile_image_url = f"/static/uploads/profiles/{filename}"
        
        try:
            db.session.commit()
            flash('Profile image updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Failed to update profile image.', 'error')
    else:
        flash('Invalid file type. Please upload JPG, PNG, or GIF files.', 'error')
    
    return redirect(url_for('admin.edit_user', user_id=user_id))

def allowed_file(filename):
    """Check if file extension is allowed"""
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions